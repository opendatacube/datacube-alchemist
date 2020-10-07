"""


"""

import importlib
import sys
# pylint: disable=map-builtin-not-iterating
from datetime import datetime
from pathlib import Path
from typing import Iterable, Type

import cattr
import cloudpickle
import fsspec
import numpy as np
import structlog
import yaml

import datacube
from datacube.model import Dataset
from datacube.testutils.io import native_load
from datacube.virtual import Transformation
from datacube_alchemist import __version__
from datacube_alchemist.settings import AlchemistSettings, AlchemistTask
from datacube_alchemist.upload import S3Upload
from eodatasets3.assemble import DatasetAssembler
from eodatasets3.model import DatasetDoc, ProductDoc
from eodatasets3.properties import StacPropertyView
from odc.index import odc_uuid
from ._dask import dask_compute_stream

_LOG = structlog.get_logger()

cattr.register_structure_hook(np.dtype, np.dtype)


class Alchemist:
    def __init__(self, *, config=None, config_file=None, dc_env=None):
        if config is not None:
            self.config = config
        else:
            with fsspec.open(config_file, mode='r') as f:
                self.config = cattr.structure(yaml.safe_load(f), AlchemistSettings)

        # Connect to the ODC Index
        self.dc = datacube.Datacube(env=dc_env)
        self.input_product = self.dc.index.products.get_by_name(self.config.specification.product)

    def generate_tasks(self, query, limit=None) -> Iterable[AlchemistTask]:
        # Find which datasets needs to be processed
        datasets = self.dc.index.datasets.search(limit=limit, product=self.config.specification.product,
                                                 **query)

        tasks = (self.generate_task(ds) for ds in datasets)

        return tasks

    def generate_task(self, dataset) -> AlchemistTask:
        return AlchemistTask(dataset=dataset,
                             settings=self.config)


def execute_with_dask(client, tasks: Iterable[AlchemistTask]):
    # Execute the tasks across the dask cluster
    completed = dask_compute_stream(client,
                                    execute_task,
                                    tasks)
    _LOG.info('processing task stream')
    for result in completed:
        try:
            print(result)
        except Exception as e:
            print(e)
            print(sys.exc_info()[0])
        pass
    _LOG.info('completed')


def execute_task(task: AlchemistTask):
    log = _LOG.bind(task=task)
    transform = _import_transform(task.settings.specification.transform)
    transform = transform(**task.settings.specification.transform_args)

    # Load and process data
    data = native_load(task.dataset, measurements=task.settings.specification.measurements,
                       dask_chunks=task.settings.processing.dask_chunks,
                       basis=task.settings.specification.basis)
    data = data.rename(task.settings.specification.measurement_renames)

    log.info('data loaded')

    output_data = transform.compute(data)
    if 'time' in output_data.dims:
        output_data = output_data.squeeze('time')

    log.info('prepared lazy transformation', output_data=output_data)

    output_data = output_data.compute()
    crs = data.attrs['crs']

    del data
    log.info('loaded and transformed')

    dtypes = set(str(v.dtype) for v in output_data.data_vars.values())
    if 'int8' in dtypes:
        log.info('Found dtype=int8 in output data, converting to uint8 for geotiffs')
        output_data = output_data.astype('uint8', copy=False)

    if 'crs' not in output_data.attrs:
        output_data.attrs['crs'] = crs

    # Ensure output path exists
    output_location = Path(task.settings.output.location)
    output_location.mkdir(parents=True, exist_ok=True)
    uuid, _ = deterministic_uuid(task)
    if task.settings.output.metadata.get("naming_conventions", "") == "dea_c3":
        name = "dea_c3"
    elif task.dataset.metadata.platform.lower().startswith("sentinel"):
        name = "dea_s2"
    else:
        name = "dea"
    with DatasetAssembler(output_location, naming_conventions=name,
                          dataset_id=uuid) as p:
        if task.settings.output.reference_source_dataset:
            source_doc = _munge_dataset_to_eo3(task.dataset)
            p.add_source_dataset(source_doc, auto_inherit_properties=True,
                                 classifier=task.settings.specification.override_product_family)

        # Copy in metadata and properties
        for k, v in task.settings.output.metadata.items():
            setattr(p, k, v)
        for k, v in task.settings.output.properties.items():
            p.properties[k] = v

        p.processed = datetime.utcnow()

        p.note_software_version(
            'datacube-alchemist',
            "https://github.com/opendatacube/datacube-alchemist",
            __version__
        )

        # Software Version of Transformer
        version_url = get_transform_info(task.settings.specification.transform)
        p.note_software_version(name=task.settings.specification.transform, url=version_url['url'],
                                version=version_url['version'])

        # TODO Note configuration settings of this Task
        # p.extend_user_metadata()

        # TODO Check whether output already exists

        p.write_measurements_odc_xarray(
            output_data,
            nodata=task.settings.output.nodata,
            **task.settings.output.write_data_settings
        )

        if task.settings.output.preview_image is not None:
            p.write_thumbnail(*task.settings.output.preview_image)
        dataset_id, metadata_path = p.done()

    return dataset_id, metadata_path


