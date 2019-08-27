from pathlib import Path

import click
import structlog

from datacube import Datacube
from datacube.ui import click as ui
from datacube_alchemist.worker import Alchemist, execute_with_dask, execute_task, AlchemistSettings

from datacube_alchemist import cloud_wrapper

_LOG = structlog.get_logger()


@click.group()
def cli():
    pass


def setup_dask_client(config: AlchemistSettings):
    from dask.distributed import Client
    client = Client(**config.processing.dask_client)
    _LOG.info('started dask', dask_client=client)
    return client


@cli.command()
@click.option('--environment', '-E',
              help='Name of the datacube environment to connect to.')
@click.option('--limit', type=int,
              help='For testing, specify a small number of tasks to run.')
@click.argument('config_file')
@ui.parsed_search_expressions
def run_many(config_file, expressions, environment=None, limit=None):
    # Load Configuration file
    alchemist = Alchemist(config_file=config_file, dc_env=environment)

    tasks = alchemist.generate_tasks(expressions, limit=limit)
    client = setup_dask_client(alchemist.config)
    execute_with_dask(client, tasks)


@cli.command()
@click.option('--environment', '-E',
              help='Name of the datacube environment to connect to.')
@click.argument('config_file')
@click.argument('input_dataset')
def run_one(config_file, input_dataset, environment=None):
    alchemist = Alchemist(config_file=config_file, dc_env=environment)

    if '://' in input_dataset:
        # Smells like a url
        input_url = input_dataset
    else:
        # Treat the input as a local file path
        input_url = Path(input_dataset).as_uri()

    dc = Datacube(env=environment)
    ds = dc.index.datasets.get_datasets_for_location(input_url)

    task = alchemist.generate_task(ds)
    execute_task(task)


@cli.command()
@click.option('--environment', '-E',
              help='Name of the datacube environment to connect to.')
@click.option('--limit', type=int,
              help='For testing, specify a small number of tasks to run.')
@click.argument('config_file')
@click.argument('message_queue')
@ui.parsed_search_expressions
def add_to_queue(config_file, message_queue, expressions, environment=None, limit=None):
    cloud_wrapper.add_to_queue(config_file, message_queue, expressions, environment, limit)


@cli.command()
@click.argument('message_queue')
@click.option('--sqs_timeout', '-s', type=int,
              help='The SQS message Visability Timeout.',
              default=400)
def pull_from_queue(message_queue, sqs_timeout=None):
    cloud_wrapper.pull_from_queue(message_queue, sqs_timeout)


if __name__ == '__main__':
    cli()
