from collections import deque
import datetime
import os
import sys
import tempfile
import unittest

from huey.api import Huey
from huey.backends.dummy import DummyDataStore
from huey.backends.dummy import DummyEventEmitter
from huey.backends.dummy import DummyQueue
from huey.backends.dummy import DummySchedule
from huey.utils import EmptyData
from huey.backends.sqlite_backend import SqliteDataStore
from huey.backends.sqlite_backend import SqliteQueue
from huey.backends.sqlite_backend import SqliteSchedule
try:
    from huey.backends.redis_backend import RedisDataStore
    from huey.backends.redis_backend import RedisEventEmitter
    from huey.backends.redis_backend import RedisQueue
    from huey.backends.redis_backend import RedisSchedule
except ImportError:
    RedisQueue = RedisDataStore = RedisSchedule = RedisEventEmitter = None

try:
    from huey.backends.rabbitmq_backend import RabbitQueue, RabbitEventEmitter
except ImportError:
    RabbitQueue = RabbitEventEmitter = None


redis_kwargs = {}

QUEUES = (DummyQueue, RedisQueue, SqliteQueue, RabbitQueue)
DATA_STORES = (DummyDataStore, RedisDataStore, SqliteDataStore, None)
SCHEDULES = (DummySchedule, RedisSchedule, SqliteSchedule, None)
EVENTS = (DummyEventEmitter, RedisEventEmitter, None, RabbitEventEmitter)


class HueyBackendTestCase(unittest.TestCase):
    def setUp(self):
        self.sqlite_location = tempfile.mkstemp(prefix='hueytest.')[1]

    def tearDown(self):
        os.unlink(self.sqlite_location)

    def test_queues(self):
        result_store = DummyDataStore('dummy')
        for q in QUEUES:
            if not q:
                continue
            if issubclass(q, SqliteQueue):
                queue = q('test', location=self.sqlite_location)
            elif issubclass(q, RedisQueue):
                queue = q('test', **redis_kwargs)
            else:
                queue = q('test')
            queue.flush()
            queue.write(b'a')
            queue.write(b'b')
            self.assertEqual(len(queue), 2)
            self.assertEqual(queue.read(), b'a')
            self.assertEqual(queue.read(), b'b')
            self.assertEqual(queue.read(), None)

            queue.write(b'c')
            queue.write(b'd')
            queue.write(b'c')
            queue.write(b'x')
            queue.write(b'd')
            self.assertEqual(len(queue), 5)
            self.assertEqual(queue.remove(b'c'), 2)
            self.assertEqual(len(queue), 3)
            self.assertEqual(queue.read(), b'd')
            self.assertEqual(queue.read(), b'x')
            self.assertEqual(queue.read(), b'd')

            queue.flush()
            test_huey = Huey(queue, result_store)

            @test_huey.task()
            def test_queues_add(k, v):
                return k + v

            res = test_queues_add('k', 'v')
            self.assertEqual(len(queue), 1)
            task = test_huey.dequeue()
            test_huey.execute(task)
            self.assertEqual(res.get(), 'kv')

            res = test_queues_add('\xce', '\xcf')
            task = test_huey.dequeue()
            test_huey.execute(task)
            self.assertEqual(res.get(), '\xce\xcf')

    def test_data_stores(self):
        for d in DATA_STORES:
            if not d:
                continue
            if issubclass(d, SqliteDataStore):
                data_store = d('test', location=self.sqlite_location)
            elif issubclass(d, RedisDataStore):
                data_store = d('test', **redis_kwargs)
            else:
                data_store = d('test')
            data_store.put('k1', b'v1')
            data_store.put('k2', b'v2')
            data_store.put('k3', b'v3')
            self.assertEqual(data_store.peek('k2'), b'v2')
            self.assertEqual(data_store.get('k2'), b'v2')
            self.assertEqual(data_store.peek('k2'), EmptyData)
            self.assertEqual(data_store.get('k2'), EmptyData)

            self.assertEqual(data_store.peek('k3'), b'v3')
            data_store.put('k3', b'v3-2')
            self.assertEqual(data_store.peek('k3'), b'v3-2')

    def test_schedules(self):
        for s in SCHEDULES:
            if not s:
                continue
            if issubclass(s, SqliteSchedule):
                schedule = s('test', location=self.sqlite_location)
            elif issubclass(s, RedisSchedule):
                schedule = s('test', **redis_kwargs)
            else:
                schedule = s('test')
            dt1 = datetime.datetime(2013, 1, 1, 0, 0)
            dt2 = datetime.datetime(2013, 1, 2, 0, 0)
            dt3 = datetime.datetime(2013, 1, 3, 0, 0)
            dt4 = datetime.datetime(2013, 1, 4, 0, 0)

            # Add to schedule out-of-order to ensure sorting is performed by
            # the schedule.
            schedule.add(b's2', dt2)
            schedule.add(b's1', dt1)
            schedule.add(b's4', dt4)
            schedule.add(b's3', dt3)

            # Ensure that asking for a timestamp previous to any item in the
            # schedule returns empty list.
            self.assertEqual(
                schedule.read(dt1 - datetime.timedelta(days=1)),
                [])

            # Ensure the upper boundary is inclusive of whatever timestamp
            # is passed in.
            self.assertEqual(schedule.read(dt3), [b's1', b's2', b's3'])
            self.assertEqual(schedule.read(dt3), [])

            # Ensure the schedule is flushed and an empty schedule returns an
            # empty list.
            self.assertEqual(schedule.read(dt4), [b's4'])
            self.assertEqual(schedule.read(dt4), [])

    def test_events(self):
        for e in EVENTS:
            if not e:
                continue
            e = e('test')

            messages = ['a', 'b', 'c', 'd']
            for message in messages:
                e.emit(message)

            if hasattr(e, '_events'):
                self.assertEqual(e._events, deque(['d', 'c', 'b', 'a']))
