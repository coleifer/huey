from collections import deque
from tempfile import mkdtemp
import datetime
import shutil
import unittest

from huey.backends.dummy import DummyDataStore
from huey.backends.dummy import DummyEventEmitter
from huey.backends.dummy import DummyQueue
from huey.backends.dummy import DummySchedule
from huey.utils import EmptyData
try:
    from huey.backends.redis_backend import RedisDataStore
    from huey.backends.redis_backend import RedisEventEmitter
    from huey.backends.redis_backend import RedisQueue
    from huey.backends.redis_backend import RedisSchedule
except ImportError:
    RedisQueue = RedisDataStore = RedisSchedule = RedisEventEmitter = None

try:
    import plyvel
    from huey.backends.leveldb_backend import LevelDbDataStore
    from huey.backends.leveldb_backend import LevelDbEventEmitter
    from huey.backends.leveldb_backend import LevelDbQueue
    from huey.backends.leveldb_backend import LevelDbSchedule
except ImportError:
    (LevelDbDataStore, LevelDbEventEmitter, LevelDbQueue,
     LevelDbSchedule) = None


QUEUES = (DummyQueue, RedisQueue, LevelDbQueue)
DATA_STORES = (DummyDataStore, RedisDataStore, LevelDbDataStore)
SCHEDULES = (DummySchedule, RedisSchedule, LevelDbSchedule)
EVENTS = (DummyEventEmitter, RedisEventEmitter, LevelDbEventEmitter)


class HueyBackendTestCase(unittest.TestCase):
    def setUp(self):
        self.leveldb_path = mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.leveldb_path)

    def test_queues(self):
        for q in QUEUES:
            if not q:
                continue
            if issubclass(q, LevelDbQueue):
                queue = q('test', plyvel.DB(self.leveldb_path,
                                            create_if_missing=True))
            else:
                queue = q('test')
            queue.write('a')
            queue.write('b')
            self.assertEqual(len(queue), 2)
            self.assertEqual(queue.read(), 'a')
            self.assertEqual(queue.read(), 'b')
            self.assertEqual(queue.read(), None)

            queue.write('c')
            queue.write('d')
            queue.write('c')
            queue.write('x')
            queue.write('d')
            self.assertEqual(len(queue), 5)
            self.assertEqual(queue.remove('c'), 2)
            self.assertEqual(len(queue), 3)
            self.assertEqual(queue.read(), 'd')
            self.assertEqual(queue.read(), 'x')
            self.assertEqual(queue.read(), 'd')

    def test_data_stores(self):
        for d in DATA_STORES:
            if not d:
                continue
            if issubclass(d, LevelDbDataStore):
                data_store = d('test', plyvel.DB(self.leveldb_path,
                                                 create_if_missing=True))
            else:
                data_store = d('test')
            data_store.put('k1', 'v1')
            data_store.put('k2', 'v2')
            data_store.put('k3', 'v3')
            self.assertEqual(data_store.peek('k2'), 'v2')
            self.assertEqual(data_store.get('k2'), 'v2')
            self.assertEqual(data_store.peek('k2'), EmptyData)
            self.assertEqual(data_store.get('k2'), EmptyData)

            self.assertEqual(data_store.peek('k3'), 'v3')
            data_store.put('k3', 'v3-2')
            self.assertEqual(data_store.peek('k3'), 'v3-2')

    def test_schedules(self):
        for s in SCHEDULES:
            if not s:
                continue
            if issubclass(s, LevelDbSchedule):
                schedule = s('test', plyvel.DB(self.leveldb_path,
                                               create_if_missing=True))
            else:
                schedule = s('test')
            dt1 = datetime.datetime(2013, 1, 1, 0, 0)
            dt2 = datetime.datetime(2013, 1, 2, 0, 0)
            dt3 = datetime.datetime(2013, 1, 3, 0, 0)
            dt4 = datetime.datetime(2013, 1, 4, 0, 0)

            # Add to schedule out-of-order to ensure sorting is performed by
            # the schedule.
            schedule.add('s2', dt2)
            schedule.add('s1', dt1)
            schedule.add('s4', dt4)
            schedule.add('s3', dt3)

            # Ensure that asking for a timestamp previous to any item in the
            # schedule returns empty list.
            self.assertEqual(
                schedule.read(dt1 - datetime.timedelta(days=1)),
                [])

            # Ensure the upper boundary is inclusive of whatever timestamp
            # is passed in.
            self.assertEqual(schedule.read(dt3), ['s1', 's2', 's3'])
            self.assertEqual(schedule.read(dt3), [])

            # Ensure the schedule is flushed and an empty schedule returns an
            # empty list.
            self.assertEqual(schedule.read(dt4), ['s4'])
            self.assertEqual(schedule.read(dt4), [])

    def test_events(self):
        for e in EVENTS:
            if not e:
                continue
            if issubclass(e, LevelDbEventEmitter):
                e = e('test', plyvel.DB(self.leveldb_path,
                                        create_if_missing=True))
            else:
                e = e('test')

            messages = ['a', 'b', 'c', 'd']
            for message in messages:
                e.emit(message)

            if hasattr(e, '_events'):
                self.assertEqual(e._events, deque(['d', 'c', 'b', 'a']))
