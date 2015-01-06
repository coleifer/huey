# -*- coding: utf-8 -*-
__author__ = 'deathowl'

import datetime
import re
import time
import pika
from pika.exceptions import AMQPConnectionError

from huey.backends.base import BaseEventEmitter
from huey.backends.base import BaseQueue


def clean_name(name):
    return re.sub('[^a-z0-9]', '', name)


class RabbitQueue(BaseQueue):
    """
    A simple Queue that uses the rabbit to store messages
    """
    def __init__(self, name, **connection):
        """
        connection = {
            'host': 'localhost',
            'port': 5672,
            'username': 'guest',
            'password': 'guest',
            'vhost': '/',
            'ssl': False
        }
        """
        super(RabbitQueue, self).__init__(name, **connection)

        self.queue_name = 'huey.rabbit.%s' % clean_name(name)
        credentials = pika.PlainCredentials(
            connection.get('username', 'guest'),
            connection.get('password', 'guest'))
        connection_params = pika.ConnectionParameters(
            host=connection.get('host', 'localhost'),
            port=connection.get('port', 5672),
            credentials=credentials,
            virtual_host=connection.get('vhost', '/'),
            ssl=connection.get('ssl', False))

        self.conn = pika.BlockingConnection(connection_params)
        self.channel = self.conn.channel()
        self.channel.queue_declare(self.queue_name, durable=True)

    def write(self, data):
        self.channel.basic_publish(
            exchange='',
            routing_key=self.queue_name,
            body=data)

    def read(self):
        return self.get_data_from_queue(self.queue_name)

    def remove(self, data):
        # This is not something you usually do in rabbit, this is the only
        # operation, which is not atomic, but this "hack" should do the trick.
        amount = 0
        idx = 0
        qlen = len(self)

        for method_frame, _, body in self.channel.consume(self.queue_name):
            idx += 1
            if body == data:
                self.channel.basic_ack(method_frame.delivery_tag)
                amount += 1
            else:
                self.channel.basic_nack(
                    method_frame.delivery_tag,
                    requeue=True)

            if idx >= qlen:
                break

        self.channel.cancel()
        return amount

    def flush(self):
        self.channel.queue_purge(queue=self.queue_name)
        return True

    def __len__(self):
        queue = self.channel.queue_declare(self.queue_name, durable=True)
        return queue.method.message_count

    def get_data_from_queue(self, queue):
        data = None
        if len(self) == 0:
            return None

        for method_frame, _, body in self.channel.consume(queue):
            data = body
            self.channel.basic_ack(method_frame.delivery_tag)
            break

        self.channel.cancel()
        return data


class RabbitBlockingQueue(RabbitQueue):
    """
    Use the blocking right pop, should result in messages getting
    executed close to immediately by the consumer as opposed to
    being polled for
    """
    blocking = True

    def read(self):
        try:
            return self.get_data_from_queue(self.queue_name)
        except AMQPConnectionError:
            return None


class RabbitEventEmitter(BaseEventEmitter):
    def __init__(self, channel, **connection):
        super(RabbitEventEmitter, self).__init__(channel, **connection)
        credentials = pika.PlainCredentials(
            connection.get('username', 'guest'),
            connection.get('password', 'guest'))
        connection_params = pika.ConnectionParameters(
            host=connection.get('host', 'localhost'),
            port=connection.get('port', 5672),
            credentials=credentials,
            virtual_host=connection.get('vhost', '/'),
            ssl=connection.get('ssl', False))

        self.conn = pika.BlockingConnection(connection_params)
        self.channel = self.conn.channel()
        self.exchange_name = 'huey.events'
        self.channel.exchange_declare(
            exchange=self.exchange_name,
            type='fanout',
            auto_delete=False,
            durable=True)

    def emit(self, message):
        properties = pika.BasicProperties(
            content_type="text/plain",
            delivery_mode=2)

        self.channel.basic_publish(
            exchange=self.exchange_name,
            routing_key='',
            body=message,
            properties=properties)


Components = (RabbitBlockingQueue, None, None, RabbitEventEmitter)
