import json
from pathlib import Path
from typing import Dict

from datacube.model import Dataset
from datacube.virtual import Measurement, Transformation
from eodatasets3 import DatasetAssembler, serialise
from eodatasets3.model import DatasetDoc, ProductDoc
from eodatasets3.properties import StacPropertyView
from eodatasets3.scripts.tostac import dc_to_stac, json_fallback
from eodatasets3.verify import PackageChecksum

from datacube_alchemist.settings import AlchemistTask


class FakeTransformation(Transformation):
    """
    Only writes input to output
    """

    def measurements(self, input_measurements) -> Dict[str, Measurement]:
        return input_measurements

    def compute(self, data) -> Dataset:
        return data


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
    stac = dc_to_stac(
        out_dataset,
        metadata_path,
        stac_path,
        stac_path.root,
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
