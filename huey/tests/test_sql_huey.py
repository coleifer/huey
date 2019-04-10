import os
import unittest

try:
    import peewee
except ImportError:
    peewee = None

try:
    from huey.contrib.sql_huey import SqlHuey
    from huey.contrib.sql_huey import SqlStorage
except ImportError:
    if peewee is not None:
        raise
from huey.tests.base import BaseTestCase
from huey.tests.test_storage import StorageTests


SQLHUEY_URL = os.environ.get('SQLHUEY_URL') or 'sqlite:////tmp/huey-sqlite.db'


@unittest.skipIf(peewee is None, 'requires peewee')
class TestSqlStorage(StorageTests, BaseTestCase):
    db_file = '/tmp/huey-sqlite.db'

    def setUp(self):
        if os.path.exists(self.db_file):
            os.unlink(self.db_file)
        super(TestSqlStorage, self).setUp()

    def tearDown(self):
        super(TestSqlStorage, self).tearDown()
        self.huey.storage.drop_tables()

    @classmethod
    def tearDownClass(cls):
        super(TestSqlStorage, cls).tearDownClass()
        if os.path.exists(cls.db_file):
            os.unlink(cls.db_file)

    def get_huey(self):
        return SqlHuey(database=SQLHUEY_URL, utc=False)

    def test_sql_huey_basic(self):
        @self.huey.task()
        def task_a(n):
            return n + 1

        r1 = task_a(1)
        r2 = task_a(2)
        self.assertEqual(self.execute_next(), 2)
        self.assertEqual(len(self.huey), 1)
        self.assertEqual(self.huey.result_count(), 1)
        r2.revoke()
        self.assertEqual(self.huey.result_count(), 2)

        self.assertTrue(self.execute_next() is None)
        self.assertEqual(len(self.huey), 0)
        self.assertEqual(self.huey.result_count(), 1)

        r3 = task_a.schedule((3,), delay=10)
        self.assertEqual(len(self.huey), 1)
        self.assertTrue(self.execute_next() is None)
        self.assertEqual(self.huey.scheduled_count(), 1)
        self.assertEqual(len(self.huey), 0)
        self.assertEqual(self.huey.result_count(), 1)

        tasks = self.huey.read_schedule(r3.task.eta)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].id, r3.id)

    def test_sql_huey_priority(self):
        @self.huey.task()
        def task_a(n):
            return n

        @self.huey.task(priority=1)
        def task_b(n):
            return n * 10

        task_a(1)
        task_b(2)
        task_a(3, priority=2)
        task_b(4, priority=2)
        task_a(5, priority=1)
        task_b(6, priority=0)
        task_a(7)
        task_b(8)

        results = [3, 40, 20, 5, 80, 1, 60, 7]
        for result in results:
            self.assertEqual(self.execute_next(), result)

        self.assertEqual(len(self.huey), 0)
