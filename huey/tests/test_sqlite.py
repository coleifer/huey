import datetime
import threading

from huey.constants import EmptyData
from huey.consumer import Consumer
from huey.contrib.sqlitedb import SqliteHuey
from huey.contrib.sqlitedb import SqliteStorage
from huey.tests.base import CaptureLogs
from huey.tests.base import HueyTestCase


sqlite_huey = SqliteHuey('/tmp/sqlite-huey.db')


class TestSqliteStorage(HueyTestCase):
    def get_huey(self):
        return sqlite_huey

    def test_enqueue_dequeue_results(self):
        @self.huey.task()
        def test_queues_add(k, v):
            return k + v

        db = self.huey.storage
        self.assertTrue(isinstance(db, SqliteStorage))

        res = test_queues_add(3, 4)
        self.assertEqual(db.queue_size(), 1)

        task = self.huey.dequeue()
        self.huey.execute(task)
        self.assertEqual(db.result_store_size(), 1)
        self.assertEqual(res.get(), 7)
        self.assertEqual(db.queue_size(), 0)
        self.assertEqual(db.result_store_size(), 0)

    def test_put_if_empty(self):
        storage = self.huey.storage
        self.assertTrue(storage.put_if_empty('k1', '1'))
        self.assertFalse(storage.put_if_empty('k1', '2'))
        self.assertEqual(storage.pop_data('k1'), '1')

        self.assertTrue(storage.put_if_empty('k1', '3'))
        self.assertTrue(storage.put_if_empty('k2', '4'))
        self.assertFalse(storage.put_if_empty('k1', 'x'))
        self.assertEqual(storage.pop_data('k1'), '3')
        self.assertEqual(storage.pop_data('k2'), '4')

    def test_schedule(self):
        dt1 = datetime.datetime(2013, 1, 1, 0, 0)
        dt2 = datetime.datetime(2013, 1, 2, 0, 0)
        dt3 = datetime.datetime(2013, 1, 3, 0, 0)

        @self.huey.task()
        def test_task(k, v):
            return k + v

        test_task.schedule((1, 2), eta=dt1, convert_utc=False)
        test_task.schedule((3, 4), eta=dt3, convert_utc=False)
        test_task.schedule((2, 3), eta=dt2, convert_utc=False)
        self.assertEqual(len(self.huey), 3)

        for i in range(3):
            self.huey.add_schedule(self.huey.dequeue())

        tasks = self.huey.scheduled()
        self.assertEqual(len(tasks), 3)

        c1, c2, c3 = tasks
        self.assertEqual(c1.data, ((1, 2), {}))
        self.assertEqual(c2.data, ((2, 3), {}))
        self.assertEqual(c3.data, ((3, 4), {}))

        storage = self.huey.storage
        self.assertEqual(len(storage.read_schedule(dt2)), 2)
        self.assertEqual(len(storage.read_schedule(dt2)), 0)

        self.assertEqual(len(storage.read_schedule(dt3)), 1)
        self.assertEqual(len(storage.read_schedule(dt3)), 0)

    def test_consumer_integration(self):
        lock = threading.Lock()

        @self.huey.task()
        def add_values(a, b):
            return a + b

        consumer = Consumer(self.huey, max_delay=0.1, workers=2,
                            worker_type='thread', health_check_interval=0.01)

        with CaptureLogs() as capture:
            consumer.start()
            try:
                r1 = add_values(1, 2)
                r2 = add_values(2, 3)
                r3 = add_values(3, 5)

                self.assertEqual(r1.get(blocking=True, timeout=3), 3)
                self.assertEqual(r2.get(blocking=True, timeout=3), 5)
                self.assertEqual(r3.get(blocking=True, timeout=3), 8)
            finally:
                consumer.stop()
                for _, worker in consumer.worker_threads:
                    worker.join()

        executing = 0
        executed = 0
        for message in capture.messages[-7:-1]:
            if message.startswith('Executing huey.tests.test_'):
                executing += 1
            elif message.startswith('Executed huey.tests.test_'):
                executed += 1

        self.assertEqual(executing, 3)
        self.assertEqual(executed, 3)
        self.assertTrue(capture.messages[-1].startswith('Shutting down'))
