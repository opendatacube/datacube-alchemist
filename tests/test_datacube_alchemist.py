from datacube_alchemist.worker import Alchemist
from moto import mock_sqs, mock_sns
import boto3

from datacube_alchemist._utils import _stac_to_sns

TEST_QUEUE_NAME = "alchemist-test-queue"


def test_alchemist_local_config(config_file):
    alchemist = Alchemist(config_file=config_file)

    assert alchemist.transform_name == "wofs.virtualproduct.WOfSClassifier"


def test_alchemist_resampling(config_file_resampling):
    alchemist = Alchemist(config_file=config_file_resampling)

    assert alchemist.resampling["fmask"] == "nearest"
    assert alchemist.resampling["*"] == "bilinear"


def test_alchemist_remote_config(remote_config_file):
    alchemist = Alchemist(config_file=remote_config_file)

    assert alchemist.transform_name == "wofs.virtualproduct.WOfSClassifier"


@mock_sns
def test_message_publish(stac_example):
    sns = boto3.client("sns")
    topic_name = "test-topic"
    topic_arn = sns.create_topic(Name=topic_name)["TopicArn"]

    _stac_to_sns(topic_arn, stac_example)


@mock_sqs
def test_empty_queue(run_alchemist, config_file):
    sqs = boto3.resource("sqs")
    sqs.create_queue(QueueName=TEST_QUEUE_NAME)

    result = run_alchemist(
        "run-from-queue", f"--config-file={config_file}", f"--queue={TEST_QUEUE_NAME}"
    )
    print(result)


def test_help_message(run_alchemist):
    result = run_alchemist("--help")
    print(result)

    result = run_alchemist("run-one", "--help")
    print(result)

    result = run_alchemist("run-many", "--help")
    print(result)

    result = run_alchemist("add-to-queue", "--help")
    print(result)

    result = run_alchemist("run-from-queue", "--help")
    print(result)

    result = run_alchemist("redrive-to-queue", "--help")
    print(result)
