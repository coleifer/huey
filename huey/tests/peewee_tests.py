from contextlib import contextmanager
import unittest

from huey import Huey
from huey.backends.dummy import DummyDataStore
from huey.backends.dummy import DummyQueue
from huey.backends.dummy import DummySchedule
from huey.peewee_helpers import db_periodic_task
from huey.peewee_helpers import db_task
from peewee import *


queue = DummyQueue('test-queue')
schedule = DummySchedule('test-queue')
data_store = DummyDataStore('test-queue')
huey = Huey(queue, data_store, schedule=schedule)

STATE = []

class MockSqliteDatabase(SqliteDatabase):
    def record_call(fn):
        def inner(*args, **kwargs):
            STATE.append(fn.__name__)
            return fn(*args, **kwargs)
        return inner
    connect = record_call(SqliteDatabase.connect)
    _close = record_call(SqliteDatabase._close)
    transaction = record_call(SqliteDatabase.transaction)

db = MockSqliteDatabase('test.huey.db')

class Value(Model):
    data = CharField()

    class Meta:
        database = db

    @classmethod
    def create(cls, *args, **kwargs):
        STATE.append('create')
        return super(Value, cls).create(*args, **kwargs)

@db_task(huey, db)
def test_db_task(val):
    return Value.create(data=val)

class TestPeeweeHelpers(unittest.TestCase):
    def setUp(self):
        global STATE
        STATE = []
        queue.flush()
        data_store.flush()
        schedule.flush()
        Value.drop_table(True)
        Value.create_table()

    def test_helper(self):
        test_db_task('foo')
        self.assertEqual(STATE, ['connect'])
        huey.execute(huey.dequeue())
        self.assertEqual(STATE, ['connect', 'transaction', 'create', '_close'])
        self.assertEqual(Value.select().count(), 1)
