from huey.api import Huey
from huey.constants import EmptyData
from huey.storage import BaseStorage

from simpledb import Client


class SimpleStorage(BaseStorage):
    def __init__(self, name='huey', host='127.0.0.1', port=31337,
                 **storage_kwargs):
        super(SimpleStorage, self).__init__(name=name, **storage_kwargs)
        self.client = Client(host=host, port=port)

    def enqueue(self, data):
        self.client.lpush(self.name, data)

    def dequeue(self):
        return self.client.rpop(self.name)

    def unqueue(self, data):
        return self.client.lrem(self.name)

    def queue_size(self):
        return self.client.llen(self.name)

    def flush_queue(self):
        return self.client.lflush(self.name)

    def flush_all(self):
        return self.client.flushall()

    def add_to_schedule(self, data, ts):
        return self.client.add(str(ts), data)

    def read_schedule(self, ts):
        return self.client.read(str(ts))

    def schedule_size(self):
        return self.client.length_schedule()

    def flush_schedule(self):
        return self.client.flush_schedule()

    def put_data(self, key, value):
        return self.client.set(key, value)

    def peek_data(self, key):
        return self.client.get(key)

    def pop_data(self, key):
        return self.client.pop(key)

    def has_data_for_key(self, key):
        return self.client.exists(key)

    def put_if_empty(self, key, value):
        return self.client.setnx(key, value)

    def result_store_size(self, key, value):
        return self.client.length()

    def flush_results(self):
        return self.client.flush()


class SimpleHuey(Huey):
    def get_storage(self, **params):
        return SimpleStorage(self.name, **params)
