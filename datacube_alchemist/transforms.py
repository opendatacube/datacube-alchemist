from typing import Dict

import numpy
import xarray as xr

# import pandas
from datacube import Datacube
from datacube.virtual import Measurement, Transformation
from nrtmodels import UnsupervisedBurnscarDetect2
from odc.algo import int_geomedian
from datacube.utils.rio import configure_s3_access
import structlog

# import datetime
import os


logger = structlog.get_logger()


class DeltaNBR(Transformation):
    """Return NBR"""

    def __init__(self):
        self.output_measurements = {
            "dnbr": {"name": "dnbr", "dtype": "float", "nodata": numpy.nan, "units": ""}
        }

    def measurements(self, input_measurements) -> Dict[str, Measurement]:
        return self.output_measurements

    def compute(self, data) -> xr.Dataset:
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
        data = xr.merge([data, {"pre": pre.isel(time=0, drop=True)}])

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

    def compute(self, data) -> xr.Dataset:

        """
        Implementation ported from https://github.com/daleroberts/nrt-predict/blob/main/nrtmodels/burnscar.py#L39
        """

        gm_base_year = data.time.dt.year.values[0] - 1
        if gm_base_year == 2021:
            gm_base_year = 2020
        # 2011 was a bad year for ladsat data, so we use 2013 instead.
        if gm_base_year == 2012:
            gm_base_year = 2013

        # Get time of input NRT image
        data_time_epoch = numpy.datetime64(data["time"].item(0), "ns")

        # Compute the relevant period for the geomedian calculation
        # GM Start date is image date minus 3 years
        #  Note that the calculation is in weeks, as delta in months/years are not constant.
        gm_start_date = data_time_epoch - numpy.timedelta64(52 * 3, "W").astype(
            "timedelta64[ns]"
        )

        # End date is start date plus 3 months
        gm_end_date = gm_start_date + numpy.timedelta64(4, "W").astype(
            "timedelta64[ns]"
        )

        logger.debug(
            "Geomedian will be generated over timeframe from "
            + str(gm_start_date)
            + " to "
            + str(gm_end_date)
        )

        # TODO - remove this section, for debugging only. Find the S2 data for the geomedian
        dc = Datacube()
        gm_query = dc.find_datasets(
            product=["s2a_ard_granule", "s2b_ard_granule"],
            time=(str(gm_start_date), str(gm_end_date)),
            like=data.geobox,
        )
        logger.info(
            "Found "
            + str(len(gm_query))
            + " matching datasets for geomedian computation"
        )

        # Find the data for geomedian calculation.
        gm_datasets = dc.load(
            product=["s2a_ard_granule", "s2b_ard_granule"],
            time=(str(gm_start_date), str(gm_end_date)),
            like=data.geobox,
            measurements=[
                "nbart_blue",
                "nbart_red",
                "nbart_nir_1",
                "nbart_swir_2",
            ],  # B02, B04, B08, B11
            dask_chunks={
                "time": -1,
                "x": 4096,
                "y": 2048,
            },
        )

        # No geomedian data, exit.
        if not gm_datasets:
            raise ValueError("No geomedian data for this location.")

        logger.debug(gm_datasets)
        logger.info("starting geomedian calculation\n")

        gm_data = int_geomedian(gm_datasets, num_threads=1)
        logger.debug("\ngm_data:")
        logger.debug(gm_data)
        logger.debug("\ndata:")
        logger.debug(data)

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
            logger.debug("starting dask operation\n")
            gm_data = gm_data.load()

        logger.debug("starting dnbr calculations\n")

        # Delta Normalised Burn Ratio (dNBR) = (B08 - B11)/(B08 + B11)
        pre_nbr = (gm_data.nbart_nir_1 - gm_data.nbart_swir_2) / (
            gm_data.nbart_nir_1 + gm_data.nbart_swir_2
        )
        logger.info(pre_nbr)

        time_dim = data.time

        data = xr.merge([data.isel(time=0, drop=True), {"pre_nbr": pre_nbr}])
        data["post_nbr"] = (data.nbart_nir_1 - data.nbart_swir_2) / (
            data.nbart_nir_1 + data.nbart_swir_2
        )

        # TODO - Review NaN handling on NBR data here
        data["delta_nbr"] = data.pre_nbr - data.post_nbr
        data["delta_nbr"] = (
            data.delta_nbr.where(data.nbart_nir_1 != -999)
            .where(data.nbart_nir1 != numpy.NaN)
            .astype(numpy.single)
        )

        # Burn Scar Index (BSI) = ((B11 + B04) - (B08 - B02)) / ((B11 + B04) + (B08 - B02))
        logger.info("Starting BSI calculation")
        pre_bsi = (
            (gm_data.nbart_swir_2 / 10000 + gm_data.nbart_red / 10000)
            - (gm_data.nbart_nir_1 / 10000 - gm_data.nbart_blue / 10000)
        ) / (
            (gm_data.nbart_swir_2 / 10000 + gm_data.nbart_red / 10000)
            + (gm_data.nbart_nir_1 / 10000 - gm_data.nbart_blue / 10000)
        )
        data = xr.merge([data, {"pre_bsi": pre_bsi}])
        data["post_bsi"] = (
            (data.nbart_swir_2 / 10000 + data.nbart_red / 10000)
            - (data.nbart_nir_1 / 10000 - data.nbart_blue / 10000)
        ) / (
            (data.nbart_swir_2 / 10000 + data.nbart_red / 10000)
            + (data.nbart_nir_1 / 10000 - data.nbart_blue / 10000)
        )

        # TODO - Review NaN handling on BSI data here
        data["delta_bsi"] = data.pre_bsi - data.post_bsi
        data["delta_bsi"] = (
            data.delta_bsi.where(data.nbart_nir_1 != -999)
            .where(data.nbart_nir1 != numpy.NaN)
            .astype(numpy.single)
        )

        # Normalized Difference Vegetation Index (NDVI) = (B08 - B04)/(B08 + B04)
        logger.info("Starting NDVI calculation")
        pre_ndvi = (gm_data.nbart_nir_1 - gm_data.nbart_red) / (
            gm_data.nbart_nir_1 + gm_data.nbart_red
        )
        data = xr.merge([data, {"pre_ndvi": pre_ndvi}])
        data["post_ndvi"] = (data.nbart_nir_1 - data.nbart_red) / (
            data.nbart_nir_1 + data.nbart_red
        )

        # TODO - Review NaN handling on NDVI data here
        data["delta_ndvi"] = data.post_ndvi - data.pre_ndvi
        data["delta_ndvi"] = (
            data.delta_ndvi.where(data.nbart_nir_1 != -999)
            .where(data.nbart_nir1 != numpy.NaN)
            .astype(numpy.single)
        )

        # Add computed geomedian data to output
        data["gm_data_nbart_nir_1"] = gm_data.nbart_nir_1
        data["gm_data_nbart_red"] = gm_data.nbart_red
        data["gm_data_nbart_blue"] = gm_data.nbart_blue
        data["gm_data_nbart_swir_2"] = gm_data.nbart_swir_2

        logger.info("Exporting data")

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
        logger.debug("Adding time dimension")
        data = data.expand_dims({"time": time_dim})

        return data


