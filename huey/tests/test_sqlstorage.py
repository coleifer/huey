import os
import unittest

try:
    import peewee
except ImportError:
    peewee = None

try:
    from huey.contrib.sqlstorage import SqlHuey
    from huey.contrib.sqlstorage import SqlStorage
except ImportError:
    if peewee is not None:
        raise
from huey.tests.base import BaseTestCase
from huey.tests.test_storage import StorageTests


@unittest.skipIf(peewee is None, 'requires peewee')
class TestSqlStorage(StorageTests, BaseTestCase):
    db_file = '/tmp/huey-sqlite.db'

    def setUp(self):
        if os.path.exists(self.db_file):
            os.unlink(self.db_file)
        super(TestSqlStorage, self).setUp()

    @classmethod
    def tearDownClass(cls):
        super(TestSqlStorage, cls).tearDownClass()
        if os.path.exists(cls.db_file):
            os.unlink(cls.db_file)

    def get_huey(self):
        return SqlHuey('sqlite:////tmp/huey-sqlite.db', utc=False)

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
