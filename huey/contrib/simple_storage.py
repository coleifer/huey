from huey.api import Huey
from huey.constants import EmptyData
from huey.contrib.simple import Client
from huey.storage import BaseStorage


class SimpleStorage(BaseStorage):
    copy_methods = (
        'add_to_schedule',
        'read_schedule',
        'schedule_size',
        'flush_schedule',
        'put_data',
        'peek_data',
        'pop_data',
        'has_data_for_key',
        'put_if_empty',
        'result_store_size',
        'flush_results')

    def __init__(self, name='huey', host='127.0.0.1', port=31337,
                 **storage_kwargs):
        super(SimpleStorage, self).__init__(name=name, **storage_kwargs)
        self.client = Client(host=host, port=port)
        self.client.connect()

        for method in self.copy_methods:
            setattr(self, method, getattr(self.client, method))

    def enqueue(self, data):
        self.client.enqueue(self.name, data)

    def dequeue(self):
        return self.client.dequeue(self.name)

    def unqueue(self, data):
        return self.client.unqueue(self.name)

    def queue_size(self):
        return self.client.queue_size(self.name)

    def flush_queue(self):
        return self.client.flush_queue(self.name)

    def flush_all(self):
        return self.client.flush_all()


class SimpleHuey(Huey):
    def get_storage(self, **params):
        return SimpleStorage(self.name, **params)
