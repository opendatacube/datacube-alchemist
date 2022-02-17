#!/usr/bin/env python
import sys
import time
from subprocess import CalledProcessError

import click
import structlog
from botocore.exceptions import ClientError
from datacube.ui import click as ui
from odc.aws.queue import get_messages, get_queue

from datacube_alchemist import __version__
from datacube_alchemist._utils import _configure_logger
from datacube_alchemist.worker import Alchemist

_LOG = structlog.get_logger()

# Define common options for all the commands
queue_option = click.option(
    "--queue", "-q", help="Name of an AWS SQS Message Queue", required=True
)
uuid_option = click.option(
    "--uuid", "-u", required=True, help="UUID of the scene to be processed"
)
queue_timeout = click.option(
    "--queue-timeout",
    "-s",
    type=int,
    help="The SQS message Visibility Timeout in seconds, default is 600, or 10 minutes.",
    default=600,
)
limit_option = click.option(
    "--limit",
    "-l",
    type=int,
    help="For testing, limit the number of tasks to create or process.",
    default=None,
)
product_limit_option = click.option(
    "--product-limit",
    "-p",
    type=int,
    help="For testing, limit the number of datasets per product.",
    default=None,
)
config_file_option = click.option(
    "--config-file",
    "-c",
    required=True,
    help="The path (URI or file) to a config file to use for the job",
)
dryrun_option = click.option(
    "--dryrun",
    "--no-dryrun",
    is_flag=True,
    default=False,
    help="Don't actually do real work",
)
sns_arn_option = click.option(
    "--sns-arn",
    default=None,
    help="Publish resulting STAC document to an SNS",
)


def cli_with_envvar_handling():
    cli(auto_envvar_prefix="ALCHEMIST")


@click.group(context_settings=dict(max_content_width=120), invoke_without_command=True)
@click.option("--version", is_flag=True, default=False)
def cli(version):
    """
    Transform Datasets from the Open Data Cube into a new type of Dataset
    """
    if version:
        click.echo(__version__)

    # Set up opinionated logging
    _configure_logger()


@cli.command()
@config_file_option
@uuid_option
@dryrun_option
def run_one(config_file, uuid, dryrun):
    """
    Run with the config file for one input_dataset (by UUID)
    """
    alchemist = Alchemist(config_file=config_file)
    task = alchemist.generate_task_by_uuid(uuid)
    if task:
        alchemist.execute_task(task, dryrun)
    else:
        _LOG.error(f"Failed to generate a task for UUID {uuid}")
        sys.exit(1)


@cli.command()
@config_file_option
@ui.parsed_search_expressions
@limit_option
@dryrun_option
def run_many(config_file, expressions, limit, dryrun):
    """
    Run Alchemist with the config file on all the Datasets matching an ODC query expression
    """
    # Load Configuration file
    alchemist = Alchemist(config_file=config_file)

    tasks = alchemist.generate_tasks(expressions, limit=limit)

    executed = 0

    for task in tasks:
        alchemist.execute_task(task, dryrun)
        executed += 1

    if executed == 0:
        _LOG.error("Failed to generate any tasks")
        sys.exit(1)


@cli.command()
@config_file_option
@queue_option
@limit_option
@queue_timeout
@dryrun_option
@sns_arn_option
def run_from_queue(config_file, queue, limit, queue_timeout, dryrun, sns_arn):
    """
    Process messages from the given queue
    """

    alchemist = Alchemist(config_file=config_file)

    tasks_and_messages = alchemist.get_tasks_from_queue(queue, limit, queue_timeout)

    errors = 0
    successes = 0

    for task, message in tasks_and_messages:
        try:
            alchemist.execute_task(task, dryrun, sns_arn)
            message.delete()
            successes += 1

        # CalledProcessError from aws cli subprocess and ClientError from sns publishing
        # if these happen, we don't want to continue, because we might have access issues.
        except (CalledProcessError, ClientError):
            errors += 1
            _LOG.exception("Access denied or other AWS error, stopping execution")
            break
        # Ignore other exceptions, but log them
        except Exception as e:
            errors += 1
            _LOG.exception(
                f"Failed to run transform {alchemist.transform_name} on dataset {task.dataset.id} with error {e}"
            )

    if errors > 0:
        _LOG.error(f"There were {errors} tasks that failed to execute.")
        sys.exit(errors)
    if limit and (errors + successes) < limit:
        _LOG.warning(
            f"There were {errors} tasks that failed and {successes} successful tasks"
            ", which is less than the limit specified"
        )


