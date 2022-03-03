import json
from pathlib import Path
import re
from typing import Dict

import boto3
import structlog
from datacube.model import Dataset
from datacube.virtual import Measurement, Transformation
from eodatasets3 import DatasetAssembler, serialise
from eodatasets3.model import DatasetDoc, ProductDoc
from eodatasets3.properties import StacPropertyView
from eodatasets3.scripts.tostac import dc_to_stac, json_fallback
from eodatasets3.verify import PackageChecksum
from toolz.dicttoolz import get_in

from datacube_alchemist.settings import AlchemistTask


# Regex for extracting region codes from tile IDs.
RE_TILE_REGION_CODE = re.compile(r".*A\d{6}_T(\w{5})_N\d{2}\.\d{2}")


class FakeTransformation(Transformation):
    """
    Only writes input to output
    """

    def measurements(self, input_measurements) -> Dict[str, Measurement]:
        return input_measurements

    def compute(self, data) -> Dataset:
        return data


def _configure_logger():
    processors = [
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.dev.ConsoleRenderer(),
    ]

    structlog.configure(
        processors=processors,
        context_class=dict,
        cache_logger_on_first_use=True,
        logger_factory=structlog.PrintLoggerFactory(),
    )


def _write_thumbnail(task: AlchemistTask, dataset_assembler: DatasetAssembler):
    if task.settings.output.preview_image is not None:
        dataset_assembler.write_thumbnail(**task.settings.output.preview_image)
    elif task.settings.output.preview_image_singleband is not None:
        dataset_assembler.write_thumbnail_singleband(
            **task.settings.output.preview_image_singleband
        )


def _write_stac(
    metadata_path: Path,
    destination_path: str,
    explorer_url: str,
    dataset_assembler: DatasetAssembler,
):
    out_dataset = serialise.from_path(metadata_path)
    stac_path = Path(str(metadata_path).replace("odc-metadata.yaml", "stac-item.json"))

    # Make sure destination path has a / at the end. Clumsy, but necessary.
    stac = dc_to_stac(
        out_dataset,
        metadata_path,
        stac_path,
        destination_path.rstrip("/") + "/",
        explorer_url,
        False,
    )

    with stac_path.open("w") as f:
        json.dump(stac, f, default=json_fallback)
    dataset_assembler.add_accessory_file("metadata:stac", stac_path)

    checksummer = PackageChecksum()
    checksum_file = (
        Path(dataset_assembler.names.dataset_location.lstrip("file:"))
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
    link_ref = next(
        filter(lambda x: x.get("rel", "") == "self", get_in(["links"], stac, [])), {}
    ).get("href", "")

    product_name = get_in(["properties", "odc:product"], stac, None)
    if product_name is None:
        product_name = stac.get("collection", None)

    if product_name is None:
        raise ValueError("No 'odc:product_name' or 'collection' found in STAC doc")

    attributes = {
        "action": {"DataType": "String", "StringValue": "ADDED"},
        "datetime": {
            "DataType": "String",
            "StringValue": str(get_in(["properties", "datetime"], stac)),
        },
        "product": {
            "DataType": "String",
            "StringValue": product_name,
        },
        "version": {
            "DataType": "String",
            "StringValue": str(get_in(["properties", "odc:dataset_version"], stac, "")),
        },
        "path": {
            "DataType": "String",
            "StringValue": link_ref,
        },
        "bbox.ll_lon": {"DataType": "Number", "StringValue": str(bbox[0])},
        "bbox.ll_lat": {"DataType": "Number", "StringValue": str(bbox[1])},
        "bbox.ur_lon": {"DataType": "Number", "StringValue": str(bbox[2])},
        "bbox.ur_lat": {"DataType": "Number", "StringValue": str(bbox[3])},
    }

    maturity = get_in(["properties", "dea:dataset_maturity"], stac)

    if maturity is not None:
        attributes["maturity"] = {"DataType": "String", "StringValue": maturity}

    client = boto3.client("sns")
    client.publish(
        TopicArn=sns_arn,
        Message=json.dumps(stac, indent=4, default=json_fallback),
        MessageAttributes=attributes,
    )


def _munge_dataset_to_eo3(ds: Dataset) -> DatasetDoc:
    """
    Convert to the DatasetDoc format that eodatasets expects.
    """
    if ds.metadata_type.name in {"eo_plus", "eo_s2_nrt", "gqa_eo"}:
        # Handle S2 NRT metadata identically to eo_plus files.
        # gqa_eo is the S2 ARD with extra quality check fields.
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


def _guess_region_code(ds: Dataset) -> str:
    """
    Get the region code of a dataset.
    """
    try:
        # EO plus
        return ds.metadata.region_code
    except AttributeError:
        # Not EO plus
        pass

    try:
        # EO
        return ds.metadata_doc["region_code"]
    except KeyError:
        # No region code!
        pass

    # Region code not specified, so get it from the tile ID.
    # An example of such a tile ID for S2A NRT is:
    # S2A_OPER_MSI_L1C_TL_VGS1_20201114T053541_A028185_T50JPP_N02.09
    # The region code is 50JPP.
    tile_match = RE_TILE_REGION_CODE.match(ds.metadata_doc["tile_id"])
    if not tile_match:
        raise ValueError("No region code for dataset {}".format(ds.id))
    return tile_match.group(1)


def _convert_eo_plus(ds) -> DatasetDoc:
    # Definitely need: # - 'datetime' # - 'eo:instrument' # - 'eo:platform' # - 'odc:region_code'
    region_code = _guess_region_code(ds)
    properties = StacPropertyView(
        {
            "odc:region_code": region_code,
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
    region_code = _guess_region_code(ds)
    properties = StacPropertyView(
        {
            "odc:region_code": region_code,
            "datetime": ds.center_time,
            "eo:instrument": ds.metadata.instrument,
            "eo:platform": ds.metadata.platform,
            "landsat:landsat_scene_id": ds.metadata.instrument,  # Used to find abbreviated instrument id
        }
    )
    product = ProductDoc(name=ds.type.name)
    return DatasetDoc(id=ds.id, product=product, crs=str(ds.crs), properties=properties)
