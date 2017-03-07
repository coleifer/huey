import datetime

from huey.constants import EmptyData
from huey.contrib.sqlitedb import SqliteHuey
from huey.contrib.sqlitedb import SqliteStorage
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

    def test_schedule(self):
        dt1 = datetime.datetime(2013, 1, 1, 0, 0)
        dt2 = datetime.datetime(2013, 1, 2, 0, 0)
        dt3 = datetime.datetime(2013, 1, 3, 0, 0)
        dt4 = datetime.datetime(2013, 1, 4, 0, 0)

        @self.huey.task()
        def test_task(k, v):
            return k + v

        test_task.schedule((1, 2), eta=dt1, convert_utc=False)
        test_task.schedule((4, 5), eta=dt4, convert_utc=False)
        test_task.schedule((3, 4), eta=dt3, convert_utc=False)
        test_task.schedule((2, 3), eta=dt2, convert_utc=False)
        self.assertEqual(len(self.huey), 4)

        for i in range(4):
            self.huey.add_schedule(self.huey.dequeue())

        tasks = self.huey.scheduled()
        self.assertEqual(len(tasks), 4)

        c1, c2, c3, c4 = tasks
        self.assertEqual(c1.data, ((1, 2), {}))
        self.assertEqual(c2.data, ((2, 3), {}))
        self.assertEqual(c3.data, ((3, 4), {}))
        self.assertEqual(c4.data, ((4, 5), {}))

        storage = self.huey.storage
        self.assertEqual(len(storage.read_schedule(dt2)), 2)
        self.assertEqual(len(storage.read_schedule(dt2)), 0)

        self.assertEqual(len(storage.read_schedule(dt4)), 2)
        self.assertEqual(len(storage.read_schedule(dt4)), 0)
