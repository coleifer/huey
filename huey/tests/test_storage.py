import datetime

from huey.tests.base import b
from huey.tests.base import HueyTestCase
from huey.utils import EmptyData

class TestRedisStorage(HueyTestCase):
    def test_queues(self):
        queue = self.huey.queue
        queue.flush()

        @self.huey.task()
        def test_queues_add(k, v):
            return k + v

        res = test_queues_add('k', 'v')
        self.assertEqual(len(queue), 1)
        task = self.huey.dequeue()
        self.huey.execute(task)
        self.assertEqual(res.get(), 'kv')

        res = test_queues_add('\xce', '\xcf')
        task = self.huey.dequeue()
        self.huey.execute(task)
        self.assertEqual(res.get(), '\xce\xcf')

    def test_data_stores(self):
        data_store = self.huey.result_store
        data_store.put('k1', 'v1')
        data_store.put('k2', 'v2')
        data_store.put('k3', 'v3')
        self.assertEqual(data_store.peek('k2'), b('v2'))
        self.assertEqual(data_store.get('k2'), b('v2'))
        self.assertEqual(data_store.peek('k2'), EmptyData)
        self.assertEqual(data_store.get('k2'), EmptyData)

        self.assertEqual(data_store.peek('k3'), b('v3'))
        data_store.put('k3', 'v3-2')
        self.assertEqual(data_store.peek('k3'), b('v3-2'))

    def test_schedules(self):
        schedule = self.huey.schedule
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
        self.assertEqual(schedule.read(dt3), [b('s1'), b('s2'), b('s3')])
        self.assertEqual(schedule.read(dt3), [])

        # Ensure the schedule is flushed and an empty schedule returns an
        # empty list.
        self.assertEqual(schedule.read(dt4), [b('s4')])
        self.assertEqual(schedule.read(dt4), [])

    def test_events(self):
        e = self.huey.events
        ps = e.listener()

        messages = ['a', 'b', 'c']
        for message in messages:
            e.emit(message)

        g = ps.listen()
        next(g)
        self.assertEqual(next(g)['data'], b('a'))
        self.assertEqual(next(g)['data'], b('b'))
        self.assertEqual(next(g)['data'], b('c'))
