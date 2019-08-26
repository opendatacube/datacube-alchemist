"""


"""
import boto3
import cloudpickle

from datacube_alchemist.worker import Alchemist

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
