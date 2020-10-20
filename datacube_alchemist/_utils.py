from eodatasets3.model import DatasetDoc, ProductDoc
from eodatasets3.properties import StacPropertyView
from datacube.model import Dataset

from typing import Dict

from datacube.virtual import Transformation, Measurement


class FakeTransformation(Transformation):
    """
    Only writes input to output
    """

    def measurements(self, input_measurements) -> Dict[str, Measurement]:
        return input_measurements

    def compute(self, data) -> Dataset:
        return data


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
        id=ds.id, product=product, crs=ds.crs.crs_str, properties=properties
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
    return DatasetDoc(
        id=ds.id, product=product, crs=ds.crs.crs_str, properties=properties
    )


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
    return DatasetDoc(
        id=ds.id, product=product, crs=ds.crs.crs_str, properties=properties
    )
