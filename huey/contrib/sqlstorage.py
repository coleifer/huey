import operator
import sys

from peewee import *
from playhouse.db_url import connect as db_url_connect

from huey.api import Huey
from huey.constants import EmptyData
from huey.storage import BaseStorage


class BytesBlobField(BlobField):
    def python_value(self, value):
        return value if isinstance(value, bytes) else bytes(value)


class SqlStorage(BaseStorage):
    def __init__(self, database, name='huey', **kwargs):
        super(SqlStorage, self).__init__(name)

        if isinstance(database, Database):
            self.database = database
        else:
            # Treat database argument as a URL connection string.
            self.database = db_url_connect(database)

        self.KV, self.Schedule, self.Task = self.create_models()
        with self.database:
            self.database.create_tables([self.KV, self.Schedule, self.Task])

    def create_models(self):
        class KV(Model):
            queue = CharField()
            key = CharField()
            value = BytesBlobField()
            class Meta:
                database = self.database
                primary_key = CompositeKey('queue', 'key')

        class Schedule(Model):
            queue = CharField()
            data = BytesBlobField()
            timestamp = TimestampField(resolution=1000)
            class Meta:
                database = self.database
                indexes = ((('queue', 'timestamp'), False),)

        class Task(Model):
            queue = CharField()
            data = BytesBlobField()
            priority = FloatField(default=0.0)
            class Meta:
                database = self.database
                indexes = ((('priority', 'id'), False),)

        return (KV, Schedule, Task)

    def close(self):
        return self.database.close()

    def tasks(self, *columns):
        return self.Task.select(*columns).where(self.Task.queue == self.name)

    def schedule(self, *columns):
        return (self.Schedule.select(*columns)
                .where(self.Schedule.queue == self.name))

    def kv(self, *columns):
        return self.KV.select(*columns).where(self.KV.queue == self.name)

    def enqueue(self, data, priority=None):
        self.Task.create(queue=self.name, data=data, priority=priority or 0)

    def dequeue(self):
        try:
            task = (self.tasks(self.Task.id, self.Task.data)
                    .order_by(self.Task.priority.desc(), self.Task.id)
                    .limit(1)
                    .get())
        except self.Task.DoesNotExist:
            return

        nrows = self.Task.delete().where(self.Task.id == task.id).execute()
        if nrows == 1:
            return task.data

    def queue_size(self):
        return self.tasks().count()

    def enqueued_items(self, limit=None):
        query = self.tasks(self.Task.data).order_by(self.Task.priority.desc(),
                                                    self.Task.id)
        if limit is not None:
            query = query.limit(limit)
        return map(operator.itemgetter(0), query.tuples())

    def flush_queue(self):
        self.Task.delete().where(self.Task.queue == self.name).execute()

    def add_to_schedule(self, data, timestamp):
        self.Schedule.create(queue=self.name, data=data, timestamp=timestamp)

    def read_schedule(self, timestamp):
        query = (self.schedule(self.Schedule.id, self.Schedule.data)
                 .where(self.Schedule.timestamp <= timestamp)
                 .tuples())
        id_list, data = [], []
        for task_id, task_data in query:
            id_list.append(task_id)
            data.append(task_data)

        if id_list:
            (self.Schedule
             .delete()
             .where(self.Schedule.id.in_(id_list))
             .execute())
        return data

    def schedule_size(self):
        return self.schedule().count()

    def scheduled_items(self):
        tasks = (self.schedule(self.Schedule.data)
                 .order_by(self.Schedule.timestamp)
                 .tuples())
        return map(operator.itemgetter(0), tasks)

    def flush_schedule(self):
        (self.Schedule
         .delete()
         .where(self.Schedule.queue == self.name)
         .execute())

    def put_data(self, key, value):
        if isinstance(self.database, PostgresqlDatabase):
            (self.KV
             .insert(queue=self.name, key=key, value=value)
             .on_conflict(conflict_target=[self.KV.queue, self.KV.key],
                          preserve=[self.KV.value])
             .execute())
        else:
            self.KV.replace(queue=self.name, key=key, value=value).execute()

    def peek_data(self, key):
        try:
            kv = self.kv(self.KV.value).where(self.KV.key == key).get()
        except self.KV.DoesNotExist:
            return EmptyData
        else:
            return kv.value

    def pop_data(self, key):
        try:
            kv = self.kv().where(self.KV.key == key).get()
        except self.KV.DoesNotExist:
            return EmptyData
        else:
            dq = self.KV.delete().where(
                (self.KV.queue == self.name) &
                (self.KV.key == key))
            return kv.value if dq.execute() == 1 else EmptyData

    def has_data_for_key(self, key):
        return self.kv().where(self.KV.key == key).exists()

    def put_if_empty(self, key, value):
        try:
            with self.database.atomic():
                self.KV.insert(queue=self.name, key=key, value=value).execute()
        except IntegrityError:
            return False
        else:
            return True

    def result_store_size(self):
        return self.kv().count()

    def result_items(self):
        query = self.kv(self.KV.key, self.KV.value).tuples()
        return dict((k, v) for k, v in query.iterator())

    def flush_results(self):
        self.KV.delete().where(self.KV.queue == self.name).execute()


class SqlHuey(Huey):
    def __init__(self, database, *args, **kwargs):
        # Parameter juju to make database the first required parameter of the
        # SqlHuey object, but then to pass it back to the storage like a
        # regular keyword argument.
        kwargs['database'] = database
        super(SqlHuey, self).__init__(*args, **kwargs)

    def get_storage(self, database=None, **kwargs):
        return SqlStorage(database, name=self.name, **kwargs)
