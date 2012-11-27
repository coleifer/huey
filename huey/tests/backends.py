import datetime
import unittest

from huey.backends.dummy import DummyQueue, DummyDataStore
from huey.exceptions import QueueException
from huey.registry import registry
from huey.utils import EmptyData
try:
    from huey.backends.redis_backend import RedisQueue, RedisDataStore
except ImportError:
    RedisQueue = RedisDataStore = None


QUEUES = (DummyQueue, RedisQueue,)
DATA_STORES = (DummyDataStore, RedisDataStore,)


class HueyBackendTestCase(unittest.TestCase):
    def test_queues(self):
        for q in QUEUES:
            if not q:
                continue
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

        for d in DATA_STORES:
            if not d:
                continue
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
