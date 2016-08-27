import datetime
import itertools

from redis.connection import ConnectionPool

from huey.constants import EmptyData
from huey.storage import RedisHuey
from huey.storage import RedisStorage
from huey.tests.base import b
from huey.tests.base import HueyTestCase

class TestRedisStorage(HueyTestCase):
    def test_queues(self):
        storage = self.huey.storage
        storage.flush_queue()

        @self.huey.task()
        def test_queues_add(k, v):
            return k + v

        res = test_queues_add('k', 'v')
        self.assertEqual(storage.queue_size(), 1)
        task = self.huey.dequeue()
        self.huey.execute(task)
        self.assertEqual(res.get(), 'kv')

        res = test_queues_add('\xce', '\xcf')
        task = self.huey.dequeue()
        self.huey.execute(task)
        self.assertEqual(res.get(), '\xce\xcf')

    def test_data_stores(self):
        storage = self.huey.storage
        storage.put_data('k1', 'v1')
        storage.put_data('k2', 'v2')
        storage.put_data('k3', 'v3')
        self.assertEqual(storage.peek_data('k2'), b('v2'))
        self.assertEqual(storage.pop_data('k2'), b('v2'))
        self.assertEqual(storage.peek_data('k2'), EmptyData)
        self.assertEqual(storage.pop_data('k2'), EmptyData)

        self.assertEqual(storage.peek_data('k3'), b('v3'))
        storage.put_data('k3', 'v3-2')
        self.assertEqual(storage.peek_data('k3'), b('v3-2'))

    def test_schedules(self):
        storage = self.huey.storage
        dt1 = datetime.datetime(2013, 1, 1, 0, 0)
        dt2 = datetime.datetime(2013, 1, 2, 0, 0)
        dt3 = datetime.datetime(2013, 1, 3, 0, 0)
        dt4 = datetime.datetime(2013, 1, 4, 0, 0)

        # Add to schedule out-of-order to ensure sorting is performed by
        # the schedule.
        storage.add_to_schedule('s2', dt2)
        storage.add_to_schedule('s1', dt1)
        storage.add_to_schedule('s4', dt4)
        storage.add_to_schedule('s3', dt3)

        # Ensure that asking for a timestamp previous to any item in the
        # schedule returns empty list.
        self.assertEqual(
            storage.read_schedule(dt1 - datetime.timedelta(days=1)),
            [])

        # Ensure the upper boundary is inclusive of whatever timestamp
        # is passed in.
        self.assertEqual(
            storage.read_schedule(dt3),
            [b('s1'), b('s2'), b('s3')])
        self.assertEqual(storage.read_schedule(dt3), [])

        # Ensure the schedule is flushed and an empty schedule returns an
        # empty list.
        self.assertEqual(storage.read_schedule(dt4), [b('s4')])
        self.assertEqual(storage.read_schedule(dt4), [])

    def test_events(self):
        storage = self.huey.storage
        ps = storage.listener()

        messages = ['a', 'b', 'c']
        for message in messages:
            storage.emit(message)

        g = ps.listen()
        next(g)
        self.assertEqual(next(g)['data'], b('a'))
        self.assertEqual(next(g)['data'], b('b'))
        self.assertEqual(next(g)['data'], b('c'))

    def test_event_iterator(self):
        i = iter(self.huey.storage)

        self.huey.storage.emit('"a"')
        self.huey.storage.emit('"b"')

        res = next(i)
        self.assertEqual(res, 'a')
        res = next(i)
        self.assertEqual(res, 'b')

    def test_conflicting_init_args(self):
        options = {
            'host': 'localhost',
            'url': 'redis://localhost',
            'connection_pool': ConnectionPool()
        }
        combinations = itertools.combinations(options.items(), 2)

        for kwargs in (dict(item) for item in combinations):
            self.assertRaises(ValueError, lambda: RedisStorage(**kwargs))

    def test_init_with_url(self):
        s = RedisStorage(url='redis://example.org:1234')
        args = s.pool.connection_kwargs
        self.assertEqual(args['host'], 'example.org')
        self.assertEqual(args['port'], 1234)

    def test_init_with_kwargs(self):
        s = RedisStorage(host='example.org', port=1234)
        args = s.pool.connection_kwargs
        self.assertEqual(args['host'], 'example.org')
        self.assertEqual(args['port'], 1234)

    def test_init_huey(self):
        huey = RedisHuey(url='redis://example.org:31337/?db=7')
        conn = huey.storage.pool.connection_kwargs
        self.assertEqual(conn['host'], 'example.org')
        self.assertEqual(conn['port'], 31337)
        self.assertEqual(conn['db'], 7)
