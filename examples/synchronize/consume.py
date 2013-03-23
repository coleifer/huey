#!/usr/bin/env python

import logging
import requests

from huey.backends.redis_backend import RedisBlockingQueue, RedisDataStore
from huey.bin.huey_consumer import Consumer
from huey.bin.config import BaseConfiguration
from huey.decorators import queue_command
from huey.queue import Invoker


queue = RedisBlockingQueue('test', host='localhost', port=6379)
result_store = RedisDataStore('test', host='localhost', port=6379)
invoker = Invoker(queue, result_store=result_store)


class Configuration(BaseConfiguration):
    QUEUE = queue
    RESULT_STORE = result_store
    LOGLEVEL = 'DEBUG'


@queue_command(invoker)
def search_yahoo(query):
    url = 'http://www.yahoo.com/?q=%s' % query
    resp = requests.get(url)
    return resp.text


@queue_command(invoker)
def search_google(query):
    url = 'http://www.google.com/search?q=%s' % query
    resp = requests.get(url)
    return resp.text


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    try:
        consumer = Consumer(invoker, Configuration)
        consumer.run()
    except KeyboardInterrupt:
        pass
