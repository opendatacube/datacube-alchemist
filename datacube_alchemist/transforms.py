from typing import Dict

import numpy
from datacube import Datacube
from datacube.virtual import Measurement, Transformation
from xarray import Dataset, merge
from nrtmodels import UnsupervisedBurnscarDetect2
from odc.algo import int_geomedian
from datacube.utils.rio import configure_s3_access
import os


class DeltaNBR(Transformation):
    """Return NBR"""

    def __init__(self):
        self.output_measurements = {
            "dnbr": {"name": "dnbr", "dtype": "float", "nodata": numpy.nan, "units": ""}
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

        pre = (gm_data.nbart_nir_1 - gm_data.nbart_swir_2) / (
            gm_data.nbart_nir_1 + gm_data.nbart_swir_2
        )
        data = merge([data, {"pre": pre.isel(time=0, drop=True)}])

        data["post"] = (data.nbart_nir_1 - data.nbart_swir_2) / (
            data.nbart_nir_1 + data.nbart_swir_2
        )
        data["dnbr"] = data.pre - data.post

        data["dnbr"] = data.dnbr.where(data.nbart_nir_1 != -999).astype(numpy.single)

        data = data.drop(["nir", "swir2", "pre", "post"])

        return data


class DeltaNBR_3band(Transformation):
    """Return 3-Band NBR"""

    def __init__(self):
        self.output_measurements = {
            "delta_nbr": {
                "name": "dnbr",
                "dtype": "float",
                "nodata": numpy.nan,
                "units": "",
            },
            "delta_bsi": {
                "name": "bsi",
                "dtype": "float",
                "nodata": numpy.nan,
                "units": "",
            },
            "delta_ndvi": {
                "name": "ndvi",
                "dtype": "float",
                "nodata": numpy.nan,
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
        # 2011 was a bad year for ladsat data, so we use 2013 instead.
        if gm_base_year == 2012:
            gm_base_year = 2013

        # Find the S2 data for the geomedian
        dc = Datacube()
        gm_datasets = dc.load(
            product=["s2a_ard_granule", "s2b_ard_granule"],
            # products=[ "s2a_ard_granule" , "s2b_ard_granule" ],
            # TODO - Compute the relevant 3 month period for the geomedian (eg. 2018-01 to 2018-03)
            time=("2018-07-01", "2018-07-02"),
            # time=("2018-07-01"),
            like=data.geobox,
            measurements=[
                "nbart_blue",
                "nbart_red",
                "nbart_nir_1",
                "nbart_swir_2",
            ],  # B02, B04, B08, B11
            dask_chunks={
                "time": -1,
                "x": 4096,  # TODO - Avoid rechunk cost by using source resolution? i.e. 10980x10980
                "y": 2048,
            },
        )

        # No geomedian data, continue?
        if not gm_datasets:
            # print(list(data.sizes.values()))
            # data["delta_nbr"] = numpy.zeros(data.sizes, dtype=float)
            # data = data.drop(
            #     [
            #     "nir",
            #     "swir2",
            #     "red",
            #     "blue",
            #     ]
            # )
            raise ValueError("No geomedian data for this location.")

        # TODO - log number of datasets from datacube query??
        print(gm_datasets)
        print("starting geomedian calculation\n")

        gm_data = int_geomedian(gm_datasets, num_threads=1)
        print("\ngm_data:")
        print(gm_data)
        print("\ndata:")
        print(data)

        # Compose the computed gm data
        # refer to https://github.com/opendatacube/datacube-wps/blob/master/datacube_wps/processes/__init__.py#L426
        from dask.distributed import Client

        with Client(
            n_workers=8, processes=True, threads_per_worker=1, memory_limit="24GB"
        ) as client:
            # TODO
            configure_s3_access(
                aws_unsigned=True,
                region_name=os.getenv("AWS_DEFAULT_REGION", "auto"),
                client=client,
            )
            print("starting dask operation\n")
            gm_data = gm_data.load()

        print("starting dnbr calculations\n")

        # Delta Normalised Burn Ratio (dNBR) = (B08 - B11)/(B08 + B11)
        pre_nbr = (gm_data.nbart_nir_1 - gm_data.nbart_swir_2) / (
            gm_data.nbart_nir_1 + gm_data.nbart_swir_2
        )
        print(pre_nbr)

        time_dim = data.time

        data = merge([data.isel(time=0, drop=True), {"pre_nbr": pre_nbr}])
        data["post_nbr"] = (data.nbart_nir_1 - data.nbart_swir_2) / (
            data.nbart_nir_1 + data.nbart_swir_2
        )

        # TODO - Review NaN handling on NBR data here
        data["delta_nbr"] = data.pre_nbr - data.post_nbr
        data["delta_nbr"] = data.delta_nbr.where(data.nbart_nir_1 != -999).astype(
            numpy.single
        )

        # Burn Scar Index (BSI) = ((B11 + B04) - (B08 - B02)) / ((B11 + B04) + (B08 - B02))
        print("Starting BSI calculation")
        pre_bsi = (
            (gm_data.nbart_swir_2 / 10000 + gm_data.nbart_red / 10000)
            - (gm_data.nbart_nir_1 / 10000 - gm_data.nbart_blue / 10000)
        ) / (
            (gm_data.nbart_swir_2 / 10000 + gm_data.nbart_red / 10000)
            + (gm_data.nbart_nir_1 / 10000 - gm_data.nbart_blue / 10000)
        )
        data = merge([data, {"pre_bsi": pre_bsi}])
        data["post_bsi"] = (
            (data.nbart_swir_2 / 10000 + data.nbart_red / 10000)
            - (data.nbart_nir_1 / 10000 - data.nbart_blue / 10000)
        ) / (
            (data.nbart_swir_2 / 10000 + data.nbart_red / 10000)
            + (data.nbart_nir_1 / 10000 - data.nbart_blue / 10000)
        )

        # TODO - Review NaN handling on BSI data here
        data["delta_bsi"] = data.pre_bsi - data.post_bsi
        data["delta_bsi"] = data.delta_bsi.where(data.nbart_nir_1 != -999).astype(
            numpy.single
        )

        # Normalized Difference Vegetation Index (NDVI) = (B08 - B04)/(B08 + B04)
        print("Starting NDVI calculation")
        pre_ndvi = (gm_data.nbart_nir_1 - gm_data.nbart_red) / (
            gm_data.nbart_nir_1 + gm_data.nbart_red
        )
        data = merge([data, {"pre_ndvi": pre_ndvi}])
        data["post_ndvi"] = (data.nbart_nir_1 - data.nbart_red) / (
            data.nbart_nir_1 + data.nbart_red
        )

        # TODO - Review NaN handling on NDVI data here
        data["delta_ndvi"] = data.post_ndvi - data.pre_ndvi
        data["delta_ndvi"] = data.delta_ndvi.where(data.nbart_nir_1 != -999).astype(
            numpy.single
        )

        # Add computed geomedian data to output
        data["gm_data_nbart_nir_1"] = gm_data.nbart_nir_1
        data["gm_data_nbart_red"] = gm_data.nbart_red
        data["gm_data_nbart_blue"] = gm_data.nbart_blue
        data["gm_data_nbart_swir_2"] = gm_data.nbart_swir_2

        print("Exporting data")

        data = data.drop(
            [
                "nbart_nir_1",
                "nbart_swir_2",
                "nbart_red",
                "nbart_blue",
                "post_nbr",
                "pre_nbr",
                "pre_bsi",
                "post_bsi",
                "pre_ndvi",
                "post_ndvi",
            ]
        )

        # add time dimension back to "data"
        print("Adding time dimension")
        data = data.expand_dims({"time": time_dim})

        return data


class S2_Geomedian(Transformation):
    """Return S2 geomedian"""

    def __init__(self):
        self.output_measurements = {
            # TODO
        }

        def measurements(self, input_measurements) -> Dict[str, Measurement]:
            return self.output_measurements

        def compute(self, data) -> Dataset:
            # TODO
            return data


class DeltaNBR_3band_s2gm(Transformation):
    """Return 3-Band NBR"""

    def __init__(self):
        self.output_measurements = {
            "delta_nbr": {
                "name": "dnbr",
                "dtype": "float",
                "nodata": numpy.nan,
                "units": "",
            },
            "delta_bsi": {
                "name": "bsi",
                "dtype": "float",
                "nodata": numpy.nan,
                "units": "",
            },
            "delta_ndvi": {
                "name": "ndvi",
                "dtype": "float",
                "nodata": numpy.nan,
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
        # 2011 was a bad year for ladsat data, so we use 2013 instead.
        if gm_base_year == 2012:
            gm_base_year = 2013

        dc = Datacube()
        gm_data = dc.load(
            product="ls8_nbart_geomedian_annual",
            time=str(gm_base_year),
            like=data.geobox,
            measurements=["blue", "red", "nir", "swir2"],  # B02, B04, B08, B11
        )

        # No geomedian data, continue?
        if not gm_data:
            # print(list(data.sizes.values()))
            # data["delta_nbr"] = numpy.zeros(data.sizes, dtype=float)
            # data = data.drop(
            #     [
            #     "nir",
            #     "swir2",
            #     "red",
            #     "blue",
            #     ]
            # )
            raise ValueError("No geomedian data for this location.")

        # Delta Normalised Burn Ratio (dNBR) = (B08 - B11)/(B08 + B11)
        pre_nbr = (gm_data.nbart_nir_1 - gm_data.nbart_swir_2) / (
            gm_data.nbart_nir_1 + gm_data.nbart_swir_2
        )
        data = merge([data, {"pre_nbr": pre_nbr.isel(time=0, drop=True)}])
        data["post_nbr"] = (data.nbart_nir_1 - data.nbart_swir_2) / (
            data.nbart_nir_1 + data.nbart_swir_2
        )
        data["delta_nbr"] = data.pre_nbr - data.post_nbr
        data["delta_nbr"] = data.delta_nbr.where(data.nbart_nir_1 != -999).astype(
            numpy.single
        )

        # Burn Scar Index (BSI) = ((B11 + B04) - (B08 - B02)) / ((B11 + B04) + (B08 - B02))
        pre_bsi = (
            (gm_data.nbart_swir_2 / 10000 + gm_data.nbart_red / 10000)
            - (gm_data.nbart_nir_1 / 10000 - gm_data.nbart_blue / 10000)
        ) / (
            (gm_data.nbart_swir_2 / 10000 + gm_data.nbart_red / 10000)
            + (gm_data.nbart_nir_1 / 10000 - gm_data.nbart_blue / 10000)
        )
        data = merge([data, {"pre_bsi": pre_bsi.isel(time=0, drop=True)}])
        data["post_bsi"] = (
            (data.nbart_swir_2 / 10000 + data.nbart_red / 10000)
            - (data.nbart_nir_1 / 10000 - data.nbart_blue / 10000)
        ) / (
            (data.nbart_swir_2 / 10000 + data.nbart_red / 10000)
            + (data.nbart_nir_1 / 10000 - data.nbart_blue / 10000)
        )
        data["delta_bsi"] = data.pre_bsi - data.post_bsi
        data["delta_bsi"] = data.delta_bsi.where(data.nbart_nir_1 != -999).astype(
            numpy.single
        )

        # Normalized Difference Vegetation Index (NDVI) = (B08 - B04)/(B08 + B04)
        pre_ndvi = (gm_data.nbart_nir_1 - gm_data.nbart_red) / (
            gm_data.nbart_nir_1 + gm_data.nbart_red
        )
        data = merge([data, {"pre_ndvi": pre_ndvi.isel(time=0, drop=True)}])
        data["post_ndvi"] = (data.nbart_nir_1 - data.nbart_red) / (
            data.nbart_nir_1 + data.nbart_red
        )
        data["delta_ndvi"] = data.post_ndvi - data.pre_ndvi
        data["delta_ndvi"] = data.delta_ndvi.where(data.nbart_nir_1 != -999).astype(
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


class BurntArea_Unsupervised(Transformation):
    """Return 1-band Unsupervised Burnt Area"""

    def __init__(self):
        self.output_measurements = {
            "burnt_area": {
                "name": "burnt_area",
                "dtype": "float",
                "nodata": numpy.nan,
                "units": "",
            }
        }

    def measurements(self, input_measurements) -> Dict[str, Measurement]:
        return self.output_measurements

    def compute(self, data) -> Dataset:

        # Load base Geomedian from datacube
        gm_base_year = data.time.dt.year.values[0] - 1
        if gm_base_year == 2021:
            gm_base_year = 2020
        # 2011 was a bad year for ladsat data, so we use 2013 instead.
        if gm_base_year == 2012:
            gm_base_year = 2013

        dc = Datacube()
        gm_data = dc.load(
            product="ls8_nbart_geomedian_annual",
            time=str(gm_base_year),
            like=data.geobox,
            measurements=["blue", "red", "nir", "swir2"],  # B02, B04, B08, B11
        )

        # Insert empty bands for compatibility with NRT lib
        gm_data.merge

        # Convert from xarray to numpy array
        squashed = data.to_array().transpose("y", "x", "variable", ...)
        data = squashed.data.astype(numpy.float32) / 10000.0

        gm_squashed = gm_data.to_array().transpose("y", "x", "variable", ...)
        gm_data = gm_squashed.data.astype(numpy.float32) / 10000.0

        mask = numpy.zeros(data.shape[:2], dtype=bool)

        model = UnsupervisedBurnscarDetect2()
        uyhat = model.predict(mask, gm_data, data)

        # convert back to xarray
        da = uyhat.DataArray(uyhat, dims=("y", "x", "variable"), name="result")
        return Dataset(data_vars={"result": da})
