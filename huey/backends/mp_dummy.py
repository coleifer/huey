from huey.backends.base import BaseQueue, BaseDataStore
from huey.utils import EmptyData
from Queue import Empty

import multiprocessing, os

_objects = {}

class MPDummyQueue(BaseQueue):
    def __init__(self, *args, **kwargs):
        super(MPDummyQueue, self).__init__(*args, **kwargs)
        
        self._id = '%s.%s' % (os.getpid(), id(self))
        queue = multiprocessing.Manager().list()
        _objects[self._id] = queue

    @property
    def _queue(self):
        return _objects[self._id]

    def write(self, data):
        self._queue.insert(0, data)

    def read(self):
        try:
            return self._queue.pop()
        except IndexError:
            return None

    def flush(self):
        while True:
            try:
                self._queue.pop()
            except IndexError:
                return

    def remove(self, data):
        self._queue.remove(data)

    def __len__(self):
        return len(self._queue)


class MPDummyDataStore(BaseDataStore):
    def __init__(self, *args, **kwargs):
        super(MPDummyDataStore, self).__init__(*args, **kwargs)
        
        self._id = '%s.%s' % (os.getpid(), id(self))
        results = multiprocessing.Manager().dict()
        _objects[self._id] = results

    @property
    def _results(self):
        return _objects[self._id]

    def put(self, key, value):
        self._results[key] = value

    def peek(self, key):
        return self._results.get(key, EmptyData)

    def get(self, key):
        return self._results.pop(key, EmptyData)

    def flush(self):
        self._results.clear()