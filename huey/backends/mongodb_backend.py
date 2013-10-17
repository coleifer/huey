from huey.backends.base import BaseDataStore
from huey.backends.base import BaseQueue
from huey.backends.base import BaseSchedule
from huey.backends.base import BaseEventEmitter
from huey.utils import EmptyData

from pymongo import MongoClient

import re
import time
from collections import deque


def clean_name(name):
    return re.sub('[^a-z0-9_-]', '', name)


class MongoDbQueue(BaseQueue):
    blocking = True

    def __init__(self, name, **connection):
        super(MongoDbQueue, self).__init__(name, **connection)
        self.queue_name = clean_name(name)
        self.client = MongoClient(connection['host'], connection['port'])
        self.db = self.client[self.queue_name]

    def write(self, data):
        self.db.queue.insert({"date_created": time.time(), "data": data})

    def read(self):
        item = self.db.queue.find_and_modify(query={}, sort=[("_id", 1)], remove=True)
        return item['data'] if item else None

    def flush(self):
        self.db.queue.drop()

    def remove(self, data):
        res = self.db.queue.remove({"data": data})
        return res['n']

    def __len__(self):
        return self.db.queue.find().count()


class MongoDbSchedule(BaseSchedule):
    def __init__(self, name, **connection):
        super(MongoDbSchedule, self).__init__(name, **connection)
        self.key = clean_name(name)
        self.client = MongoClient(connection['host'], connection['port'])
        self.db = self.client[self.key]

    def convert_ts(self, ts):
        return time.mktime(ts.timetuple())

    def add(self, data, ts):
        self.db.schedule.insert({"date_created": time.time(), "data": data, "ts": self.convert_ts(ts)})

    def read(self, ts):
        uts = self.convert_ts(ts)
        res = []
        item = self.db.schedule.find_and_modify(query={"ts": {"$lt": uts}}, sort=[("_id", 1)], remove=True)
        while item:
            res.append(item['data'])
            item = self.db.schedule.find_and_modify(query={"ts": {"$lt": uts}}, sort=[("_id", 1)], remove=True)
        return res

    def flush(self):
        self.db.schedule.drop()


class MongoDbDataStore(BaseDataStore):
    def __init__(self, name, **connection):
        super(MongoDbDataStore, self).__init__(name, **connection)
        self.key = clean_name(name)
        self.client = MongoClient(connection['host'], connection['port'])
        self.db = self.client[self.key]

    def put(self, key, value):
        self.db.results.insert({"date_created": time.time(), "key": key, "value": value})

    def peek(self, key):
        item = self.db.results.find_one({"key": key})
        return item['value'] if item else EmptyData

    def get(self, key):
        item = self.db.results.find_and_modify(query={"key": key}, remove=True)
        return item['value'] if item else EmptyData

    def flush(self):
        self.db.results.drop()


class DummyEventEmitter(BaseEventEmitter):
    def __init__(self, *args, **kwargs):
        super(DummyEventEmitter, self).__init__(*args, **kwargs)
        self._events = deque()
        self.__size = 100

    def emit(self, message):
        self._events.appendleft(message)
        num_events = len(self._events)
        if num_events > self.__size * 1.5:
            while num_events > self.__size:
                self._events.popright()
                num_events -= 1


Components = (MongoDbQueue, MongoDbDataStore, MongoDbSchedule, DummyEventEmitter)
