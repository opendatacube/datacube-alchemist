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