class DeltaNBR_3band_s2be(Transformation):
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

    def compute(self, data) -> xr.Dataset:

        """
        Implementation ported from https://github.com/daleroberts/nrt-predict/blob/main/nrtmodels/burnscar.py#L39
        """

        gm_base_year = 2018

        # TODO - remove this section, for debugging only. Find the S2 data for the geomedian
        dc = Datacube()
        gm_query = dc.find_datasets(
            product=["s2_barest_earth"],
            time=gm_base_year,
            like=data.geobox,
        )
        logger.info(
            "Found "
            + str(len(gm_query))
            + " matching datasets for geomedian computation"
        )

        # Find the data for geomedian calculation.
        gm_data = dc.load(
            product="s2_barest_earth",
            time=gm_base_year,
            like=data.geobox,
            measurements=[
                "s2be_blue",
                "s2be_red",
                "s2be_nir_1",
                "s2be_swir_2",
            ],  # B02, B04, B08, B11
        )

        # No geomedian data, exit.
        if not gm_data:
            raise ValueError("No geomedian data for this location.")

        logger.debug("\ngm_data:")
        logger.debug(gm_data)
        logger.debug("\ndata:")
        logger.debug(data)

        logger.debug("starting dnbr calculations\n")

        # Delta Normalised Burn Ratio (dNBR) = (B08 - B11)/(B08 + B11)
        pre_nbr = (gm_data.s2be_nir_1 - gm_data.s2be_swir_2) / (
            gm_data.s2be_nir_1 + gm_data.s2be_swir_2
        )
        logger.info(pre_nbr)

        data = xr.merge([data.isel(time=0, drop=True), {"pre_nbr": pre_nbr}])
        data["post_nbr"] = (data.nbart_nir_1 - data.nbart_swir_2) / (
            data.nbart_nir_1 + data.nbart_swir_2
        )

        # TODO - Review NaN handling on NBR data here
        data["delta_nbr"] = data.pre_nbr - data.post_nbr
        data["delta_nbr"] = data.delta_nbr.where(data.nbart_nir_1 != -999).astype(
            numpy.single
        )
        data["delta_nbr"] = data.delta_nbr.where(data.nbart_nir_1 != numpy.NaN).astype(
            numpy.single
        )

        # Burn Scar Index (BSI) = ((B11 + B04) - (B08 - B02)) / ((B11 + B04) + (B08 - B02))
        logger.info("Starting BSI calculation")
        pre_bsi = (
            (gm_data.s2be_swir_2 / 10000 + gm_data.s2be_red / 10000)
            - (gm_data.s2be_nir_1 / 10000 - gm_data.s2be_blue / 10000)
        ) / (
            (gm_data.s2be_swir_2 / 10000 + gm_data.s2be_red / 10000)
            + (gm_data.s2be_nir_1 / 10000 - gm_data.s2be_blue / 10000)
        )
        data = xr.merge([data, {"pre_bsi": pre_bsi}])
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
        data["delta_bsi"] = data.delta_bsi.where(data.nbart_nir_1 != numpy.NaN).astype(
            numpy.single
        )

        # Normalized Difference Vegetation Index (NDVI) = (B08 - B04)/(B08 + B04)
        logger.info("Starting NDVI calculation")
        pre_ndvi = (gm_data.s2be_nir_1 - gm_data.s2be_red) / (
            gm_data.s2be_nir_1 + gm_data.s2be_red
        )
        data = xr.merge([data, {"pre_ndvi": pre_ndvi}])
        data["post_ndvi"] = (data.nbart_nir_1 - data.nbart_red) / (
            data.nbart_nir_1 + data.nbart_red
        )

        # TODO - Review NaN handling on NDVI data here
        data["delta_ndvi"] = data.post_ndvi - data.pre_ndvi
        data["delta_ndvi"] = data.delta_ndvi.where(data.nbart_nir_1 != -999).astype(
            numpy.single
        )
        data["delta_ndvi"] = data.delta_ndvi.where(
            data.nbart_nir_1 != numpy.NaN
        ).astype(numpy.single)

        logger.info("Exporting data")

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

        return data