@cli.command()
@config_file_option
@queue_option
@ui.parsed_search_expressions
@limit_option
@product_limit_option
@dryrun_option
def add_to_queue(config_file, queue, expressions, limit, product_limit, dryrun):
    """
    Search for Datasets and enqueue Tasks into an AWS SQS Queue for later processing.
    """

    start_time = time.time()

    alchemist = Alchemist(config_file=config_file)
    n_messages = alchemist.enqueue_datasets(
        queue, expressions, limit, product_limit, dryrun
    )

    if not dryrun:
        _LOG.info(f"Pushed {n_messages} items in {time.time() - start_time:.2f}s.")
    else:
        _LOG.info(f"DRYRUN! Would have pushed {n_messages} items.")


@cli.command()
@config_file_option
@queue_option
@dryrun_option
@click.argument("ids", nargs=-1)
def add_ids_to_queue(config_file, queue, dryrun, ids):
    """
    Add Datasets by ID to the queue.
    """
    _LOG.info(f"Adding {len(ids)} Datasets to the queue.")

    start_time = time.time()

    alchemist = Alchemist(config_file=config_file)

    datasets = alchemist.dc.index.datasets.bulk_get(ids)
    if not dryrun:
        n_messages = alchemist._datasets_to_queue(queue, datasets)
        _LOG.info(f"Pushed {n_messages} items in {time.time() - start_time:.2f}s.")
    else:
        n_messages = sum(1 for _ in datasets)
        _LOG.info(f"DRYRUN! Would have pushed {n_messages} items.")


@cli.command()
@click.option(
    "--predicate",
    help='Python predicate to filter datasets. Dataset is available as "d"',
)
@config_file_option
@queue_option
@dryrun_option
def add_missing_to_queue(config_file, queue, predicate, dryrun):
    """
    Search for datasets that don't have a target product dataset and add them to the queue

    If a predicate is supplied, datasets which do not match are filtered out.

    Example predicate:
     - 'd.metadata.gqa_iterative_mean_xy <= 1'
    """

    alchemist = Alchemist(config_file=config_file)

    datasets = alchemist.find_unprocessed_datasets(queue, dryrun)

    if predicate:
        code_obj = compile(predicate, "<string>", "eval")
        datasets = [d for d in datasets if eval(code_obj)]
        _LOG.info(f'After filtering with "{predicate}", {len(datasets)} remain.')

    if not dryrun:
        alchemist.datasets_to_queue(queue, datasets)
        _LOG.info(f"Pushed {len(datasets)} items.")
    else:
        _LOG.info(f"DRYRUN! Would have pushed {len(datasets)} alchemist tasks.")
        for dataset in datasets:
            _LOG.info(f"Transform: {alchemist.transform_name}; Dataset: {dataset}")


@cli.command()
@queue_option
@limit_option
@click.option("--to-queue", "-t", help="Url of SQS Queue to move to", required=False)
@dryrun_option
def redrive_to_queue(queue, to_queue, limit, dryrun):
    """
    Redrives all the messages from the given sqs queue to their source, or the target queue
    """

    dead_queue = get_queue(queue)
    if to_queue:
        alive_queue = get_queue(to_queue)
    else:
        count = 0
        for q in dead_queue.dead_letter_source_queues.all():
            alive_queue = q
            count += 1
            if count > 1:
                raise Exception(
                    "Deadletter queue has more than one source, please specify the target queue name."
                )
    messages = get_messages(dead_queue)

    count = 0

    count_messages = dead_queue.attributes.get("ApproximateNumberOfMessages")

    if count_messages == 0:
        _LOG.info("No messages to redrive")
        return

    _LOG.info(f"Commencing pusing messages from {dead_queue.url} to {alive_queue.url}")
    if not dryrun:
        for message in messages:
            response = alive_queue.send_message(MessageBody=message.body)
            if response["ResponseMetadata"]["HTTPStatusCode"] == 200:
                message.delete()
                count += 1
                if limit and count >= limit:
                    break
            else:
                _LOG.error(
                    f"Unable to send message {message} to queue {alive_queue.url}"
                )
        _LOG.info(f"Completed sending {count} messages to the queue {alive_queue.url}")
    else:
        _LOG.warning(
            f"DRYRUN enabled, would have pushed approx {count_messages} messages to the queue {alive_queue.url}"
        )


if __name__ == "__main__":
    cli_with_envvar_handling()
