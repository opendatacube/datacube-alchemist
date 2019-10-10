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


def processing_loop(sqs, sqs_queue_url, sqs_poll_time=10, job_max_time=600, max_jobs=10):

    messages_processed = 0
    more_mesages = True
    while more_mesages:
        # Check the queue for messages
        # _LOG.debug("Checking Queue, %s wait time: %s, job time: %s, max jobs per worker, %s",
        #               sqs_queue_url, sqs_poll_time, job_max_time, max_jobs)
        start_time = time.time()
        response = sqs.receive_message(
            QueueUrl=sqs_queue_url,
            WaitTimeSeconds=sqs_poll_time,
            VisibilityTimeout=job_max_time,
            MaxNumberOfMessages=max_jobs,
            MessageAttributeNames=['All'])
        print (response)
        if "Messages" not in response:
            # No messages, exit successfully
            _LOG.info("No new messages, exiting successfully")
            more_mesages = False
        else:
            for message in response.get("Messages"):
                _LOG.info("Processing message: {}".format(message.get("Body")))
                pickled_task = message['MessageAttributes']['pickled_task']['BinaryValue']
                execute_pickled_task(pickled_task)


if __name__ == '__main__':
    sqs = boto3.client('sqs')

    response = sqs.get_queue_url(QueueName=SQS_QUEUE_URL)
    queue_url = response.get('QueueUrl')

    processing_loop(sqs,
                    queue_url,
                    int(SQS_POLL_TIME_SEC),
                    int(JOB_MAX_TIME_SEC),
                    int(MAX_JOB_PER_WORKER))
