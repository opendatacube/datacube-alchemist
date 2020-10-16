#!/usr/bin/env python3

import time

from odc.aws.queue import get_messages

import boto3
import click
import structlog
from datacube import Datacube
from datacube.ui import click as ui

from datacube_alchemist.worker import (
    Alchemist,
    execute_task,
)

_LOG = structlog.get_logger()

# Define common options for all the commands
queue_option = click.option(
    "--queue", "-q", help="Name of an AWS SQS Message Queue"
)
uuid_option = click.option("--uuid", "-u", help="UUID of the scene to be processed")
sqs_timeout = click.option(
    "--sqs_timeout",
    "-s",
    type=int,
    help="The SQS message Visability Timeout, default is 10 minutes.",
    default=600,
)
limit_option = click.option(
    "--limit", type=int, help="For testing, limit the number of tasks to create."
)
config_file_option = click.option(
    "--config", '-c',
    help="The path (URI or file) to a config file to use for the job"
)


def cli_with_envvar_handling():
    cli(auto_envvar_prefix="ALCHEMIST")


@click.group(context_settings=dict(max_content_width=120))
def cli():
    """
    Transform Datasets from the Open Data Cube into a new type of Dataset for the Open Data Cube
    """


@cli.command()
@config_file_option
@ui.parsed_search_expressions
@limit_option
def run_many(config_file, expressions, limit=None):
    """
    Run Alchemist with the config file on all the Datasets matching an ODC query expression
    """
    # Load Configuration file
    alchemist = Alchemist(config_file=config_file)

    tasks = alchemist.generate_tasks(expressions, limit=limit)

    for task in tasks:
        execute_task(task)


@cli.command()
@config_file_option
@uuid_option
def run_one(config_file, input_dataset):
    """
    Run with the config file for one input_dataset (by UUID)
    """
    alchemist = Alchemist(config_file=config_file)

    dc = Datacube()
    try:
        ds = dc.index.datasets.get(input_dataset)
        task = alchemist.generate_task(ds)
        execute_task(task)
    except ValueError as e:
        _LOG.error(f"Couldn't find dataset with ID={input_dataset} with exception{e}")


@cli.command()
@config_file_option
@queue_option
@ui.parsed_search_expressions
@limit_option
def addtoqueue(config_file, queue, expressions, limit=None):
    """
    Search for Datasets and enqueue Tasks into an AWS SQS Queue for later processing.
    """

    def _push_messages(queue, messages):
        response = queue.send_messages(Entries=messages)
        return response

    _LOG.info("Start add to queue.")
    start_time = time.time()

    # Connect to the queue
    sqs = boto3.resource("sqs")
    queue = sqs.get_queue_by_name(QueueName=queue)

    # TODO: consider doing QA checke before pushing tasks
    dc = Datacube()

    dataset_products = {}
    for product in config_file.products:
        product_datasets = dc.index.datasets.search(limit=limit, product=product, **expressions)
        # TODO: Make sure we can concatenate
        dataset_products[product] = product_datasets

    messages = []
    count = 0

    for product, datasets in dataset_products.items():
        for dataset in datasets:
            count += 1
            # TODO: Make sure attributes are formatted properly
            atts = {"pickled_task": {"product": product}}

            body = {
                "id": dataset.id
            }
            messages.append(
                {"MessageBody": body, "Id": str(count), "MessageAttributes": atts}
            )

    # Push the final batch of messages
    if len(messages) >= 1:
        _ = _push_messages(queue, messages)
    _LOG.info(f"Pushed {len(messages)} items in {time.time() - start_time:.2f}s.")


@cli.command()
@config_file_option
@queue_option
def process_from_queue(config_file, queue):
    """
    Process messages from the given sqs url
    Currently it processes for all the given filepaths it calculates FC & WO
    """
    _LOG.info("Start pull from queue.")
    messages = get_messages()

    for message in messages:
        try:
            print("do the thing")
        except Exception as e:
            print(f"Failed to do the thing with exception {e}")


@cli.command()
@click.option("--from-queue", "-F", help="Url of SQS Queue to move from")
@click.option("--to-queue", "-T", help="Url of SQS Queue to move to")
def redrive_sqs(from_queue, to_queue):
    """
    Redrives all the messages from the given sqs queue to the destination
    """

    dead_queue = 'some-queue'
    alive_queue = "some-queue"

    messages = get_messages(dead_queue)

    for message in messages:
        response = alive_queue.send_message(
                QueueUrl=to_queue, MessageBody=message["Body"]
            )
        if response["ResponseMetadata"]["HTTPStatusCode"] == 200:
            message.delete()
        else:
            _LOG.info(f"Unable to send to: {message['Body']}")


if __name__ == "__main__":
    cli_with_envvar_handling()
