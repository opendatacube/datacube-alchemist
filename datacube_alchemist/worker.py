import importlib
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping, Type, Union

import cattr
import fsspec
import numpy as np
import psycopg2
import structlog
import yaml

import datacube
from datacube.model import Dataset
from datacube.testutils.io import native_geobox, native_load
from datacube.utils.aws import configure_s3_access
from datacube.virtual import Transformation
from datacube_alchemist import __version__
from datacube_alchemist._utils import (
    _munge_dataset_to_eo3,
    _stac_to_sns,
    _write_stac,
    _write_thumbnail,
)
from datacube_alchemist.settings import AlchemistSettings, AlchemistTask
from eodatasets3.assemble import DatasetAssembler
from odc.apps.dc_tools._docs import odc_uuid
from odc.apps.dc_tools._stac import stac_transform
from odc.aws import s3_url_parse
from odc.aws.queue import get_messages, get_queue

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
        products = self.input_products
        if not product_limit:
            product_limit = limit

        # Allow specifying a single product out of multiple input products
        query_product = query.get("product", None)
        if query_product is not None:
            query.pop("product")

            if query_product not in [p.name for p in self.input_products]:
                raise ValueError(
                    f"Query included product {query_product} but this is not in input_products"
                )
            for p in self.input_products:
                if p.name == query_product:
                    products = [p]
                    break

        for product in products:
            datasets = self.dc.index.datasets.search(
                limit=product_limit, product=product.name, **query
            )

            try:
                for dataset in datasets:
                    yield dataset
                    count += 1
                    if limit is not None and count >= limit:
                        return
            except ValueError as e:
                _LOG.warning(
                    f"Error searching for datasets, maybe it returned no datasets. Error was {e}"
                )
                continue

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

    def datasets_to_queue(self, queue, datasets):
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
            return self.datasets_to_queue(queue, datasets)
        else:
            return sum(1 for _ in datasets)

    def find_unprocessed_datasets(self, queue, dryrun):
        """
        Find any datasets
        """
        query = """
            select source_dataset.id
            from agdc.dataset as source_dataset
            join agdc.dataset_type as source_product
            on source_dataset.dataset_type_ref = source_product.id
            left join (
                select
                    lineage.dataset_ref,
                    lineage.source_dataset_ref
                from agdc.dataset_source as lineage
                join agdc.dataset as source_dataset
                on source_dataset.id = lineage.dataset_ref
                join agdc.dataset_type as output_product
                on source_dataset.dataset_type_ref = output_product.id
                where output_product.name = %(output_product)s
            ) as lineage
            on source_dataset.id = lineage.source_dataset_ref
            where source_product.name in %(input_products)s
            and lineage.dataset_ref is null
            and source_dataset.archived is null
        """

        input_products = tuple(p.name for p in self.input_products)
        output_product = self._determine_output_product()

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

        datasets = [self.dc.index.datasets.get(row[0]) for row in results]
        return datasets

    def _determine_output_product(self):
        # Most of this guff is just to get a destination product name...
        output_product = ""
        dataset = self.dc.find_datasets(product=self.input_products[0].name, limit=1)
        source_doc = _munge_dataset_to_eo3(dataset[0])
        with DatasetAssembler(
            metadata_path=Path("/tmp/fake"),
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
            # add dataset maturity property from original dataset rather than output config
            if "dea:dataset_maturity" in source_doc.properties:
                dataset_assembler.properties[
                    "dea:dataset_maturity"
                ] = source_doc.properties["dea:dataset_maturity"]
            if self.config.output.properties:
                for k, v in self.config.output.properties.items():
                    dataset_assembler.properties[k] = v
            dataset_assembler.processed = datetime.utcnow()

            output_product = dataset_assembler.names.product_name
            dataset_assembler.cancel()
        return output_product

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

            try:
                # First try the simple case that the JSON object has an ODC ID
                task = self.generate_task_by_uuid(message_body["id"])
            except ValueError:
                # If that fails, try doing a standard STAC transform and getting an ID from that
                _LOG.info("Couldn't find dataset by UUID, trying another way")
                message_transformed = stac_transform(message_body)
                task = self.generate_task_by_uuid(message_transformed["id"])
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
            pass

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

        # Write it all to a tempdir root, and then either shift or s3 sync it into place
        with tempfile.TemporaryDirectory() as temp_dir:
            with DatasetAssembler(
                collection_location=Path(temp_dir),
                naming_conventions=self.naming_convention,
                dataset_id=uuid,
            ) as dataset_assembler:
                #
                # Organise metadata
                #
                if task.settings.output.reference_source_dataset:
                    source_doc = _munge_dataset_to_eo3(task.dataset)
                    dataset_assembler.add_source_dataset(
                        source_doc,
                        auto_inherit_properties=True,
                        inherit_geometry=task.settings.output.inherit_geometry,
                        classifier=task.settings.specification.override_product_family,
                    )
                    # also extract dataset maturity
                    if "dea:dataset_maturity" in source_doc.properties:
                        dataset_assembler.properties[
                            "dea:dataset_maturity"
                        ] = source_doc.properties["dea:dataset_maturity"]

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

                #
                # Write out the data and ancillaries
                #
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

                #
                # Organise paths for final output information
                #
                relative_path = dataset_assembler.names.dataset_folder
                dataset_location = Path(temp_dir) / relative_path
                destination_path = (
                    f"{task.settings.output.location.rstrip('/')}/{relative_path}"
                )

                # Write STAC, because it depends on this being .done()
                # Conveniently, this also checks that files are there!
                stac = None
                if task.settings.output.write_stac:
                    stac = _write_stac(
                        metadata_path,
                        destination_path,
                        task.settings.output.explorer_url,
                        dataset_assembler,
                    )
                    log.info("STAC file written")

                if s3_destination:
                    s3_command = [
                        "aws",
                        "s3",
                        "sync",
                        "--only-show-errors",
                        "--acl bucket-owner-full-control",
                        str(dataset_location),
                        destination_path,
                    ]

                    if not dryrun:
                        log.info(f"Syncing files to {destination_path}")
                    else:
                        s3_command.append("--dryrun")
                        log.warning(
                            "DRYRUN: pretending to sync files to S3",
                            destination_path=destination_path,
                        )

                    log.info("Writing files to s3", location=destination_path)
                    subprocess.run(" ".join(s3_command), shell=True, check=True)
                else:
                    destination_path = Path(destination_path)
                    if not dryrun:
                        log.info("Writing files to disk", location=destination_path)
                        # This should perhaps be couched in a warning as it delete important files
                        if destination_path.exists():
                            shutil.rmtree(destination_path)
                        shutil.copytree(dataset_location, destination_path)
                    else:
                        log.warning(
                            f"DRYRUN: not moving data from {dataset_location} to {destination_path}"
                        )

                log.info("Task complete")
                if stac is not None and sns_arn:
                    if not dryrun:
                        _stac_to_sns(sns_arn, stac)
                elif sns_arn:
                    _LOG.error("Not posting to SNS because there's no STAC to post")

        return dataset_id, metadata_path
