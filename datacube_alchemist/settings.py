from collections.abc import Mapping, Sequence
from typing import Any

import attr
import cattr
from datacube.model import Dataset
from rasterio.enums import Resampling


def _convert_union_mapping(obj, typ):
    # ignore typ, check obj behaves correctly
    if isinstance(obj, str):
        return obj
    # duck-type validation for a Mapping[str, str]
    if all(isinstance(v, str) for v in obj.values()):
        return obj
    raise ValueError(f"Expected Union[str, Mapping[str, str]]; got {obj!r}")


cattr.register_structure_hook(str | Mapping[str, str], _convert_union_mapping)
cattr.register_structure_hook(str | Mapping[str, str] | None, _convert_union_mapping)


def _convert_write_data_settings(settings):
    if "overview_resampling" in settings:
        strval = settings["overview_resampling"]
        settings["overview_resampling"] = Resampling[strval]
    return settings


@attr.s(auto_attribs=True)
class OutputSettings:
    location: str
    write_data_settings: Mapping[str, str] | None = attr.ib(
        converter=_convert_write_data_settings
    )
    nodata: int | None = None
    preview_image: Mapping[Any, Any] | None = None
    preview_image_singleband: Mapping[Any, Any] | None = None
    metadata: Mapping[str, str] | None = None
    properties: Mapping[str, str] | None = None
    reference_source_dataset: bool = attr.ib(default=True)
    write_stac: bool | None = False
    inherit_geometry: bool = attr.ib(default=True)
    explorer_url: str | None = None


@attr.s(auto_attribs=True)
class Specification:
    measurements: Sequence[str]
    transform: str
    transform_url: str | None = ""
    product: str | None = None
    products: Sequence[str] | None = None
    measurement_renames: Mapping[str, str] | None = None
    transform_args: Any = None
    transform_args_per_product: Mapping[str, Any] = None
    resampling: str | Mapping[str, str] | None = None
    override_product_family: str | None = attr.ib(default=None)
    basis: str | None = attr.ib(default=None)
    aws_unsigned: bool | None = True


@attr.s(auto_attribs=True)
class ProcessingSettings:
    dask_chunks: Mapping[str, int] = attr.ib(default={})
    dask_client: Mapping[str, Any] | None = attr.ib(default={})


@attr.s(auto_attribs=True)
class AlchemistSettings:
    specification: Specification
    output: OutputSettings
    processing: ProcessingSettings


@attr.s(auto_attribs=True)
class AlchemistTask:
    dataset: Dataset
    settings: AlchemistSettings
