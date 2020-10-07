from typing import Optional, Mapping, List, Sequence, Any

import attr
import numpy as np
from rasterio.enums import Resampling

from datacube.model import Dataset


def _convert_write_data_settings(settings):
    if "overview_resampling" in settings:
        strval = settings["overview_resampling"]
        settings["overview_resampling"] = Resampling[strval]
    return settings


@attr.s(auto_attribs=True)
class OutputSettings:
    location: str
    dtype: np.dtype
    nodata: int  # type depends on dtype
    write_data_settings: Optional[Mapping[str, str]] = attr.ib(converter=_convert_write_data_settings)
    preview_image: Optional[List[str]] = None
    metadata: Optional[Mapping[str, str]] = None
    properties: Optional[Mapping[str, str]] = None
    reference_source_dataset: bool = attr.ib(default=True)


@attr.s(auto_attribs=True)
class Specification:
    product: str
    measurements: Sequence[str]
    transform: str
    measurement_renames: Optional[Mapping[str, str]] = None
    transform_args: Any = None
    override_product_family: Optional[str] = attr.ib(default=None)
    basis: Optional[str] = attr.ib(default=None)


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
