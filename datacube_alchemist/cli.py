from pathlib import Path

import click
import structlog
import boto3
import cloudpickle

from datacube import Datacube
from datacube.ui import click as ui
from datacube_alchemist.worker import Alchemist, execute_with_dask, execute_task, AlchemistSettings

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

    # Set up the queue
    sqs = boto3.resource('sqs')
    queue = sqs.get_queue_by_name(QueueName=message_queue)

    # Load Configuration file
    alchemist = Alchemist(config_file=config_file, dc_env=environment)

    tasks = alchemist.generate_tasks(expressions, limit=limit)
    for task in tasks:
        pickled_task = cloudpickle.dumps(task)
        atts = {'pickled_task': {'BinaryValue': pickled_task, 'DataType': 'Binary'}}
        # The information is in the pickled_task message attribute
        # The message body is not used by the s/w
        body = task.dataset.local_uri if task.dataset.local_uri is not None else 'local_uri is None'
        queue.send_message(MessageBody=body,  MessageAttributes=atts)


@cli.command()
@click.argument('message_queue')
@click.option('--sqs_timeout', '-s', type=int,
              help='The SQS message Visability Timeout.',
              default=1000)
def pull_from_queue(message_queue, sqs_timeout=None):
    # Set up the queue
    sqs = boto3.resource('sqs')
    queue = sqs.get_queue_by_name(QueueName=message_queue)

    messages = queue.receive_messages(
        VisibilityTimeout=sqs_timeout,
        MaxNumberOfMessages=1,
        MessageAttributeNames=['All']
    )
    if len(messages) > 0:
        message = messages[0]
        pickled_task = message.message_attributes['pickled_task']['BinaryValue']
        task = cloudpickle.loads(pickled_task)
        _LOG.info("Found task to process: {}".format(task))
        execute_task(task)

        message.delete()
        _LOG.info("SQS message deleted")
    else:
        _LOG.warning("No messages!")


if __name__ == '__main__':
    cli()