class BAUnsupervised_s2be(Transformation):
    """Return NRT Unsupervised Model using S2 barest earth dataset"""

    def __init__(self):
        self.output_measurements = {
            "ba_unsupervised": {
                "name": "dnbr",
                "dtype": "float",
                "nodata": numpy.nan,
                "units": "",
            }
        }

    def measurements(self, input_measurements) -> Dict[str, Measurement]:
        return self.output_measurements

    def compute(self, data) -> xr.Dataset:

        """
        Implementation ported from https://github.com/daleroberts/nrt-predict/blob/main/nrtmodels/burnscar.py#L39
        """

        gm_base_year = 2018

        # TODO - remove this section, for debugging only. Find the S2 data for the geomedian
        dc = Datacube()
        gm_query = dc.find_datasets(
            product=["s2_barest_earth"],
            time=gm_base_year,
            like=data.geobox,
        )
        logger.info(
            "Found " + str(len(gm_query)) + " matching S2 barest earth datasets"
        )

        # Find the data for geomedian calculation.
        gm_data = dc.load(
            product="s2_barest_earth",
            time=gm_base_year,
            like=data.geobox,
            measurements=[
                "s2be_blue",
                "s2be_red",
                "s2be_nir_1",
                "s2be_swir_2",
            ],  # B02, B04, B08, B11
            resampling="average",
            dask_chunks={"time": 1},
        )

        # No geomedian data, exit.
        if not gm_data:
            raise ValueError("No geomedian data for this location.")

        logger.debug("\ngm_data:")
        logger.debug(gm_data)
        logger.debug("\ndata:")
        logger.debug(data)

        logger.debug("starting unsupervised calculations\n")

        # Convert from xarray to numpy array

        gm_data["s2be_blue"] = gm_data.s2be_blue.where(
            gm_data.s2be_blue == -999, numpy.NaN
        )
        gm_data["s2be_red"] = gm_data.s2be_red.where(
            gm_data.s2be_red == -999, numpy.NaN
        )
        gm_data["s2be_nir_1"] = gm_data.s2be_nir_1.where(
            gm_data.s2be_nir_1 == -999, numpy.NaN
        )
        gm_data["s2be_swir_2"] = gm_data.s2be_swir_2.where(
            gm_data.s2be_swir_2 == -999, numpy.NaN
        )

        # Renaming bands to match expected band names (B02, B04, B08, B11)
        gm_data = (
            gm_data.rename(
                {
                    "s2be_blue": "B02",
                    "s2be_red": "B04",
                    "s2be_nir_1": "B08",
                    "s2be_swir_2": "B11",
                }
            ).astype(numpy.float64)
            / 10000.0
        )

        # gm_data=gm_data.where(gm_data.B02 != numpy.NaN)
        # gm_data=gm_data.where(gm_data.B02 != numpy.Infinity)
        # gm_data=gm_data.where(gm_data.B04 != numpy.NaN)
        # gm_data=gm_data.where(gm_data.B04 != numpy.Infinity)
        # gm_data=gm_data.where(gm_data.B08 != numpy.NaN)
        # gm_data=gm_data.where(gm_data.B08 != numpy.Infinity)
        # gm_data=gm_data.where(gm_data.B11 != numpy.NaN)
        # gm_data=gm_data.where(gm_data.B11 != numpy.Infinity)

        # Select/compute the mask array
        mask = xr.where(data.fmask == 1, 0, 1).astype(numpy.int8)
        mask = mask.isel(time=0, drop=True)

        # data["nbart_blue"] = data.nbart_blue.where(data.nbart_blue == -999, numpy.NaN).astype(numpy.float64)

        data["nbart_blue"] = data.nbart_blue.where(data.nbart_blue == -999, numpy.NaN)
        data["nbart_red"] = data.nbart_red.where(data.nbart_red == -999, numpy.NaN)
        data["nbart_nir_1"] = data.nbart_nir_1.where(
            data.nbart_nir_1 == -999, numpy.NaN
        )
        data["nbart_swir_2"] = data.nbart_swir_2.where(
            data.nbart_swir_2 == -999, numpy.NaN
        )

        data = (
            data.rename(
                {
                    "nbart_blue": "B02",
                    "nbart_red": "B04",
                    "nbart_nir_1": "B08",
                    "nbart_swir_2": "B11",
                }
            ).astype(numpy.float64)
            / 10000.0
        )

        # data=data.where(data.B02 != numpy.NaN)
        # data=data.where(data.B02 != numpy.Infinity)
        # data=data.where(data.B04 != numpy.NaN)
        # data=data.where(data.B04 != numpy.Infinity)
        # data=data.where(data.B08 != numpy.NaN)
        # data=data.where(data.B08 != numpy.Infinity)
        # data=data.where(data.B11 != numpy.NaN)
        # data=data.where(data.B11 != numpy.Infinity)

        gm_data = gm_data.load()
        data = data.load()

        gm_data = gm_data.isel(time=0, drop=True)
        post_data = data.isel(time=0, drop=True)

        # mask = numpy.zeros(post_data["B02"].shape, dtype=bool)

        logger.debug(post_data["B02"].shape)
        # mask = numpy.zeros(post_data["B02"].shape, dtype=bool)

        # gm_data = {
        #     "B02": gm_data["B02"].astype(numpy.float32)
        #     / 10000.0,
        #     "B04": gm_data["s2be_red"].astype(numpy.float32)
        #     / 10000.0,
        #     "B08": gm_data["s2be_nir_1"].astype(numpy.float32)
        #     / 10000.0,
        #     "B11": gm_data["s2be_swir_2"].astype(numpy.float32)
        #     / 10000.0,
        # }

        # post_data = post_data.where(post_data["nbart_blue"])

        logger.debug(mask)
        logger.debug(gm_data)
        logger.debug(post_data)

        # Invoke NRT unsupervised model calculation
        model = UnsupervisedBurnscarDetect2()
        result = model.predict(mask, gm_data, post_data)
        logger.debug("result:")
        logger.debug(result)

        # convert numpy data back to xarray
        logger.debug("Converting back to xarray.")
        da = xr.DataArray(result, dims=("y", "x"), name="result")
        # dr = xr.Dataset(data_vars={"result": da})

        logger.debug(da)

        # Prepare the output dataset
        # data = xr.merge([data, {"ba_unsupervised": da}])
        ds = xr.Dataset(
            data_vars={"ba_unsupervised": da}, coords=data.coords, attrs=data.attrs
        )

        # data = data.drop(
        #     [
        #         "B02",
        #         "B04",
        #         "B08",
        #         "B11",
        #         # "fmask",
        #     ]
        # )

        logger.debug(ds)

        # data.rename(
        #         {
        #             "B02":"nbart_blue",
        #             "B04":"nbart_red",
        #             "B08":"nbart_nir_1",
        #             "B11":"nbart_swir_2",
        #         }
        #     )

        return ds


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

    def compute(self, data) -> xr.Dataset:

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

        # Convert from xarray to numpy array
        squashed = data.to_array().transpose("y", "x", "variable", ...)
        data = squashed.data.astype(numpy.float32) / 10000.0

        gm_squashed = gm_data.to_array().transpose("y", "x", "variable", ...)
        gm_data = gm_squashed.data.astype(numpy.float32) / 10000.0

        mask = numpy.zeros(data.shape[:2], dtype=bool)

        model = UnsupervisedBurnscarDetect2()
        uyhat = model.predict(mask, gm_data, data)

        # convert back to xarray
        da = xr.DataArray(uyhat, dims=("y", "x", "variable"), name="result")
        return xr.Dataset(data_vars={"result": da})
