import importlib
import json
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Iterable, Type

# TODO: replace with odc tools function when it's merged
import boto3

import cattr
import datacube
import fsspec
import numpy as np
import structlog
import yaml
from datacube.model import Dataset
from datacube.testutils.io import native_geobox, native_load
from datacube.virtual import Transformation
from eodatasets3 import serialise
from eodatasets3.assemble import DatasetAssembler
from eodatasets3.images import FileWrite
from eodatasets3.scripts.tostac import dc_to_stac, json_fallback
from eodatasets3.verify import PackageChecksum
from odc.aws import s3_url_parse
from odc.index import odc_uuid

from datacube_alchemist import __version__
from datacube_alchemist._utils import _munge_dataset_to_eo3
from datacube_alchemist.settings import AlchemistSettings, AlchemistTask

_LOG = structlog.get_logger()

cattr.register_structure_hook(np.dtype, np.dtype)


def get_queue(queue_name):
    sqs = boto3.resource("sqs")
    queue = sqs.get_queue_by_name(QueueName=queue_name)
    return queue


def publish_message(queue, msg):
    resp = queue.send_message(QueueUrl=queue.url, MessageBody=msg)

    assert (
        resp["ResponseMetadata"]["HTTPStatusCode"] == 200
    ), "Failed to publish the message"


def get_messages(queue, limit, visibility_timeout=60):
    count = 0
    while True:
        messages = queue.receive_messages(
            VisibilityTimeout=visibility_timeout,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=10,
            MessageAttributeNames=["All"],
        )

        if len(messages) == 0 or (limit and count >= limit):
            break
        else:
            for message in messages:
                count += 1
                yield message


