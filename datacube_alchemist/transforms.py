from typing import Dict

import numpy
from datacube import Datacube
from datacube.virtual import Measurement, Transformation
from xarray import Dataset, merge


class DeltaNBR(Transformation):
    """Return NBR"""

    def __init__(self):
        self.output_measurements = {
            "dnbr": {"name": "dnbr", "dtype": "float", "nodata": -9999, "units": ""}
        }

    def measurements(self, input_measurements) -> Dict[str, Measurement]:
        return self.output_measurements

    def compute(self, data) -> Dataset:
        base_year = data.time.dt.year.values[0] - 1
        if base_year == 2021:
            base_year = 2020
        if base_year == 2012:
            base_year = 2013

        dc = Datacube()
        gm_data = dc.load(
            product="ls8_nbart_geomedian_annual",
            time=str(base_year),
            like=data.geobox,
            measurements=["nir", "swir2"],
        )

        pre = (gm_data.nir - gm_data.swir2) / (gm_data.nir + gm_data.swir2)
        data = merge([data, {"pre": pre.isel(time=0, drop=True)}])

        data["post"] = (data.nir - data.swir2) / (data.nir + data.swir2)
        data["dnbr"] = data.pre - data.post

        data["dnbr"] = data.dnbr.where(data.nir != -999).astype(numpy.single)

        data = data.drop(["nir", "swir2", "pre", "post"])

        return data


class DeltaNBR_3band(Transformation):
    """Return 3-Band NBR"""

    def __init__(self):
        self.output_measurements = {
            "delta_nbr": {
                "name": "dnbr",
                "dtype": "float",
                "nodata": -9999,
                "units": "",
            },
            "delta_bsi": {
                "name": "bsi",
                "dtype": "float",
                "nodata": -9999,
                "units": "",
            },
            "delta_ndvi": {
                "name": "ndvi",
                "dtype": "float",
                "nodata": -9999,
                "units": "",
            },
        }

    def measurements(self, input_measurements) -> Dict[str, Measurement]:
        return self.output_measurements

    def compute(self, data) -> Dataset:

        """
        Implementation ported from https://github.com/daleroberts/nrt-predict/blob/main/nrtmodels/burnscar.py#L39
        """

        gm_base_year = data.time.dt.year.values[0] - 1
        if gm_base_year == 2021:
            gm_base_year = 2020
        if gm_base_year == 2012:
            gm_base_year = 2013

        dc = Datacube()
        gm_data = dc.load(
            product="ls8_nbart_geomedian_annual",
            time=str(gm_base_year),
            like=data.geobox,
            measurements=["blue", "red", "nir", "swir2"],  # B02, B04, B08, B11
        )

        # Delta Normalised Burn Ratio (dNBR) = (B08 - B11)/(B08 + B11)
        pre_nbr = (gm_data.nir - gm_data.swir2) / (gm_data.nir + gm_data.swir2)
        data = merge([data, {"pre_nbr": pre_nbr.isel(time=0, drop=True)}])
        data["post_nbr"] = (data.nir - data.swir2) / (data.nir + data.swir2)
        data["delta_nbr"] = data.pre_nbr - data.post_nbr
        data["delta_nbr"] = data.delta_nbr.where(data.nir != -999).astype(numpy.single)

        # Burn Scar Index (BSI) = ((B11 + B04) - (B08 - B02)) / ((B11 + B04) + (B08 - B02))
        pre_bsi = ((gm_data.swir2 + gm_data.red) - (gm_data.nir - gm_data.blue)) / (
            (gm_data.swir2 + gm_data.red) + (gm_data.nir - gm_data.blue)
        )
        data = merge([data, {"pre_bsi": pre_bsi.isel(time=0, drop=True)}])
        data["post_bsi"] = ((data.swir2 + data.red) - (data.nir - data.blue)) / (
            (data.swir2 + data.red) + (data.nir - data.blue)
        )
        data["delta_bsi"] = data.pre_bsi - data.post_bsi
        data["delta_bsi"] = data.delta_bsi.where(data.nir != -999).astype(numpy.single)

        # Normalized Difference Vegetation Index (NDVI) = (B08 - B04)/(B08 + B04)
        pre_ndvi = (gm_data.nir - gm_data.red) / (gm_data.nir + gm_data.red)
        data = merge([data, {"pre_ndvi": pre_ndvi.isel(time=0, drop=True)}])
        data["post_ndvi"] = (data.nir - data.red) / (data.nir + data.red)
        data["delta_ndvi"] = data.post_ndvi - data.pre_ndvi
        data["delta_ndvi"] = data.delta_ndvi.where(data.nir != -999).astype(
            numpy.single
        )

        data = data.drop(
            [
                "nir",
                "swir2",
                "red",
                "blue",
                "post_nbr",
                "pre_nbr",
                "pre_bsi",
                "post_bsi",
                "pre_ndvi",
                "post_ndvi",
            ]
        )

        return data
