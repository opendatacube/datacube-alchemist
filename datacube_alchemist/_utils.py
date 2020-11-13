try:
    # Only available in Python 3.8+
    from importlib import metadata
except ImportError:
    # Backport installed from PyPI
    from importlib_metadata import metadata, PackageNotFoundError
import boto3
import json
import logging
import structlog
import sys
from pathlib import Path
from toolz import dicttoolz
from typing import Dict

from datacube.model import Dataset
from datacube.virtual import Measurement, Transformation
from datacube_alchemist.settings import AlchemistTask
from eodatasets3 import DatasetAssembler, serialise
from eodatasets3.model import DatasetDoc, ProductDoc
from eodatasets3.properties import StacPropertyView
from eodatasets3.scripts.tostac import dc_to_stac, json_fallback
from eodatasets3.verify import PackageChecksum

_LOG = structlog.get_logger()


class FakeTransformation(Transformation):
    """
    Only writes input to output
    """

    def measurements(self, input_measurements) -> Dict[str, Measurement]:
        return input_measurements

    def compute(self, data) -> Dataset:
        return data


def _get_logger(name: str):
    logger = structlog.get_logger(name)
    logging.basicConfig(
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        stream=sys.stdout,
        level=logging.INFO,
        datefmt="%y-%m-%d %H:%M:%S",
    )
    structlog.configure(
        processors=[structlog.processors.KeyValueRenderer(key_order=["event"])],
        context_class=structlog.threadlocal.wrap_dict(dict),
        logger_factory=structlog.stdlib.LoggerFactory(),
    )

    return logger


def _write_thumbnail(task: AlchemistTask, dataset_assembler: DatasetAssembler):
    if task.settings.output.preview_image is not None:
        dataset_assembler.write_thumbnail(*task.settings.output.preview_image)
    elif task.settings.output.preview_image_singleband is not None:
        dataset_assembler.write_thumbnail_singleband(
            **task.settings.output.preview_image_singleband
        )


def _write_stac(
    metadata_path: Path,
    task: AlchemistTask,
    dataset_assembler: DatasetAssembler,
):
    out_dataset = serialise.from_path(metadata_path)
    stac_path = Path(str(metadata_path).replace("odc-metadata.yaml", "stac-item.json"))
    # Madness in deferred destination logic
    uri_base = dataset_assembler.names.destination_folder(
        Path(task.settings.output.location)
    )
    uri_base = str(uri_base) + "/"

    stac = dc_to_stac(
        out_dataset,
        metadata_path,
        stac_path,
        uri_base.replace("s3:/", "s3://"),
        task.settings.output.explorer_url,
        False,
    )

    with stac_path.open("w") as f:
        json.dump(stac, f, default=json_fallback)
    dataset_assembler.add_accessory_file("metadata:stac", stac_path)

    # dataset_assembler._checksum.write(dataset_assembler._accessories["checksum:sha1"])
    # Need a new checksummer because EODatasets is insane
    checksummer = PackageChecksum()
    checksum_file = (
        dataset_assembler._dataset_location
        / dataset_assembler._accessories["checksum:sha1"].name
    )
    checksummer.read(checksum_file)
    checksummer.add_file(stac_path)
    checksummer.write(checksum_file)
    return stac


def _stac_to_sns(sns_arn, stac):
    """
    Publish our STAC document to an SNS
    """
    bbox = stac["bbox"]

    client = boto3.client("sns")
    client.publish(
        TopicArn=sns_arn,
        Message=json.dumps(stac, indent=4, default=json_fallback),
        MessageAttributes={
            "action": {"DataType": "String", "StringValue": "ADDED"},
            "datetime": {
                "DataType": "String",
                "StringValue": str(dicttoolz.get_in(["properties", "datetime"], stac)),
            },
            "product": {
                "DataType": "String",
                "StringValue": dicttoolz.get_in(["properties", "odc:product"], stac),
            },
            "maturity": {
                "DataType": "String",
                "StringValue": dicttoolz.get_in(
                    ["properties", "dea:dataset_maturity"], stac
                ),
            },
            "bbox.ll_lon": {"DataType": "Number", "StringValue": str(bbox.left)},
            "bbox.ll_lat": {"DataType": "Number", "StringValue": str(bbox.bottom)},
            "bbox.ur_lon": {"DataType": "Number", "StringValue": str(bbox.right)},
            "bbox.ur_lat": {"DataType": "Number", "StringValue": str(bbox.top)},
        },
    )


def _munge_dataset_to_eo3(ds: Dataset) -> DatasetDoc:
    """
    Convert to the DatasetDoc format that eodatasets expects.
    """
    if ds.metadata_type.name == "eo_plus":
        return _convert_eo_plus(ds)

    if ds.metadata_type.name == "eo":
        return _convert_eo(ds)

    # Else we have an already mostly eo3 style dataset
    product = ProductDoc(name=ds.type.name)
    # Wrap properties to avoid typos and the like
    properties = StacPropertyView(ds.metadata_doc.get("properties", {}))
    if properties.get("eo:gsd"):
        del properties["eo:gsd"]
    return DatasetDoc(
        id=ds.id,
        product=product,
        crs=str(ds.crs),
        properties=properties,
        geometry=ds.extent,
    )


def _convert_eo_plus(ds) -> DatasetDoc:
    # Definitely need: # - 'datetime' # - 'eo:instrument' # - 'eo:platform' # - 'odc:region_code'
    properties = StacPropertyView(
        {
            "odc:region_code": ds.metadata.region_code,
            "datetime": ds.center_time,
            "eo:instrument": ds.metadata.instrument,
            "eo:platform": ds.metadata.platform,
            "landsat:landsat_scene_id": ds.metadata_doc.get(
                "tile_id", "??"
            ),  # Used to find abbreviated instrument id
            "sentinel:sentinel_tile_id": ds.metadata_doc.get("tile_id", "??"),
        }
    )
    product = ProductDoc(name=ds.type.name)
    return DatasetDoc(id=ds.id, product=product, crs=str(ds.crs), properties=properties)


def _convert_eo(ds) -> DatasetDoc:
    # Definitely need: # - 'datetime' # - 'eo:instrument' # - 'eo:platform' # - 'odc:region_code'
    properties = StacPropertyView(
        {
            "odc:region_code": ds.metadata_doc["region_code"],
            "datetime": ds.center_time,
            "eo:instrument": ds.metadata.instrument,
            "eo:platform": ds.metadata.platform,
            "landsat:landsat_scene_id": ds.metadata.instrument,  # Used to find abbreviated instrument id
        }
    )
    product = ProductDoc(name=ds.type.name)
    return DatasetDoc(id=ds.id, product=product, crs=str(ds.crs), properties=properties)


def get_transform_info(transform_name):
    """
    Given a transform return version and url info of the transform.
    """
    version = ""
    version_major_minor = ""
    url = ""
    try:
        transform_package = transform_name.split(".")[0]

        m = metadata(transform_package)
        version = m["Version"]
        version_major_minor = ".".join(version.split(".")[0:2])
        url = m.get("Home-page", "")
    except (AttributeError, PackageNotFoundError):
        _LOG.info(
            "algorithm_version not set and " "not used to generate deterministic uuid"
        )
    return {
        "version": version,
        "version_major_minor": version_major_minor,
        "url": url,
    }
