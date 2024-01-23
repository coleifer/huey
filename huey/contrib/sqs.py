import base64
import datetime

import boto3
from botocore.exceptions import ClientError

from huey.api import Huey
from huey.exceptions import HueyException
from huey.storage import BaseStorage
from huey.storage import EmptyData
from huey.utils import utcnow


"""
EXPERIMENTAL storage layer for SQS and S3.

* Does not support priorities.
* Does not support at-least-once delivery.
* Limited support for scheduled/delayed execution (max 900 seconds).
* May rack up a lot of API calls?

Usage:

huey = SqsHuey(
    name='huey',
    queue_name='huey_queue',
    bucket_name='huey.queue.results',
    sqs_settings={'MaximumMessageSize': '262144'},
    s3_settings={'CreateBucketConfiguration': {
        'LocationConstraint': 'us-west-1'}})

"""


class SqsStorage(BaseStorage):
    blocking = True
    priority = False

    def __init__(self, name, queue_name=None, bucket_name=None,
                 sqs_settings=None, s3_settings=None, result_expire_days=30):
        super(SqsStorage, self).__init__(name)
        self.queue_name = queue_name or ('huey.%s' % queue_name)
        self.queue_settings = sqs_settings or {}
        self._sqs = boto3.resource('sqs')
        self._queue = None

        self.bucket_name = bucket_name or ('huey.%s' % bucket_name)
        self.bucket_settings = s3_settings or {}
        self._s3 = boto3.resource('s3')
        self._bucket = None
        self.result_expire_days = result_expire_days

    @property
    def queue(self):
        if self._queue is None:
            try:
                self._queue = self._sqs.get_queue_by_name(
                    QueueName=self.queue_name)
            except ClientError:
                self._queue = self._sqs.create_queue(
                    QueueName=self.queue_name,
                    Attributes=self.queue_settings)
        return self._queue

    @property
    def bucket(self):
        if self._bucket is None:
            bucket = self._s3.Bucket(self.bucket_name)
            if not bucket.creation_date:
                bucket = self._s3.create_bucket(
                    Bucket=self.bucket_name,
                    **self.bucket_settings)
            self._bucket = bucket
        return self._bucket

    def enqueue(self, data, priority=None):
        self.queue.send_message(
            MessageBody=base64.b64encode(data).decode('ascii'))

    def dequeue(self):
        try:
            messages = self.queue.receive_messages(
                MaxNumberOfMessages=1,
                WaitTimeSeconds=20)
            if messages:
                message, = messages
                data = base64.b64decode(message.body)
                message.delete()
                return data
        except ClientError:
            pass

    def flush_queue(self):
        self.queue.purge()

    def add_to_schedule(self, data, ts, utc):
        if utc:
            now = utcnow()
        else:
            now = datetime.datetime.now()
        delay_seconds = max(0, (ts - now).total_seconds())
        if delay_seconds > 900:
            raise HueyException('SQS does not support delays of greater than '
                                '900 seconds.')
        self.queue.send_message(
            MessageBody=base64.b64encode(data).encode('ascii'),
            DelaySeconds=int(delay_seconds))

    def read_schedule(self, ts):
        return []

    def put_data(self, key, value, is_result=False):
        expires = utcnow() + datetime.timedelta(days=self.result_expire_days)
        self.bucket.put_object(
            Body=value,
            Expires=expires,
            Key=key)

    def peek_data(self, key):
        obj = self.bucket.Object(key=key)
        try:
            resp = obj.get()
        except ClientError:
            return EmptyData
        else:
            return resp['Body'].read()

    def pop_data(self, key):
        obj = self.bucket.Object(key=key)
        try:
            resp = obj.get()
        except ClientError:
            return EmptyData
        else:
            data = resp['Body'].read()
            obj.delete()
            return data

    def delete_data(self, key):
        obj = self.bucket.Object(key=key)
        try:
            obj.delete()
        except ClientError:
            return False
        else:
            return True

    def has_data_for_key(self, key):
        client = self.s3.meta.client
        try:
            client.head_object(Bucket=self.bucket.name, Key=key)
        except ClientError:
            return False
        else:
            return True

    def put_if_empty(self, key, value):
        client = self.s3.meta.client
        try:
            client.head_object(Bucket=self.bucket.name, Key=key)
        except ClientError:
            client.put_object(Body=value, Bucket=self.bucket.name, Key=key)
            return True
        else:
            return False

    def flush_results(self):
        self.bucket.objects.delete()

    def flush_all(self):
        self.flush_queue()
        self.flush_results()


class SqsHuey(Huey):
    storage_class = SqsStorage
