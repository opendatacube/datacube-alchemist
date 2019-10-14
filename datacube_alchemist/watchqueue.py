#!/usr/bin/env python3

import logging
import os
import time
import boto3
import structlog

from datacube_alchemist.worker import execute_pickled_task

_LOG = structlog.get_logger()

SQS_QUEUE_URL = os.getenv('SQS_QUEUE_URL', 'alchemist-standard')
SQS_MESSAGE_PREFIX = os.getenv('SQS_MESSAGE_PREFIX', '')
SQS_POLL_TIME_SEC = os.getenv('SQS_POLL_TIME_SEC', '10')
JOB_MAX_TIME_SEC = os.getenv('JOB_MAX_TIME_SEC', '20')
MAX_JOB_PER_WORKER = os.getenv('MAX_JOB_PER_WORKER', '5')

def delete_message(sqs, queue_url, message):
    """
    deletes a message from the queue to ensure it isn't processed again

    :param boto3.client sqs: an initialised boto sqs client
    :param str queue_url: the sqs queue we're deleting from
    :param str queue_url: the sqs queue we're deleting from
    """
    sqs.delete_message(
        QueueUrl=queue_url,
        ReceiptHandle=message["ReceiptHandle"])
    _LOG.debug("Deleted Message %s", message.get("MessageId"))


def processing_loop(message_queue, sqs_timeout=600):
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
            execute_pickled_task(pickled_task)

            message.delete()
            _LOG.info("SQS message deleted")


if __name__ == '__main__':
    sqs = boto3.client('sqs')

    response = sqs.get_queue_url(QueueName=SQS_QUEUE_URL)
    queue_url = response.get('QueueUrl')

    processing_loop(sqs,
                    queue_url,
                    int(SQS_POLL_TIME_SEC),
                    int(JOB_MAX_TIME_SEC),
                    int(MAX_JOB_PER_WORKER))
