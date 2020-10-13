#!/usr/bin/env python3
import json
import os
import sys
import time
from distutils.dir_util import copy_tree
from json import JSONDecodeError

import boto3
import click
import cloudpickle
import structlog
import yaml
from datacube import Datacube
from datacube.ui import click as ui

from datacube_alchemist._dask import setup_dask_client
from datacube_alchemist.upload import S3Upload
from datacube_alchemist.utils import get_config
from datacube_alchemist.worker import (
    Alchemist,
    execute_with_dask,
    execute_task,
)

_LOG = structlog.get_logger()

sqs_client = boto3.client("sqs")
s3 = boto3.resource("s3")

# Define common options for all the commands
message_queue_option = click.option("--message_queue", "-M", help="Name of an AWS SQS Message Queue")
algorithm = click.option("--algorithm", "-A", help="Algorithm, either 'fc', 'wo'")
uuid = click.option("--uuid", "-U", help="Uuid of the scene to be processed")
environment_option = click.option("--environment", "-E", help="Name of the Datacube environment to connect to.")
sqs_timeout = click.option("--sqs_timeout", "-S", type=int, help="The SQS message Visability Timeout.", default=400,)
limit_option = click.option("--limit", type=int, help="For testing, limit the number of tasks to create.")


def s3_file_exists(bucket_name, filename):
    bucket = s3.Bucket(bucket_name)
    return bool(list(bucket.objects.filter(Prefix=filename)))


def s3_upload(local_location, s3_location):
    s3ul = S3Upload(s3_location)
    s3_location = s3ul.location
    copy_tree(local_location, s3_location)


def cli_with_envvar_handling():
    cli(auto_envvar_prefix="ALCHEMIST")


@click.group(context_settings=dict(max_content_width=120))
def cli():
    """
    Transform Open Data Cube Datasets into a new type of Dataset
    """


# TODO: Does this work?
@cli.command()
@environment_option
@click.argument("config_file")
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
@click.argument("config_file")
@click.argument("input_dataset")
def run_one(config_file, input_dataset, environment=None):
    """
    Run with CONFIG_FILE on a single INPUT_DATASET

    INPUT_DATASET may be either a URL or a Dataset ID
    """
    alchemist = Alchemist(config_file=config_file, dc_env=environment)

    dc = Datacube(env=environment)
    try:
        ds = dc.index.datasets.get(input_dataset)
        task = alchemist.generate_task(ds)
        execute_task(task)
    except ValueError as e:
        _LOG.error("Couldn't find dataset with ID={} with exception {} trying by URL".format(input_dataset, e))


@cli.command()
@environment_option
@limit_option
@message_queue_option
@click.option("--config_file")
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
    sqs = boto3.resource("sqs")
    queue = sqs.get_queue_by_name(QueueName=message_queue)

    # Load Configuration file
    alchemist = Alchemist(config_file=config_file, dc_env=environment)
    tasks = alchemist.generate_tasks(expressions, limit=limit)
    messages = []
    sum_size = 0
    count = -1
    for count, task in enumerate(tasks):
        # TODO: Replace 'pickled task' with a simple JSON chunk that looks like the
        # STAC metadata, perhaps converted, perhaps not. It could just be {'id': uuid}
        pickled_task = cloudpickle.dumps(task)
        msize = sys.getsizeof(pickled_task)
        sum_size += msize
        atts = {"pickled_task": {"BinaryValue": pickled_task, "DataType": "Binary"}}

        # The information is in the pickled_task message attribute
        # The message body is not used by the s/w
        body = task.dataset.uris[0] if task.dataset.uris is not None else "location not known."
        messages.append({"MessageBody": body, "Id": str(count), "MessageAttributes": atts})

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


# Done
def process_c3(uuid, algorithm):
    """
    Accepts a filepath for the metadata and prcesses the fractional cover for that

    """
    _LOG.info(f"Received uuid --> {uuid}")
    dc = Datacube()

    try:
        dataset = dc.index.datasets.get(uuid)
        if algorithm == "fc":
            _LOG.info(f"Running FC for --> {uuid}")
            config_file = "examples/c3_config_fc.yaml"
            fc = Alchemist(config_file=config_file)
            execute_task(fc.generate_task(dataset))
        elif algorithm == "wo":
            config_file = "examples/c3_config_wo.yaml"
            wo = Alchemist(config_file=config_file)
            _LOG.info(f"Running WO for --> {uuid}")
            execute_task(wo.generate_task(dataset))
        else:
            _LOG.info(f"Invalid algorithm --> {uuid}. Algorithm must be either fc/wo")
            raise RuntimeError(f"Invalid algorithm --> {uuid}. Algorithm must be either fc/wo")

        local_location = get_config(config_file, "output.local_location")
        s3_location = get_config(config_file, "output.s3_location")
        s3_upload(local_location, s3_location)

    except yaml.YAMLError as e:
        _LOG.exception(e)


# Done
@cli.command()
@algorithm
def process_c3_from_queue(algorithm):
    """
    Process messages from the given sqs url
    Currently it processes for all the given filepaths it calculates FC & WO
    """
    _LOG.info("Start pull from queue.")
    sqs_url = os.environ.get("SQS_URL")
    while True:
        messages = sqs_client.receive_message(QueueUrl=sqs_url, MaxNumberOfMessages=1)
        if "Messages" in messages:
            # Each message contain the UUID of the scene
            # For each message process and delete the message from the queue.
            for message in messages["Messages"]:
                try:
                    uuid = json.loads(json.loads(message["Body"])["Message"])["id"]
                    _LOG.info(f"Extracted uuid {uuid}")
                    process_c3(uuid, algorithm)
                    sqs_client.delete_message(QueueUrl=sqs_url, ReceiptHandle=message["ReceiptHandle"])
                except (JSONDecodeError, TypeError, KeyError, StopIteration):
                    _LOG.exception("Error during parsing and extracting filepaths from sqs message")
                    _LOG.info(message)
        else:
            print("Queue is now empty")
            break


# Done
@cli.command()
@click.option("--from-queue", "-F", help="Url of SQS Queue to move from")
@click.option("--to-queue", "-T", help="Url of SQS Queue to move to")
def redrive_sqs(from_queue, to_queue):
    """
    Redrives all the messages from the given sqs queue to the destination,
    Ideally used in reprocessing the dead letter scenario
    """
    while True:
        messages = sqs_client.receive_message(QueueUrl=from_queue, MaxNumberOfMessages=10)
        if "Messages" in messages:
            for message in messages["Messages"]:
                print(message["Body"])
                response = sqs_client.send_message(QueueUrl=to_queue, MessageBody=message["Body"])
                if response["ResponseMetadata"]["HTTPStatusCode"] == 200:
                    sqs_client.delete_message(QueueUrl=from_queue, ReceiptHandle=message["ReceiptHandle"])
                else:
                    _LOG.info(f"Unable to send to: {message['Body']}")
        else:
            print("Queue is now empty")
            break


if __name__ == "__main__":
    cli_with_envvar_handling()
