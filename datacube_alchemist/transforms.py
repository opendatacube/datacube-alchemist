import os
from typing import Dict

import numpy
import structlog
import xarray as xr
from dask.distributed import Client
from datacube import Datacube
from datacube.utils.rio import configure_s3_access
from datacube.virtual import Measurement, Transformation
from nrtmodels import (
    UnsupervisedBurnscarDetect2,
    # UnsupervisedBurnscarDetect1,
    SupervisedBurnscarDetect1,
)
from odc.algo import int_geomedian

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
            f"Geomedian will be generated over timeframe from {gm_start_date} to {gm_end_date}"
        )

        # TODO - remove this section, for debugging only. Find the S2 data for the geomedian
        dc = Datacube()
        gm_query = dc.find_datasets(
            product=["s2a_ard_granule", "s2b_ard_granule"],
            time=(str(gm_start_date), str(gm_end_date)),
            like=data.geobox,
        )
        logger.info(
            f"Found {len(gm_query)} matching datasets for geomedian computation"
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

        logger.debug(f"Geomedian Datasets: {gm_datasets}")
        logger.info("starting geomedian calculation")

        gm_data = int_geomedian(gm_datasets, num_threads=1)
        logger.debug(f"gm_data: {gm_data} data: {data}")

        # Compose the computed gm data
        # refer to https://github.com/opendatacube/datacube-wps/blob/master/datacube_wps/processes/__init__.py#L426

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
        logger.info(f"pre_nbr: {pre_nbr}")

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

        # Bare Soil Index (Rikimaru, Miyatake 2002)
        # (BSI) = ((Swir2 + red) - (nir + Blue)) / ((Swir2 + red) + (nir + Blue))
        logger.info("Starting BSI calculation")
        pre_bsi = (
            (gm_data.nbart_swir_2 + gm_data.nbart_red)
            - (gm_data.nbart_nir_1 + gm_data.nbart_blue)
        ) / (
            (gm_data.nbart_swir_2 + gm_data.nbart_red)
            + (gm_data.nbart_nir_1 + gm_data.nbart_blue)
        )
        data = xr.merge([data, {"pre_bsi": pre_bsi}])
        data["post_bsi"] = (
            (data.nbart_swir_2 + data.nbart_red) - (data.nbart_nir_1 + data.nbart_blue)
        ) / (
            (data.nbart_swir_2 + data.nbart_red) + (data.nbart_nir_1 + data.nbart_blue)
        )

        # TODO - Review NaN handling on BSI data here
        data["delta_bsi"] = data.pre_bsi - data.post_bsi
        data["delta_bsi"] = (
            data.delta_bsi.where(data.nbart_nir_1 != -999)
            .where(data.nbart_nir1 != numpy.NaN)
            .astype(numpy.single)
        )
        data["delta_bsi"] = (
            data.delta_bsi * -1
        )  # multiply by -1 to scale the same as other models

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
        data["delta_ndvi"] = data.pre_ndvi - data.post_ndvi
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

        data = data.drop_vars(
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
            product="s2_barest_earth",
            time=gm_base_year,
            like=data.geobox,
        )
        logger.info(
            f"Found {len(gm_query)} matching datasets for geomedian computation"
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

        # Filter Bands
        # Filter bad S2 BE data
        # Filter bad S2 NRT data
        filter_ard_bands = (
            "nbart_blue",
            "nbart_red",
            "nbart_nir_1",
            "nbart_swir_2",
        )

        for band in filter_ard_bands:
            data[band] = (
                data[band]
                .where(data[band] != -999, numpy.NaN)
                .where(numpy.isfinite(data[band]), numpy.NaN)
            )

        filter_gm_bands = (
            "s2be_blue",
            "s2be_red",
            "s2be_nir_1",
            "s2be_swir_2",
        )
        for band in filter_gm_bands:
            gm_data[band] = (
                gm_data[band]
                .where(gm_data[band] != -999, numpy.NaN)
                .where(numpy.isfinite(gm_data[band]), numpy.NaN)
            )

        logger.debug(f"gm_data: {gm_data} data: {data}")

        logger.debug("starting dnbr calculations\n")

        # Normalised Burn Ratio (NBR) = (B08 - B11)/(B08 + B11)
        pre_nbr = (gm_data.s2be_nir_1 - gm_data.s2be_swir_2) / (
            gm_data.s2be_nir_1 + gm_data.s2be_swir_2
        )
        logger.info(f"pre_nbr: {pre_nbr}")

        data = xr.merge([data.isel(time=0, drop=True), {"pre_nbr": pre_nbr}])
        data["post_nbr"] = (data.nbart_nir_1 - data.nbart_swir_2) / (
            data.nbart_nir_1 + data.nbart_swir_2
        )
        # Delta NBR preNBR - postNBR
        data["delta_nbr"] = data.pre_nbr - data.post_nbr
        # Filter output NBR data based on:
        # 1. contiguity layer instead of nir_1
        # 2. barest earth nodata value
        # 3. only keep finite values on output band.
        data["delta_nbr"] = data.delta_nbr.where(data.nbart_nir_1 != -999).astype(
            numpy.single
        )
        data["delta_nbr"] = data.delta_nbr.where(
            numpy.isfinite(data.delta_nbr), numpy.NaN
        ).astype(numpy.single)
        data["delta_nbr"] = data.delta_nbr.where(data.nbart_nir_1 != numpy.NaN).astype(
            numpy.single
        )
        # FMask filter:
        # Keep pixels tagged 'valid' or 'water', remove pixels tagged 'snow', 'invalid', 'cloud' and 'cloud shadow'
        # Water can have a similar signature to fire/burn, and so needs to be tested using a different water algorithm
        # at a later stage
        #
        # Ref: https://cmi.ga.gov.au/data-products/dea/404/dea-surface-reflectance-oa-landsat-8-oli-tirs#details
        fmask_filter = (data.fmask == 1) | (data.fmask == 5)
        data["delta_nbr"] = data.delta_nbr.where(fmask_filter, numpy.NaN).astype(
            numpy.single
        )

        # Bare Soil Index (Rikimaru, Miyatake 2002)
        # (BSI) = ((Swir2 + red) - (nir + Blue)) / ((Swir2 + red) + (nir + Blue))
        logger.info("Starting BSI calculation")
        pre_bsi = (
            (gm_data.s2be_swir_2 + gm_data.s2be_red)
            - (gm_data.s2be_nir_1 + gm_data.s2be_blue)
        ) / (
            (gm_data.s2be_swir_2 + gm_data.s2be_red)
            + (gm_data.s2be_nir_1 + gm_data.s2be_blue)
        )
        data = xr.merge([data, {"pre_bsi": pre_bsi}])
        data["post_bsi"] = (
            (data.nbart_swir_2 + data.nbart_red) - (data.nbart_nir_1 + data.nbart_blue)
        ) / (
            (data.nbart_swir_2 + data.nbart_red) + (data.nbart_nir_1 + data.nbart_blue)
        )
        # delta BSI preBSI - post BSI
        data["delta_bsi"] = data.pre_bsi - data.post_bsi
        # Filter output BSI data based on:
        # 1. contiguity layer instead of nir_1
        # 2. barest earth nodata value
        # 3. only keep finite values on output band.
        data["delta_bsi"] = data.delta_bsi.where(data.nbart_nir_1 != -999).astype(
            numpy.single
        )
        data["delta_bsi"] = data.delta_bsi.where(
            numpy.isfinite(data.delta_bsi), numpy.NaN
        ).astype(numpy.single)
        data["delta_bsi"] = data.delta_bsi.where(data.nbart_nir_1 != numpy.NaN).astype(
            numpy.single
        )
        data["delta_bsi"] = (
            data.delta_bsi * -1
        )  # multiply by -1 to scale the same as other models
        # FMask filter:
        data["delta_bsi"] = data.delta_bsi.where(fmask_filter, numpy.NaN).astype(
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

        # Filter NDVI output data based on:
        # 1. contiguity layer instead of nir_1
        # 2. barest earth nodata value
        # 3. only keep finite values on output band.
        data["delta_ndvi"] = data.pre_ndvi - data.post_ndvi
        data["delta_ndvi"] = data.delta_ndvi.where(data.nbart_nir_1 != -999).astype(
            numpy.single
        )
        data["delta_ndvi"] = data.delta_ndvi.where(
            numpy.isfinite(data.delta_ndvi), numpy.NaN
        ).astype(numpy.single)
        data["delta_ndvi"] = data.delta_ndvi.where(
            data.nbart_nir_1 != numpy.NaN
        ).astype(numpy.single)
        # FMask filter:
        data["delta_ndvi"] = data.delta_ndvi.where(fmask_filter, numpy.NaN).astype(
            numpy.single
        )

        logger.info("Exporting data")

        data = data.drop_vars(
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

        gm_base_year = 2018

        # TODO - remove this section, for debugging only. Find the S2 data for the geomedian
        dc = Datacube()
        gm_query = dc.find_datasets(
            product=["s2_barest_earth"],
            time=gm_base_year,
            like=data.geobox,
        )
        logger.info(f"Found {len(gm_query)} matching S2 barest earth datasets")

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

        # Filter bad data
        gm_data["s2be_blue"] = gm_data.s2be_blue.where(
            gm_data.s2be_blue != -999, numpy.NaN
        ).where(numpy.isfinite(gm_data.s2be_blue), numpy.NaN)

        gm_data["s2be_red"] = gm_data.s2be_red.where(
            gm_data.s2be_red != -999, numpy.NaN
        ).where(numpy.isfinite(gm_data.s2be_red), numpy.NaN)

        gm_data["s2be_nir_1"] = gm_data.s2be_nir_1.where(
            gm_data.s2be_nir_1 != -999, numpy.NaN
        ).where(numpy.isfinite(gm_data.s2be_nir_1), numpy.NaN)

        gm_data["s2be_swir_2"] = gm_data.s2be_swir_2.where(
            gm_data.s2be_swir_2 != -999, numpy.NaN
        ).where(numpy.isfinite(gm_data.s2be_swir_2), numpy.NaN)

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

        # Select/compute the mask array
        mask = xr.where(data.fmask == 1, 0, 1).astype(
            numpy.int8
        )  # update fmask mask if use models
        mask = mask.isel(time=0, drop=True)
        logger.debug("uniques:")
        logger.debug(numpy.unique(mask))

        # data["nbart_blue"] = data.nbart_blue.where(data.nbart_blue == -999, numpy.NaN).astype(numpy.float64)

        data["nbart_blue"] = data.nbart_blue.where(
            data.nbart_blue != -999, numpy.NaN
        ).where(numpy.isfinite(data.nbart_blue), numpy.NaN)

        data["nbart_red"] = data.nbart_red.where(
            (data.nbart_red != -999), numpy.NaN
        ).where(numpy.isfinite(data.nbart_red), numpy.NaN)

        data["nbart_nir_1"] = data.nbart_nir_1.where(
            data.nbart_nir_1 != -999, numpy.NaN
        ).where(numpy.isfinite(data.nbart_nir_1), numpy.NaN)

        data["nbart_swir_2"] = data.nbart_swir_2.where(
            data.nbart_swir_2 != -999, numpy.NaN
        ).where(numpy.isfinite(data.nbart_swir_2), numpy.NaN)

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

        gm_data = gm_data.load()
        data = data.load()

        logger.debug(data.B02.values)
        logger.debug(f"B02 min:{str(data.B02.min())}")
        logger.debug(f"B02 max:{str(data.B02.max())}")
        logger.debug(f"B04 min:{str(data.B04.min())}")
        logger.debug(f"B04 max:{str(data.B04.max())}")
        logger.debug(f"B08 min:{str(data.B08.min())}")
        logger.debug(f"B08 max:{str(data.B08.max())}")
        logger.debug(f"B11 min:{str(data.B11.min())}")
        logger.debug(f"B11 max:{str(data.B11.max())}")

        logger.debug(f"be B02 min:{str(gm_data.B02.min())}")
        logger.debug(f"be B02 max:{str(gm_data.B02.max())}")
        logger.debug(f"be B04 min:{str(gm_data.B04.min())}")
        logger.debug(f"be B04 max:{str(gm_data.B04.max())}")
        logger.debug(f"be B08 min:{str(gm_data.B08.min())}")
        logger.debug(f"be B08 max:{str(gm_data.B08.max())}")
        logger.debug(f"be B11 min:{str(gm_data.B11.min())}")
        logger.debug(f"be B11 max:{str(gm_data.B11.max())}")

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

        # NOTE: **THIS IS VERY MEMORY INTESIVE!!** ~30GB Memory required
        # model1 = UnsupervisedBurnscarDetect1()
        # result1 = model1.predict(mask, gm_data, post_data)
        # logger.debug("result 1:")
        # logger.debug(result1)
        # da1 = xr.DataArray(result1, dims=("y", "x"), name="result1")
        # logger.debug(da1)

        model3 = SupervisedBurnscarDetect1()
        result3 = model3.predict(mask, gm_data, post_data)
        logger.debug("result 3:")
        logger.debug(result3)
        da3 = xr.DataArray(result3, dims=("y", "x"), name="result3")
        logger.debug(da3)

        # model2 = UnsupervisedBurnscarDetect2()
        # result2 = model2.predict(mask, gm_data, post_data)
        # logger.debug("result 2:")
        # logger.debug(result2)
        # da2 = xr.DataArray(result2, dims=("y", "x"), name="result2")
        # logger.debug(da2)

        # convert numpy data back to xarray
        logger.debug("Converting back to xarray.")

        # Prepare the output dataset
        ds = xr.Dataset(
            data_vars={
                # "ba_unsupervised_model_1": da1,
                # "ba_unsupervised_model_2": da2,
                "ba_unsupervised_model_3": da3,
            },
            coords=data.coords,
            attrs=data.attrs,
        )

        logger.debug(ds)

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
        # 2011 was a bad year for landsat data, so we use 2013 instead.
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
