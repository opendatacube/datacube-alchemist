#!/usr/bin/env python3

import sys
import time
from pathlib import Path

import boto3
import click
import cloudpickle
import structlog

from datacube import Datacube
from datacube.ui import click as ui
from datacube_alchemist._dask import setup_dask_client
from datacube_alchemist.worker import Alchemist, execute_with_dask, \
    execute_task, execute_pickled_task

_LOG = structlog.get_logger()

# Define common options for all the commands
message_queue_option = click.option('--message_queue', '-M',
                                    help='Name of an AWS SQS Message Queue')

environment_option = click.option('--environment', '-E',
                                  help='Name of the Datacube environment to connect to.')


def cli_with_envvar_handling():
    cli(auto_envvar_prefix='ALCHEMIST')


@click.group(context_settings=dict(max_content_width=120))
def cli():
    """
    Transform Open Data Cube Datasets into a new type of Dataset
    """


@cli.command()
@click.option('--environment', '-E',
              help='Name of the datacube environment to connect to.')
@click.option('--limit', type=int,
              help='For testing, specify a small number of tasks to run.')
@click.argument('config_file')
@ui.parsed_search_expressions
def run_many(config_file, expressions, environment=None, limit=None):
    """
    Run Alchemist with CONFIG_FILE, on all the Datasets matching an ODC query expression
    """
    # Load Configuration file
    alchemist = Alchemist(config_file=config_file, dc_env=environment)

    tasks = alchemist.generate_tasks(expressions, limit=limit)

    client = setup_dask_client(alchemist.config)
    execute_with_dask(client, tasks)


@cli.command()
@environment_option
@click.argument('config_file')
@click.argument('input_dataset')
def run_one(config_file, input_dataset, environment=None):
    """
    Run with CONFIG_FILE on a single INPUT_DATASET

    INPUT_DATASET may be either a URL or a Dataset ID
    """
    alchemist = Alchemist(config_file=config_file, dc_env=environment)

    dc = Datacube(env=environment)
    try:
        ds = dc.index.datasets.get(input_dataset)
    except ValueError as e:
        _LOG.info("Couldn't find dataset with ID={} with exception {} trying by URL".format(
            input_dataset, e
        ))
        # Couldn't find a dataset by ID, try something
        if '://' in input_dataset:
            # Smells like a url
            input_url = input_dataset
        else:
            # Treat the input as a local file path
            input_url = Path(input_dataset).as_uri()

        ds = dc.index.datasets.get_datasets_for_location(input_url)

    # Currently this doesn't work by URL... TODO: fixme!
    task = alchemist.generate_task(ds)
    execute_task(task)


@cli.command()
@environment_option
@click.option('--limit', type=int,
              help='For testing, limit the number of tasks to create.')
@message_queue_option
@click.option('--config_file')
@ui.parsed_search_expressions
def addtoqueue(config_file, message_queue, expressions, environment=None, limit=None):
    """
    Search for Datasets and enqueue Tasks into an AWS SQS Queue for later processing.
    """

    def _push_messages(queue, messages):
        response = queue.send_messages(Entries=messages)
        return response

    _LOG.info("Start add to queue.")
    start_time = time.time()
    # Set up the queue
    sqs = boto3.resource('sqs')
    queue = sqs.get_queue_by_name(QueueName=message_queue)

    # Load Configuration file
    alchemist = Alchemist(config_file=config_file, dc_env=environment)
    tasks = alchemist.generate_tasks(expressions, limit=limit)
    messages = []
    sum_size = 0
    count = -1
    for count, task in enumerate(tasks):
        pickled_task = cloudpickle.dumps(task)
        msize = sys.getsizeof(pickled_task)
        sum_size += msize
        atts = {'pickled_task': {'BinaryValue': pickled_task, 'DataType': 'Binary'}}

        # The information is in the pickled_task message attribute
        # The message body is not used by the s/w
        body = task.dataset.uris[0] if task.dataset.uris is not None else 'location not known.'
        messages.append({'MessageBody': body, 'Id': str(count), 'MessageAttributes': atts})

        # Call can't exceed 262,144 bytes.  I'm only measuring the config file size though.
        # And I'm adding messages until it's over a limit.
        # So I am conservative.
        if sum_size > 180000:
            _ = _push_messages(queue, messages)
            _LOG.info("Pushed {} items. Total Att byte size of {}".format(count, sum_size))
            sum_size = 0
            messages = []
    # Push the final batch of messages
    if len(messages) >= 1:
        _ = _push_messages(queue, messages)
    _LOG.info("Ending. Pushed {} items in {:.2f}s.".format(count + 1, time.time() - start_time))


@cli.command()
@message_queue_option
@click.option('--sqs_timeout', '-S', type=int,
              help='The SQS message Visability Timeout.',
              default=400)
def pullfromqueue(message_queue, sqs_timeout=None):
    """
    Process a single task from an AWS SQS Queue
    """
    _LOG.info("Start pull from queue.")
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
        dataset_id, metadata_path = execute_pickled_task(pickled_task)

        # TODO: see if we can catch failed tasts that return and don't delete the message if they failed
        message.delete()
        _LOG.info("SQS message deleted")
    else:
        _LOG.warning("No messages!")


# TODO: don't repeat contents of this function in the above function
@cli.command()
@click.option('--message_queue', '-M')
@click.option('--sqs_timeout', '-S', type=int,
              help='The SQS message Visibility Timeout.',
              default=400)
def processqueue(message_queue, sqs_timeout=None):
    """
    Process all available tasks from an AWS SQS Queue
    """
    _LOG.info("Start pull from queue.")
    # Set up the queue
    sqs = boto3.resource('sqs')
    queue = sqs.get_queue_by_name(QueueName=message_queue)

    more_mesages = True
    while more_mesages:
        messages = queue.receive_messages(
            VisibilityTimeout=int(sqs_timeout),
            MaxNumberOfMessages=1,
            MessageAttributeNames=['All']
        )
        if len(messages) == 0:
            # No messages, exit successfully
            _LOG.info("No new messages, exiting successfully")
            more_mesages = False
        else:
            message = messages[0]
            pickled_task = message.message_attributes['pickled_task']['BinaryValue']
            dataset_id, metadata_path = execute_pickled_task(pickled_task)

            # TODO: see if we can catch failed tasts that return and don't delete the message if they failed

            message.delete()
            _LOG.info("SQS message deleted")


if __name__ == '__main__':
    cli_with_envvar_handling()
