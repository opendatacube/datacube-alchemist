#!/usr/bin/env python3
import os
import pathlib
import re
import sys
import time
from distutils.dir_util import copy_tree
from json import JSONDecodeError

import boto3
import click
import cloudpickle
import requests
import structlog
import yaml
from datacube import Datacube
from datacube.ui import click as ui

from datacube_alchemist._dask import setup_dask_client
from datacube_alchemist.upload import S3Upload
from datacube_alchemist.worker import (
    Alchemist,
    execute_with_dask,
    execute_task,
)

_LOG = structlog.get_logger()

def get_config(config_file, properties):
    """
    Receives a YAML file as config_file and returns the value of the nested lookup.
    params:
    config_file: filepath or http path of the yaml file
    properties: list of keys or string,
        - if string returns the value of the key
        - if list/tuple returns the value of the nested.
        - Returns None if there is no relevant key found.
    """
    if re.match(r"(http|https)://", config_file):
        response = requests.get(config_file)
        file_content = response.text
    else:
        p = pathlib.Path(config_file)
        if not p.is_file():
            raise RuntimeError(
                "config_file must be either a vaid http|https url or a valid filepath"
            )
        file_content = open(config_file, "r").read()

    structure = yaml.safe_load(file_content)
    _LOG.info(f"Loaded configuration {structure}")

    if type(properties) == str:
        return structure[properties]
    if type(properties) in [list, tuple]:
        for p in properties:
            structure = structure[p]  # Let it fail with KeyError if the lookup fails
        return structure

# Define common options for all the commands
# TODO: make sure all this makes sense
message_queue_option = click.option(
    "--message_queue", "-M", help="Name of an AWS SQS Message Queue"
)
algorithm = click.option("--algorithm", "-A", help="Algorithm, either 'fc', 'wo'")
uuid = click.option("--uuid", "-U", help="Uuid of the scene to be processed")
environment_option = click.option(
    "--environment", "-E", help="Name of the Datacube environment to connect to."
)
sqs_timeout = click.option(
    "--sqs_timeout",
    "-S",
    type=int,
    help="The SQS message Visability Timeout.",
    default=400,
)
limit_option = click.option(
    "--limit", type=int, help="For testing, limit the number of tasks to create."
)

def s3_file_exists(bucket_name, filename):
    s3 = boto3.resource("s3")
    bucket = s3.Bucket(bucket_name)
    return bool(list(bucket.objects.filter(Prefix=filename)))

def s3_upload(local_location, s3_location):
    # s3_location = "s3://dea-public-data-dev/derivative"  # todo remove the hardcoded paths
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

## TODO: Does this work?
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
        _LOG.error(
            "Couldn't find dataset with ID={} with exception {} trying by URL".format(
                input_dataset, e
            )
        )

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
        ## TODO: Replace 'pickled task' with a simple JSON chunk that looks like the
        ## STAC metadata, perhaps converted, perhaps not. It could just be {'id': uuid}
        pickled_task = cloudpickle.dumps(task)
        msize = sys.getsizeof(pickled_task)
        sum_size += msize
        atts = {"pickled_task": {"BinaryValue": pickled_task, "DataType": "Binary"}}

        # The information is in the pickled_task message attribute
        # The message body is not used by the s/w
        body = (
            task.dataset.uris[0]
            if task.dataset.uris is not None
            else "location not known."
        )
        messages.append(
            {"MessageBody": body, "Id": str(count), "MessageAttributes": atts}
        )

        # Call can't exceed 262,144 bytes.  I'm only measuring the config file size though.
        # And I'm adding messages until it's over a limit.
        # So I am conservative.
        if sum_size > 180000:
            _ = _push_messages(queue, messages)
            _LOG.info(
                "Pushed {} items. Total Att byte size of {}".format(count, sum_size)
            )
            sum_size = 0
            messages = []
    # Push the final batch of messages
    if len(messages) >= 1:
        _ = _push_messages(queue, messages)
    _LOG.info(
        "Ending. Pushed {} items in {:.2f}s.".format(
            count + 1, time.time() - start_time
        )
    )

