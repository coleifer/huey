from huey.backends.base import BaseQueue, BaseDataStore
from huey.utils import EmptyData


class DummyQueue(BaseQueue):
    def __init__(self, *args, **kwargs):
        super(DummyQueue, self).__init__(*args, **kwargs)
        self._queue = []

    def write(self, data):
        self._queue.insert(0, data)

    def read(self):
        try:
            return self._queue.pop()
        except IndexError:
            return None

    def flush(self):
        self._queue = []

    def remove(self, data):
        clone = []
        ct = 0
        for elem in self._queue:
            if elem == data:
                ct += 1
            else:
                clone.append(elem)
        self._queue = clone
        return ct

    def __len__(self):
        return len(self._queue)


class DummyDataStore(BaseDataStore):
    def __init__(self, *args, **kwargs):
        super(DummyDataStore, self).__init__(*args, **kwargs)
        self._results = {}

    def put(self, key, value):
        self._results[key] = value

    def peek(self, key):
        return self._results.get(key, EmptyData)

    def get(self, key):
        return self._results.pop(key, EmptyData)

    def flush(self):
        self._results = {}