def _munge_dataset_to_eo3(ds: Dataset) -> DatasetDoc:
    """
    Convert to the DatasetDoc format that eodatasets expects.
    """
    if ds.metadata_type.name == 'eo_plus':
        return convert_eo_plus(ds)

    if ds.metadata_type.name == 'eo':
        return convert_eo(ds)

    # Else we have an already mostly eo3 style dataset
    product = ProductDoc(name=ds.type.name)
    # Wrap properties to avoid typos and the like
    properties = StacPropertyView(ds.metadata_doc.get('properties', {}))
    return DatasetDoc(
        id=ds.id,
        product=product,
        crs=ds.crs.crs_str,
        properties=properties
    )


def convert_eo_plus(ds) -> DatasetDoc:
    # Definitely need: # - 'datetime' # - 'eo:instrument' # - 'eo:platform' # - 'odc:region_code'
    properties = StacPropertyView({
        'odc:region_code': ds.metadata.region_code,
        'datetime': ds.center_time,
        'eo:instrument': ds.metadata.instrument,
        'eo:platform': ds.metadata.platform,
        'landsat:landsat_scene_id': ds.metadata_doc.get('tile_id', '??'),  # Used to find abbreviated instrument id
        'sentinel:sentinel_tile_id': ds.metadata_doc.get('tile_id', '??'),
    })
    product = ProductDoc(name=ds.type.name)
    return DatasetDoc(
        id=ds.id,
        product=product,
        crs=ds.crs.crs_str,
        properties=properties
    )


def convert_eo(ds) -> DatasetDoc:
    # Definitely need: # - 'datetime' # - 'eo:instrument' # - 'eo:platform' # - 'odc:region_code'
    properties = StacPropertyView({
        'odc:region_code': ds.metadata_doc['region_code'],
        'datetime': ds.center_time,
        'eo:instrument': ds.metadata.instrument,
        'eo:platform': ds.metadata.platform,
        'landsat:landsat_scene_id': ds.metadata.instrument,  # Used to find abbreviated instrument id
    })
    product = ProductDoc(name=ds.type.name)
    return DatasetDoc(
        id=ds.id,
        product=product,
        crs=ds.crs.crs_str,
        properties=properties
    )


def _import_transform(transform_name: str) -> Type[Transformation]:
    module_name, class_name = transform_name.rsplit('.', maxsplit=1)
    module = importlib.import_module(name=module_name)
    imported_class = getattr(module, class_name)
    assert issubclass(imported_class, Transformation)
    return imported_class


def execute_pickled_task(pickled_task):
    task = cloudpickle.loads(pickled_task)
    s3ul = S3Upload(task.settings.output.location)
    # make location local if the location is S3
    task.settings.output.location = s3ul.location
    _LOG.info("Found task to process: {}".format(task))
    execute_task(task)
    s3ul.upload_if_needed()


def deterministic_uuid(task, algorithm_version=None, **other_tags):
    if algorithm_version is None:
        transform_info = get_transform_info(task.settings.specification.transform)
        algorithm_version = transform_info['version_major_minor']
    if 'dataset_version' not in other_tags:
        try:
            other_tags['dataset_version'] = task.settings.output.metadata['dataset_version']
        except KeyError:
            _LOG.info('dataset_version not set and '
                      'not used to generate deterministic uuid')
    uuid = odc_uuid(algorithm=task.settings.specification.transform,
                    algorithm_version=algorithm_version,
                    sources=[task.dataset.id], **other_tags)

    uuid_values = other_tags.copy()
    uuid_values['algorithm_version'] = algorithm_version
    uuid_values['dataset.id'] = task.dataset.id
    uuid_values['algorithm'] = task.settings.specification.transform

    return uuid, uuid_values


def get_transform_info(transform):
    """
    Given a transform return version and url info of the transform.
    :param transform:
    :return:
    """
    version = ''
    version_major_minor = ''
    try:
        base_module = importlib.import_module(transform.split('.')[0])
        version = base_module.__version__
        version_major_minor = '.'.join(version.split('.')[0:2])
    except (AttributeError, ModuleNotFoundError):
        _LOG.info('algorithm_version not set and '
                  'not used to generate deterministic uuid')
    return {
        'version': version,
        'version_major_minor': version_major_minor,
        'url': ''
    }