def process_c3(uuid, algorithm):
    """
    Accepts a filepath for the metadata and prcesses the fractional cover for that

    """
    _LOG.info(f"Received uuid --> {uuid}")
    fc = Alchemist(config_file="examples/c3_config_fc.yaml")
    wo = Alchemist(config_file="examples/c3_config_wo.yaml")
    dc = Datacube()

    try:
        dataset = dc.index.datasets.get(uuid)
        if algorithm == "fc":
            _LOG.info(f"Running FC for --> {uuid}")
            execute_task(fc.generate_task(dataset))
        elif algorithm == "wo":
            _LOG.info(f"Running WO for --> {uuid}")
            execute_task(wo.generate_task(dataset))
        else:
            _LOG.info(f"Invalid algorithm --> {uuid}. Algorithm must be either fc/wo")

        s3_upload(local_location, s3_location)

    except yaml.YAMLError as e:
        _LOG.exception(e)

## TODO: KILL IT!
# # Helper method for one time data fix, not part of actual delivery
# def grab_uuid_from_s3_path(filepath):
#     response = s3_client.get_object(Bucket=S3_BUCKET, Key=filepath)
#     metadata = yaml.safe_load(response["Body"])
#     return metadata["id"]


## TODO: THIS SHOULD ALL BE DRIVEN BY CLI ARGUMENTS
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
        ## TODO: THIS is not clean
        if "Messages" in messages:

            # Each message contain the S3 path of the metadata file
            # For each message process and delete the message from the queue.
            for message in messages["Messages"]:
                try:
                    ## TODO: WHAT HAPPENED HERE? WE do NOT need to go to S3 to get the UUID...
                    ## This should have been implemented properly...
                    uuid = grab_uuid_from_s3_path(message["Body"])
                    # uuid = json.loads(json.loads(message["Body"])["Message"])["id"]
                    _LOG.info(f"Extracted uuid {uuid}")
                    ## TODO: THIS FUNCTION SHOULD NOT EXIST
                    process_c3(uuid, algorithm)
                    # sqs_client.delete_message(QueueUrl=sqs_url, ReceiptHandle=message["ReceiptHandle"])
                    ## TODO: pretty sure you can just do this
                    message.delete()
                except (JSONDecodeError, TypeError, KeyError, StopIteration):
                    _LOG.exception(
                        "Error during parsing and extracting filepaths from sqs message"
                    )
                    _LOG.info(message)
        else:
            print("Queue is now empty")
            break

## TODO: THIS IS NOT THE RIGHT WAY TO DRIVE THINGS
## THIS SHOULD BE DONE USING THE DATACUBE
## Something like dc.find_datasets(product='xxx')

# @cli.command()
# @click.option("--suffix", "-F", help="Suffix of the files to be iterated")
# @click.option("--prefix", "-P", help="Prefix of the files to be iterated")
# @click.option("--bucket_name", "-B", help="Name of the S3 Bucket")
# @message_queue_option
# def push_to_queue_from_s3(message_queue, bucket_name, prefix, suffix):
#     """
#     For a given S3 bucket
#     For a given prefix
#     For all the files in the S3 bucket that matches the prefix
#     Pushes a simple message to the given queuename
#     """
#     # Initialise S3 bucket
#     s3 = boto3.resource("s3")
#     bucket = s3.Bucket(bucket_name)

#     # Initialise SQS queue
#     sqs = boto3.resource("sqs")
#     queue = sqs.get_queue_by_name(QueueName=message_queue)

#     # Iterate files that matches with suffix and prefix, and push to SQS queue
#     for object in bucket.objects.filter(Prefix=prefix):
#         if not object.key.endswith(suffix):
#             continue

#         # Don't push if it's already processed
#         if s3_file_exists("derivative/ga_ls_wofs_3/" + "/".join(object.key.split("/")[2:-1])):
#             continue

#         _LOG.info(f"Sending message to queue: {object.key}")
#         queue.send_message(MessageBody=object.key)


@cli.command()
@click.option("--from-queue", "-F", help="Url of SQS Queue to move from")
@click.option("--to-queue", "-T", help="Url of SQS Queue to move to")
def redrive_sqs(from_queue, to_queue):
    """
    Redrives all the messages from the given sqs queue to the destination
    """
    while True:
        messages = sqs_client.receive_message(
            QueueUrl=from_queue, MaxNumberOfMessages=10
        )
        if "Messages" in messages:
            for message in messages["Messages"]:
                print(message["Body"])
                response = sqs_client.send_message(
                    QueueUrl=to_queue, MessageBody=message["Body"]
                )
                if response["ResponseMetadata"]["HTTPStatusCode"] == 200:
                    sqs_client.delete_message(
                        QueueUrl=from_queue, ReceiptHandle=message["ReceiptHandle"]
                    )
                else:
                    _LOG.info(f"Unable to send to: {message['Body']}")
        else:
            print("Queue is now empty")
            break

if __name__ == "__main__":
    cli_with_envvar_handling()
