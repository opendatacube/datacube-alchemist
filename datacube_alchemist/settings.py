from typing import Optional, Mapping, Sequence, Any, Union

import attr
import cattr
from rasterio.enums import Resampling

from datacube.model import Dataset


def _convert_union_mapping(obj, typ):
    # ignore typ, check obj behaves correctly
    if isinstance(obj, str):
        return obj
    # duck-type validation for a Mapping[str, str]
    if all(isinstance(v, str) for v in obj.values()):
        return obj
    raise ValueError(f"Expected Union[str, Mapping[str, str]]; got {repr(obj)}")


cattr.register_structure_hook(Union[str, Mapping[str, str]], _convert_union_mapping)
cattr.register_structure_hook(
    Optional[Union[str, Mapping[str, str]]], _convert_union_mapping
)


def _convert_write_data_settings(settings):
    if "overview_resampling" in settings:
        strval = settings["overview_resampling"]
        settings["overview_resampling"] = Resampling[strval]
    return settings


@attr.s(auto_attribs=True)
class OutputSettings:
    location: str
    write_data_settings: Optional[Mapping[str, str]] = attr.ib(
        converter=_convert_write_data_settings
    )
    nodata: Optional[int] = None
    preview_image: Optional[Mapping[Any, Any]] = None
    preview_image_singleband: Optional[Mapping[Any, Any]] = None
    metadata: Optional[Mapping[str, str]] = None
    properties: Optional[Mapping[str, str]] = None
    reference_source_dataset: bool = attr.ib(default=True)
    write_stac: Optional[bool] = False
    inherit_geometry: bool = attr.ib(default=True)
    explorer_url: Optional[str] = None


@attr.s(auto_attribs=True)
class Specification:
    measurements: Sequence[str]
    transform: str
    transform_url: Optional[str] = ""
    product: Optional[str] = None
    products: Optional[Sequence[str]] = None
    measurement_renames: Optional[Mapping[str, str]] = None
    transform_args: Any = None
    transform_args_per_product: Mapping[str, Any] = None
    resampling: Optional[Union[str, Mapping[str, str]]] = None
    override_product_family: Optional[str] = attr.ib(default=None)
    basis: Optional[str] = attr.ib(default=None)
    aws_unsigned: Optional[bool] = True


@attr.s(auto_attribs=True)
class ProcessingSettings:
    dask_chunks: Mapping[str, int] = attr.ib(default=dict())
    dask_client: Optional[Mapping[str, Any]] = attr.ib(default=dict())


@attr.s(auto_attribs=True)
class AlchemistSettings:
    specification: Specification
    output: OutputSettings
    processing: ProcessingSettings


@attr.s(auto_attribs=True)
class AlchemistTask:
    dataset: Dataset
    settings: AlchemistSettings
