import importlib
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Iterable, Type, Union, Mapping

import cattr
import datacube
import fsspec
import numpy as np
import psycopg2
import structlog
import yaml
from datacube.model import Dataset
from datacube.testutils.io import native_geobox, native_load
from datacube.virtual import Transformation
from eodatasets3.assemble import DatasetAssembler
from odc.aws import s3_url_parse
from odc.aws.queue import get_messages, get_queue
from odc.index import odc_uuid
from datacube.utils.aws import configure_s3_access

from datacube_alchemist import __version__
from datacube_alchemist._utils import (
    _munge_dataset_to_eo3,
    _stac_to_sns,
    _write_stac,
    _write_thumbnail,
)
from datacube_alchemist.settings import AlchemistSettings, AlchemistTask

_LOG = structlog.get_logger()
cattr.register_structure_hook(np.dtype, np.dtype)


class Alchemist:
    def __init__(self, *, config=None, config_file=None, dc_env=None):
        if config is not None:
            self.config = config
        else:
            with fsspec.open(config_file, mode="r") as f:
                self.config = cattr.structure(yaml.safe_load(f), AlchemistSettings)

        # Connect to the ODC Index
        self.dc = datacube.Datacube(env=dc_env)
        self.input_products = []

        if self.config.specification.product and self.config.specification.products:
            _LOG.warning(
                "Both `product` and `products` are defined, only using product."
            )

        # Store the products that we're allowing as inputs
        if self.config.specification.product:
            self.input_products.append(
                self.dc.index.products.get_by_name(self.config.specification.product)
            )
        elif self.config.specification.products:
            for product in self.config.specification.products:
                self.input_products.append(self.dc.index.products.get_by_name(product))

        # Rasterio environment activation
        configure_s3_access(
            cloud_defaults=True, aws_unsigned=self.config.specification.aws_unsigned
        )

    @property
    def transform_name(self) -> str:
        return self.config.specification.transform

    @property
    def resampling(self) -> Union[str, Mapping[str, str]]:
        return self.config.specification.resampling

    @property
    def transform(self) -> Type[Transformation]:

        module_name, class_name = self.transform_name.rsplit(".", maxsplit=1)
        module = importlib.import_module(name=module_name)
        imported_class = getattr(module, class_name)
        assert issubclass(imported_class, Transformation)
        return imported_class

    @property
    def naming_convention(self) -> str:
        return self.config.output.metadata.get("naming_conventions", "default")

    def _native_resolution(self, task: AlchemistTask) -> float:
        geobox = native_geobox(
            task.dataset, basis=list(task.dataset.measurements.keys())[0]
        )
        return geobox.affine[0]

    def _transform_with_args(self, task: AlchemistTask) -> Transformation:
        transform_args = None
        if task.settings.specification.transform_args:
            transform_args = task.settings.specification.transform_args
        elif task.settings.specification.transform_args_per_product:
            # Get transform args per product
            transform_args = task.settings.specification.transform_args_per_product.get(
                task.dataset.type.name
            )
        if transform_args is not None:
            return self.transform(**transform_args)
        else:
            return self.transform()

    def _find_dataset(self, uuid: str) -> Dataset:
        # Find a dataset for a given UUID from within the available
        dataset = self.dc.index.datasets.get(uuid)
        if dataset is not None:
            if dataset.type not in self.input_products:
                # Dataset is in the wrong product
                dataset = None
                _LOG.error(
                    f"Dataset {uuid} is not one of {', '.join(product.name for product in self.input_products)}"
                )
            if dataset.archived_time is not None:
                # Dataset is archived
                dataset = None
                _LOG.error(f"Dataset {uuid} has been archived")
        else:
            # Dataset doesn't exist
            _LOG.error(f"Couldn't find dataset {uuid}")
        return dataset

    def _find_datasets(
        self, query, limit=None, product_limit=None
    ) -> Iterable[Dataset]:
        # Find many datasets across many products with a limit
        count = 0
        if not product_limit:
            product_limit = limit

        for product in self.input_products:
            datasets = self.dc.index.datasets.search(
                limit=product_limit, product=product.name, **query
            )
            for dataset in datasets:
                yield dataset
                count += 1
                if limit is not None and count >= limit:
                    return

    def _deterministic_uuid(self, task, algorithm_version=None, **other_tags):
        if algorithm_version is None:
            transform_info = self._get_transform_info()
            algorithm_version = transform_info["version_major_minor"]
        if "dataset_version" not in other_tags:
            try:
                other_tags["dataset_version"] = task.settings.output.metadata[
                    "dataset_version"
                ]
            except KeyError:
                _LOG.info(
                    "dataset_version not set and not used to generate deterministic uuid"
                )
        uuid = odc_uuid(
            algorithm=task.settings.specification.transform,
            algorithm_version=algorithm_version,
            sources=[task.dataset.id],
            **other_tags,
        )

        uuid_values = other_tags.copy()
        uuid_values["algorithm_version"] = algorithm_version
        uuid_values["dataset.id"] = task.dataset.id
        uuid_values["algorithm"] = task.settings.specification.transform

        return uuid, uuid_values

    def _get_transform_info(self):
        """
        Given a transform return version and url info of the transform.
        :param transform:
        :return:
        """
        version = ""
        version_major_minor = ""
        try:
            base_module = importlib.import_module(self.transform_name.split(".")[0])
            version = base_module.__version__
            version_major_minor = ".".join(version.split(".")[0:2])
        except (AttributeError, ModuleNotFoundError):
            _LOG.info(
                "algorithm_version not set and "
                "not used to generate deterministic uuid"
            )
        return {
            "version": version,
            "version_major_minor": version_major_minor,
            "url": self.config.specification.transform_url,
        }

    def _datasets_to_queue(self, queue, datasets):
        alive_queue = get_queue(queue)

        def post_messages(messages, count):
            alive_queue.send_messages(Entries=messages)
            sys.stdout.write(f"\rAdded {count} messages...")
            return []

        count = 0
        messages = []
        sys.stdout.write("\rAdding messages...")
        for dataset in datasets:
            message = {
                "Id": str(count),
                "MessageBody": json.dumps(
                    {"id": str(dataset.id), "transform": self.transform_name}
                ),
            }
            messages.append(message)

            count += 1
            if count % 10 == 0:
                messages = post_messages(messages, count)

        # Post the last messages if there are any
        if len(messages) > 0:
            post_messages(messages, count)
        sys.stdout.write("\r")

        return count

    # Task related functions
    def generate_task(self, dataset) -> AlchemistTask:
        return AlchemistTask(dataset=dataset, settings=self.config)

    def generate_task_by_uuid(self, uuid: str) -> AlchemistTask:
        # Retrieve a task based on a UUID, or none if it doesn't exist for input product(s)
        dataset = self._find_dataset(uuid)
        if dataset:
            return AlchemistTask(dataset=dataset, settings=self.config)
        else:
            return None

    def generate_tasks(self, query, limit=None) -> Iterable[AlchemistTask]:
        # Find which datasets needs to be processed
        datasets = self._find_datasets(query, limit)

        tasks = (self.generate_task(ds) for ds in datasets)

        return tasks

    # Queue related functions
    def enqueue_datasets(
        self, queue, query, limit=None, product_limit=None, dryrun=False
    ):
        datasets = self._find_datasets(query, limit, product_limit)
        if not dryrun:
            return self._datasets_to_queue(queue, datasets)
        else:
            return sum(1 for _ in datasets)

    def find_fill_missing(self, queue, dryrun):
        query = """
            select d.id
            from agdc.dataset as d
            join agdc.dataset_type as t
            on d.dataset_type_ref = t.id
            left join (
                select
                    sub_s.dataset_ref,
                    sub_s.source_dataset_ref
                from agdc.dataset_source as sub_s
                join agdc.dataset as sub_d
                on sub_d.id = sub_s.dataset_ref
                join agdc.dataset_type as sub_t
                on sub_d.dataset_type_ref = sub_t.id
                where sub_t.name = %(output_product)s
            ) as s
            on d.id = s.source_dataset_ref
            where t.name in %(input_products)s
            and s.dataset_ref is null
            and d.archived is null
        """

        # Most of this guff is just to get a destination product name...
        input_products = tuple(p.name for p in self.input_products)
        output_product = ""

        dataset = self.dc.find_datasets(product=self.input_products[0].name, limit=1)
        source_doc = _munge_dataset_to_eo3(dataset[0])

        with DatasetAssembler(
            metadata_path="/fake/path",
            naming_conventions=self.naming_convention,
        ) as dataset_assembler:
            dataset_assembler.add_source_dataset(
                source_doc,
                auto_inherit_properties=True,
                inherit_geometry=self.config.output.inherit_geometry,
                classifier=self.config.specification.override_product_family,
            )
            for k, v in self.config.output.metadata.items():
                setattr(dataset_assembler, k, v)
            for k, v in self.config.output.properties.items():
                dataset_assembler.properties[k] = v
            dataset_assembler.processed = datetime.utcnow()

            output_product = dataset_assembler.names.product_name
            dataset_assembler.cancel()

        # This is actual valuable work
        _LOG.info("Querying database, please wait...")
        conn = psycopg2.connect(str(self.dc.index.url))
        cur = conn.cursor()

        query_args = dict(input_products=input_products, output_product=output_product)
        cur.execute(query, query_args)
        results = cur.fetchall()
        _LOG.info(
            (
                f"Found {len(results)} datasets from {len(self.input_products)} input products"
                f" missing in the output product {output_product}"
            )
        )

        if not dryrun:
            datasets = [self.dc.index.datasets.get(row[0]) for row in results]
            return self._datasets_to_queue(queue, datasets)
        else:
            return len(results)

    def get_tasks_from_queue(self, queue, limit, queue_timeout):
        """Retrieve messages from the named queue, returning an iterable of (AlchemistTasks, SQS Messages)"""
        alive_queue = get_queue(queue)
        messages = get_messages(alive_queue, limit, visibility_timeout=queue_timeout)

        for message in messages:
            message_body = json.loads(message.body)
            uuid = message_body.get("id", None)
            if uuid is None:
                # This is probably a message created from an SNS, so it's double
                # JSON dumped
                message_body = json.loads(message_body["Message"])
            transform = message_body.get("transform", None)

            if transform and transform != self.transform_name:
                _LOG.error(
                    f"Your transform doesn't match the transform in the message. Ignoring {uuid}"
                )
                continue
            task = self.generate_task_by_uuid(message_body["id"])
            if task:
                yield task, message

    # Task execution
    def execute_task(
        self, task: AlchemistTask, dryrun: bool = False, sns_arn: str = None
    ):
        log = _LOG.bind(task=task.dataset.id)
        log.info("Task commencing", task=task)

        # Make sure our task makes sense and store it
        if task.settings.specification.transform != self.transform_name:
            raise ValueError("Task transform is different to the Alchemist transform")
        transform = self._transform_with_args(task)

        # Ensure output path exists, this should be fine for file or s3 paths
        s3_destination = False
        try:
            s3_url_parse(task.settings.output.location)
            s3_destination = True
        except ValueError:
            fs_destination = Path(task.settings.output.location)

        # Load and process data in a decimated array
        if dryrun:
            res_by_ten = self._native_resolution(task) * 10
            data = self.dc.load(
                product=task.dataset.type.name,
                id=task.dataset.id,
                measurements=task.settings.specification.measurements,
                output_crs=task.dataset.crs,
                resolution=(-1 * res_by_ten, res_by_ten),
                resampling=task.settings.specification.resampling,
            )
        else:
            data = native_load(
                task.dataset,
                measurements=task.settings.specification.measurements,
                dask_chunks=task.settings.processing.dask_chunks,
                basis=task.settings.specification.basis,
                resampling=task.settings.specification.resampling,
            )
        data = data.rename(task.settings.specification.measurement_renames)

        log.info("Data loaded")

        output_data = transform.compute(data)
        if "time" in output_data.dims:
            output_data = output_data.squeeze("time")

        log.info("Prepared lazy transformation", output_data=output_data)

        output_data = output_data.compute()
        crs = data.attrs["crs"]

        del data
        log.info("Loaded and transformed")

        # Because"/env/lib/python3.6/site-packages/eodatasets3/images.py", line 489, in write_from_ndarray
        # raise TypeError("Datatype not supported: {dt}".format(dt=dtype))
        # TODO: investigate if this is ok
        dtypes = set(str(v.dtype) for v in output_data.data_vars.values())
        if "int8" in dtypes:
            log.info(
                "Found dtype=int8 in output data, converting to uint8 for geotiffs"
            )
            output_data = output_data.astype("uint8", copy=False)

        if "crs" not in output_data.attrs:
            output_data.attrs["crs"] = crs

        uuid, _ = self._deterministic_uuid(task)

        temp_metadata_path = Path(tempfile.gettempdir()) / f"{task.dataset.id}.yaml"
        with DatasetAssembler(
            metadata_path=temp_metadata_path,
            naming_conventions=self.naming_convention,
            dataset_id=uuid,
        ) as dataset_assembler:
            if task.settings.output.reference_source_dataset:
                source_doc = _munge_dataset_to_eo3(task.dataset)
                dataset_assembler.add_source_dataset(
                    source_doc,
                    auto_inherit_properties=True,
                    inherit_geometry=task.settings.output.inherit_geometry,
                    classifier=task.settings.specification.override_product_family,
                )

            # Copy in metadata and properties
            for k, v in task.settings.output.metadata.items():
                setattr(dataset_assembler, k, v)

            if task.settings.output.properties:
                for k, v in task.settings.output.properties.items():
                    dataset_assembler.properties[k] = v

            # Update the GSD
            dataset_assembler.properties["eo:gsd"] = self._native_resolution(task)

            dataset_assembler.processed = datetime.utcnow()

            dataset_assembler.note_software_version(
                "datacube-alchemist",
                "https://github.com/opendatacube/datacube-alchemist",
                __version__,
            )

            # Software Version of Transformer
            version_url = self._get_transform_info()
            dataset_assembler.note_software_version(
                name=task.settings.specification.transform,
                url=version_url["url"],
                version=version_url["version"],
            )

            # Write it all to a tempdir root, and then either shift or s3 sync it into place
            with tempfile.TemporaryDirectory() as temp_dir:
                # Set up a temporary directory
                dataset_assembler.collection_location = Path(temp_dir)
                # Dodgy hack!
                dataset_assembler._metadata_path = None

                # Write out the data
                dataset_assembler.write_measurements_odc_xarray(
                    output_data,
                    nodata=task.settings.output.nodata,
                    **task.settings.output.write_data_settings,
                )
                log.info("Finished writing measurements")

                # Write out the thumbnail
                _write_thumbnail(task, dataset_assembler)
                log.info("Wrote thumbnail")

                # Do all the deferred work from above
                dataset_id, metadata_path = dataset_assembler.done()
                log.info("Assembled dataset", metadata_path=metadata_path)

                # Write STAC, because it depends on this being .done()
                # Conveniently, this also checks that files are there!
                stac = None
                if task.settings.output.write_stac:
                    stac = _write_stac(metadata_path, task, dataset_assembler)
                    log.info("STAC file written")

                relative_path = dataset_assembler._dataset_location.relative_to(
                    temp_dir
                )
                if s3_destination:
                    s3_location = (
                        f"s3://{task.settings.output.location.rstrip('/')}/{relative_path}"
                    )
                    s3_command = [
                        "aws",
                        "s3",
                        "sync",
                        "--only-show-errors",
                        "--acl bucket-owner-full-control",
                        str(dataset_assembler._dataset_location),
                        s3_location,
                    ]

                    if not dryrun:
                        log.info(f"Syncing files to {s3_location}")
                    else:
                        s3_command.append("--dryrun")
                        log.warning(
                            "PRETENDING to sync files to S3", s3_location=s3_location
                        )

                    log.info("Writing files to s3", location=s3_location)
                    # log.debug("S3 command: ", command=s3_command)
                    subprocess.run(" ".join(s3_command), shell=True, check=True)
                else:
                    dest_directory = fs_destination / relative_path
                    if not dryrun:
                        log.info("Writing files to disk", location=dest_directory)
                        if dest_directory.exists():
                            shutil.rmtree(dest_directory)
                        shutil.copytree(
                            dataset_assembler._dataset_location, dest_directory
                        )
                    else:
                        log.warning(
                            f"NOT moving data from {temp_dir} to {dest_directory}"
                        )

                log.info("Task complete")
                if stac is not None and sns_arn:
                    if not dryrun:
                        _stac_to_sns(sns_arn, stac)
                elif sns_arn:
                    _LOG.error("Not posting to SNS because there's no STAC to post")

        return dataset_id, metadata_path
