"""
Test-only implementations of Queue and DataStore.  These will not work for
real applications because they only store tasks/results in memory.
"""
from collections import deque
import heapq

from huey.backends.base import BaseDataStore
from huey.backends.base import BaseEventEmitter
from huey.backends.base import BaseQueue
from huey.backends.base import BaseSchedule
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


class DummySchedule(BaseSchedule):
    def __init__(self, *args, **kwargs):
        super(DummySchedule, self).__init__(*args, **kwargs)
        self._schedule = []

    def add(self, data, ts):
        heapq.heappush(self._schedule, (ts, data))

    def read(self, ts):
        res = []
        while len(self._schedule):
            sts, data = heapq.heappop(self._schedule)
            if sts <= ts:
                res.append(data)
            else:
                self.add(data, sts)
                break
        return res

    def flush(self):
        self._schedule = []


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


Components = (DummyQueue, DummyDataStore, DummySchedule, DummyEventEmitter)