# TODO: End bit that needs replaced


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

    @property
    def transform_name(self) -> str:
        return self.config.specification.transform

    @property
    def _transform(self) -> Type[Transformation]:

        module_name, class_name = self.transform_name.rsplit(".", maxsplit=1)
        module = importlib.import_module(name=module_name)
        imported_class = getattr(module, class_name)
        assert issubclass(imported_class, Transformation)
        return imported_class

    def _transform_with_args(self, task: AlchemistTask) -> Type[Transformation]:
        transform_args = {}
        if task.settings.specification.transform_args:
            transform_args = task.settings.specification.transform_args
        elif task.settings.specification.transform_args_per_product:
            # Get transform args per product
            transform_args = task.settings.specification.transform_args_per_product.get(
                task.dataset.type.name
            )

        return self._transform(**transform_args)

    def _find_dataset(self, uuid: str) -> Dataset:
        # Find a dataset for a given UUID from within the available
        dataset = self.dc.index.datasets.get(uuid)
        if dataset.type in self.input_products:
            return dataset
        else:
            return None

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
                if limit is not None and count > limit:
                    break

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
            "url": "",
        }

    def _write_thumbnail(
        self, task: AlchemistTask, dataset_assembler: DatasetAssembler
    ):
        if (
            task.settings.output.preview_image
            and task.settings.output.preview_image_lookuptable
        ):
            _LOG.warning(
                "preview_image and preview_imag_lookuptable options both set, defaulting to preview_image"
            )
        if task.settings.output.preview_image is not None:
            dataset_assembler.write_thumbnail(*task.settings.output.preview_image)
        elif task.settings.output.preview_image_lookuptable is not None:
            writer = FileWrite()

            measurements = dict(
                (name, (grid, path))
                for grid, name, path in dataset_assembler._measurements.iter_paths()
            )

            if task.settings.output.preview_image_lookuptable_band not in measurements:
                _LOG.error(
                    f"Can't find band {task.settings.output.preview_image_lookuptable_band} to write thumbnail with"
                )
            else:
                image_in = measurements[
                    task.settings.output.preview_image_lookuptable_band
                ][1]
                thumb_path = dataset_assembler.names.thumbnail_name(
                    dataset_assembler._work_path
                )
                thumb_out = Path(thumb_path)
                writer.create_thumbnail_singleband(
                    image_in,
                    thumb_out,
                    lookup_table=task.settings.output.preview_image_lookuptable,
                )
                dataset_assembler.add_accessory_file("thumbnail:jpg", thumb_out)

    def _write_stac(
        self,
        metadata_path: Path,
        task: AlchemistTask,
        dataset_assembler: DatasetAssembler,
    ):
        out_dataset = serialise.from_path(metadata_path)
        stac_path = Path(
            str(metadata_path).replace("odc-metadata.yaml", "stac-item.json")
        )
        stac = dc_to_stac(
            out_dataset,
            metadata_path,
            stac_path,
            stac_path.root,
            task.settings.output.explorer_url,
            False,
        )
        with stac_path.open("w") as f:
            json.dump(stac, f, default=json_fallback)
        dataset_assembler.add_accessory_file("metadata:stac", stac_path)

        # dataset_assembler._checksum.write(dataset_assembler._accessories["checksum:sha1"])
        # Need a new checksummer because EODatasets is insane
        checksummer = PackageChecksum()
        checksum_file = dataset_assembler._dataset_location / dataset_assembler._accessories["checksum:sha1"].name
        checksummer.read(checksum_file)
        checksummer.add_file(stac_path)
        checksummer.write(checksum_file)

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
            _LOG.error(f"Couldn't find dataset with UUID {uuid}")

    def generate_tasks(self, query, limit=None) -> Iterable[AlchemistTask]:
        # Find which datasets needs to be processed
        datasets = self._find_datasets(query, limit)

        tasks = (self.generate_task(ds) for ds in datasets)

        return tasks

    # Queue related functions
    def enqueue_datasets(self, queue, query, limit=None, product_limit=None):
        datasets = self._find_datasets(query, limit, product_limit)
        alive_queue = get_queue(queue)

        count = 0
        for dataset in datasets:
            message = {"id": str(dataset.id), "transform": self.transform_name}
            publish_message(alive_queue, json.dumps(message))
            count += 1

        return count

    def get_tasks_from_queue(self, queue, limit, queue_timeout):
        alive_queue = get_queue(queue)
        messages = get_messages(alive_queue, limit, visibility_timeout=queue_timeout)

        for message in messages:
            message_body = json.loads(message.body)
            if message_body["transform"] != self.config.specification.transform:
                raise ValueError(
                    "Your transform doesn't match the transform in the message."
                )
            yield self.generate_task_by_uuid(message_body["id"])

    # Task execution
    def execute_task(self, task: AlchemistTask, dryrun: bool):
        log = _LOG.bind(task=task.dataset.id)
        log.info("Task commencing", task=task)

        # Make sure our task makes sense and store it
        if task.settings.specification.transform != self.config.specification.transform:
            raise ValueError("Task transform is different to the Alchemist transform")
        transform = self._transform_with_args(task)

        # Ensure output path exists, this should be fine for file or s3 paths
        s3_destination = None
        try:
            s3_bucket, s3_path = s3_url_parse(task.settings.output.location)
            s3_destination = True
        except ValueError:
            fs_destination = Path(task.settings.output.location)

        # Load and process data in a decimated array
        if dryrun:
            geobox = native_geobox(
                task.dataset, basis=list(task.dataset.measurements.keys())[0]
            )
            res_by_ten = geobox.affine[0] * 10
            data = self.dc.load(
                product=task.dataset.type.name,
                id=task.dataset.id,
                measurements=task.settings.specification.measurements,
                output_crs=task.dataset.crs,
                resolution=(-1 * res_by_ten, res_by_ten),
            )
        else:
            data = native_load(
                task.dataset,
                measurements=task.settings.specification.measurements,
                dask_chunks=task.settings.processing.dask_chunks,
                basis=task.settings.specification.basis,
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

        naming_conventions = task.settings.output.metadata.get(
            "naming_conventions", None
        )
        if not naming_conventions:
            # Default to basic naming conventions
            naming_conventions = "default"

        temp_metadata_path = Path(tempfile.gettempdir()) / f"{task.dataset.id}.yaml"
        with DatasetAssembler(
            metadata_path=temp_metadata_path,
            naming_conventions=naming_conventions,
            dataset_id=uuid,
        ) as dataset_assembler:
            if task.settings.output.reference_source_dataset:
                source_doc = _munge_dataset_to_eo3(task.dataset)
                dataset_assembler.add_source_dataset(
                    source_doc,
                    auto_inherit_properties=True,
                    classifier=task.settings.specification.override_product_family,
                )

            # Copy in metadata and properties
            for k, v in task.settings.output.metadata.items():
                setattr(dataset_assembler, k, v)
            for k, v in task.settings.output.properties.items():
                dataset_assembler.properties[k] = v

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
                self._write_thumbnail(task, dataset_assembler)
                log.info("Wrote thumbnail")

                # Do all the deferred work from above
                dataset_id, metadata_path = dataset_assembler.done()
                log.info("Assembled dataset", metadata_path=metadata_path)

                # Write STAC, because it depends on this being .done()
                # Conveniently, this also checks that files are there!
                if task.settings.output.write_stac:
                    self._write_stac(metadata_path, task, dataset_assembler)
                    log.info("STAC file written")

                relative_path = str(dataset_assembler._dataset_location).lstrip(
                    temp_dir
                )
                if s3_destination:
                    s3_location = f"s3://{s3_bucket}/{s3_path.rstrip('/')}/{relative_path}"
                    s3_command = [
                        "aws",
                        "s3",
                        "sync",
                        "--only-show-errors",
                        str(dataset_assembler._dataset_location),
                        s3_location,
                    ]

                    if dryrun:
                        s3_command.append('--dryrun')
                        log.warning("PRETENDING to sync files to S3", s3_location=s3_destination)
                    else:
                        log.info(f"Syncing files to {s3_location}")

                    log.info("S3 command: ", command=s3_command)
                    subprocess.run(' '.join(s3_command), shell=True, check=True)
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
                        log.warning(f"NOT moving data from {temp_dir} to {dest_directory}")

                log.info("Task complete")

        return dataset_id, metadata_path
