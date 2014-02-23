from datetime import datetime
import binascii
import hashlib
import json
import time

from huey.backends.base import BaseQueue
from huey.backends.base import BaseSchedule
from huey.backends.base import BaseDataStore
from huey.backends.base import BaseEventEmitter
from huey.utils import EmptyData


class IdCounter(object):
    """ LevelDb does not have support for auto-incrementing IDs, so we have
        to use this object to keep track of the last ID.

    Also, since LevelDb's default comparator sorts in lexicographical order,
    we store the ID as a (by default) fixed-width 64bit bytestring instead
    of an integer.
    """
    def __init__(self, start=0, size=64):
        self.size = size
        self._max_value = (2**self.size)-1
        if isinstance(start, basestring):
            self.count = self.id_to_int(start)
        else:
            self.count = start

    def int_to_id(self, val):
        hexval = hex(val)[2:].rstrip('L')
        return binascii.unhexlify('0'*(self.size-len(hexval))+hexval)

    def id_to_int(self, val):
        return int(binascii.hexlify(val), 16)

    def increment(self):
        if self.count == self._max_value:
            raise ValueError("Maximum value reached.")
        self.count += 1
        return self.current()

    def current(self):
        return self.int_to_id(self.count)


class LevelDbQueue(BaseQueue):
    def __init__(self, name, db, sync=False):
        self._db = db.prefixed_db(b"huey_queue_{0}".format(name))
        self._sync = sync
        try:
            last_entry = next(self._db.iterator(reverse=True,
                                                include_value=False))
            self._counter = IdCounter(start=last_entry.split('_')[0])
        except StopIteration:
            self._counter = IdCounter()
        self.name = name
        self.connection = {'db': self._db}

    def write(self, data):
        key = b"{0}_{1}".format(self._counter.increment(),
                                hashlib.sha1(data).hexdigest())
        self._db.put(key, data, sync=self._sync)

    def read(self):
        try:
            id, data = next(self._db.iterator())
        except StopIteration:
            return None
        if id:
            self._db.delete(id)
            return data

    def remove(self, data):
        delete_counter = 0
        shasum = hashlib.sha1(data).hexdigest()
        for id in self._db.iterator(include_value=False):
            if id.split('_')[1] == shasum:
                self._db.delete(id)
                delete_counter += 1
        return delete_counter

    def flush(self):
        for id in self._db.iterator(include_value=False):
            self._db.delete(id)

    def __len__(self):
        # TODO: This is clearly not ideal, but it seems like short of keeping
        # our own on-write counter this seems to be the way to go [1]
        # http://stackoverflow.com/questions/13418942
        counter = 0
        for x in self._db.iterator(include_value=False, include_key=False):
            counter += 1
        return counter


class LevelDbSchedule(BaseSchedule):
    def __init__(self, name, db, sync=False):
        self._db = db.prefixed_db("huey_schedule_{0}".format(name))
        self._sync = sync
        try:
            last_entry = next(self._db.iterator(reverse=True,
                                                include_value=False))
            self._counter = IdCounter(start=last_entry.split('_')[1])
        except StopIteration:
            self._counter = IdCounter()
        self.name = name
        self.connection = {'db': self._db}

    def convert_ts(self, ts):
        return datetime.strftime(ts, "%Y-%m-%dT%H:%M:%S.%f")

    def parse_ts(self, ts):
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%f")

    def add(self, data, ts):
        id = self._counter.increment()
        self._db.put(b"{0}_{1}".format(self.convert_ts(ts), id), bytes(data),
                     sync=self._sync)

    def read(self, ts):
        results = []
        # TODO: This is far from ideal, there must be a way to accomplish this
        # more efficiently with the `start`, `stop` or `prefix` parameter to
        # the iterator. Since the schedule will in all likelihood never store
        # a huge amount of tasks, it should be safe for now.
        for key, data in self._db.iterator():
            entry_ts = self.parse_ts(key.split('_')[0])
            if entry_ts <= ts:
                results.append(data)
                self._db.delete(key)
        return results

    def flush(self):
        for id in self._db.iterator(include_value=False):
            self._db.delete(id)


class LevelDbDataStore(BaseDataStore):
    """
    Base implementation for a data store
    """
    def __init__(self, name, db, sync=False):
        self._db = db.prefixed_db("huey_results_{0}".format(name))
        self._sync = sync
        self.name = name
        self.connection = {'db': self._db}

    def put(self, key, value):
        self._db.put(bytes(key), bytes(value), sync=self._sync)

    def peek(self, key):
        data = self._db.get(bytes(key))
        if data is None:
            return EmptyData
        else:
            return data

    def get(self, key):
        data = self._db.get(bytes(key))
        if data is None:
            return EmptyData
        else:
            self._db.delete(key)
            return data

    def flush(self):
        for id in self._db.iterator(include_value=False):
            self._db.delete(id)


class LevelDbEventEmitter(BaseEventEmitter):
    def __init__(self, channel, db, size=500, sync=False):
        self._size = size
        self._db = db.prefixed_db("huey_events_{0}".format(channel))
        self._sync = sync
        try:
            last_entry = next(self._db.iterator(reverse=True,
                                                include_value=False))
            self._counter = IdCounter(start=last_entry)
        except StopIteration:
            self._counter = IdCounter()
        self.channel = channel
        self.connection = {'db': self._db}

    def emit(self, message):
        id = self._counter.increment()
        self._db.put(id, bytes(message), sync=self._sync)
        current_counter = self._counter.id_to_int(self._counter.current())
        if current_counter >= self._size:
            stop = self._counter.int_to_id(current_counter - self._size - 200)
            for id in self._db.iterator(stop=stop, include_value=False):
                self._db.delete(id)

    def read(self):
        wait = 0.1
        max_wait = 2
        tries = 0
        old_val = self._counter.current()
        while True:
            if self._counter.current() != old_val:
                return (json.loads(msg) for msg in
                        self._db.iterator(start=old_val,
                                          stop=self._counter.current(),
                                          include_start=False,
                                          include_stop=True,
                                          include_key=False))
            else:
                tries += 1
                time.sleep(wait)
                wait = min(max_wait, tries/10 + wait)


Components = (LevelDbQueue, LevelDbSchedule, LevelDbDataStore,
              LevelDbEventEmitter)
