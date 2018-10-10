import operator
import pickle
import threading

from peewee import *

from huey.api import Huey
from huey.constants import EmptyData
from huey.storage import BaseStorage


class BaseModel(Model):
    class Meta:
        database = SqliteDatabase(None)  # Placeholder.


class Task(BaseModel):
    queue = CharField()
    data = BlobField()


class Schedule(BaseModel):
    queue = CharField()
    data = BlobField()
    timestamp = TimestampField()


class KeyValue(BaseModel):
    queue = CharField()
    key = CharField()
    value = BlobField()

    class Meta:
        primary_key = CompositeKey('queue', 'key')


class SqliteStorage(BaseStorage):
    def __init__(self, name='huey', filename='huey.db', **storage_kwargs):
        self.filename = filename
        self.database = SqliteDatabase(filename, **storage_kwargs)
        super(SqliteStorage, self).__init__(name)
        self.initialize_task_table()

    def initialize_task_table(self):
        Task._meta.database = self.database
        Schedule._meta.database = self.database
        KeyValue._meta.database = self.database
        self.database.create_tables([Task, Schedule, KeyValue], safe=True)

    def tasks(self, *columns):
        return Task.select(*columns).where(Task.queue == self.name)

    def delete(self):
        return Task.delete().where(Task.queue == self.name)

    def schedule(self, *columns):
        return (Schedule
                .select(*columns)
                .where(Schedule.queue == self.name)
                .order_by(Schedule.timestamp))

    def kv(self, *columns):
        return KeyValue.select(*columns).where(KeyValue.queue == self.name)

    def enqueue(self, data):
        Task.create(queue=self.name, data=data)

    def dequeue(self):
        try:
            task = (self
                    .tasks()
                    .order_by(Task.id)
                    .limit(1)
                    .get())
        except Task.DoesNotExist:
            return
        res = self.delete().where(Task.id == task.id).execute()
        if res == 1:
            return task.data

    def unqueue(self, data):
        return (self
                .delete()
                .where(Task.data == data)
                .execute())

    def queue_size(self):
        return self.tasks().count()

    def enqueued_items(self, limit=None):
        query = self.tasks(Task.data).tuples()
        if limit is not None:
            query = query.limit(limit)
        return map(operator.itemgetter(0), query)

    def flush_queue(self):
        self.delete().execute()

    def add_to_schedule(self, data, ts):
        Schedule.create(data=data, timestamp=ts, queue=self.name)

    def read_schedule(self, ts):
        tasks = (self
                 .schedule(Schedule.id, Schedule.data)
                 .where(Schedule.timestamp <= ts)
                 .tuples())
        id_list, data = [], []
        for task_id, task_data in tasks:
            id_list.append(task_id)
            data.append(task_data)
        if id_list:
            (Schedule
             .delete()
             .where(Schedule.id << id_list)
             .execute())
        return data

    def schedule_size(self):
        return self.schedule().count()

    def scheduled_items(self, limit=None):
        tasks = (self
                 .schedule(Schedule.data)
                 .order_by(Schedule.timestamp)
                 .tuples())
        return map(operator.itemgetter(0), tasks)

    def flush_schedule(self):
        return Schedule.delete().where(Schedule.queue == self.name).execute()

    def put_data(self, key, value):
        KeyValue.create(queue=self.name, key=key, value=value)

    def peek_data(self, key):
        try:
            kv = self.kv(KeyValue.value).where(KeyValue.key == key).get()
        except KeyValue.DoesNotExist:
            return EmptyData
        else:
            return kv.value

    def pop_data(self, key):
        try:
            kv = self.kv().where(KeyValue.key == key).get()
        except KeyValue.DoesNotExist:
            return EmptyData
        else:
            dq = KeyValue.delete().where(
                (KeyValue.queue == self.name) &
                (KeyValue.key == key))
            return kv.value if dq.execute() == 1 else EmptyData

    def has_data_for_key(self, key):
        return self.kv().where(KeyValue.key == key).exists()

    def put_if_empty(self, key, value):
        sql = ('INSERT OR ABORT INTO "keyvalue" ("queue", "key", "value") '
               'VALUES (?, ?, ?);')
        try:
            res = self.database.execute_sql(sql, (self.name, key, value))
        except IntegrityError:
            return False
        else:
            return True

    def result_store_size(self):
        return self.kv().count()

    def result_items(self):
        query = self.kv(KeyValue.key, KeyValue.value).tuples()
        return dict((k, pickle.loads(v)) for k, v in query.iterator())

    def flush_results(self):
        return KeyValue.delete().where(KeyValue.queue == self.name).execute()

    def put_error(self, metadata):
        pass

    def get_error(self, limit=None, offset=0):
        pass

    def flush_errors(self):
        pass

    def emit(self, message):
        pass

    def __iter__(self):
        return self

    def next(self):
        raise StopIteration
    __next__ = next


class SqliteHuey(Huey):
    def get_storage(self, filename='huey.db', **sqlite_kwargs):
        return SqliteStorage(
            name=self.name,
            filename=filename,
            **sqlite_kwargs)
