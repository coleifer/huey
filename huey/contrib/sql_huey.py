from functools import partial
import operator

from peewee import *
from playhouse.db_url import connect as db_url_connect

from huey.api import Huey
from huey.constants import EmptyData
from huey.exceptions import ConfigurationError
from huey.storage import BaseStorage


class BytesBlobField(BlobField):
    def python_value(self, value):
        return value if isinstance(value, bytes) else bytes(value)


class SqlStorage(BaseStorage):
    def __init__(self, name='huey', database=None, **kwargs):
        super(SqlStorage, self).__init__(name)

        if database is None:
            raise ConfigurationError('Use of SqlStorage requires a '
                                     'database= argument, which should be a '
                                     'peewee database or a connection string.')

        if isinstance(database, Database):
            self.database = database
        else:
            # Treat database argument as a URL connection string.
            self.database = db_url_connect(database)

        self.KV, self.Schedule, self.Task = self.create_models()
        self.create_tables()

        # Check for FOR UPDATE SKIP LOCKED support.
        if isinstance(self.database, PostgresqlDatabase):
            self.for_update = 'FOR UPDATE SKIP LOCKED'
        elif isinstance(self.database, MySQLDatabase):
            self.for_update = 'FOR UPDATE SKIP LOCKED'  # Assume support.
            # Try to determine if we're using MariaDB or MySQL.
            version, = self.database.execute_sql('select version()').fetchone()
            if 'mariadb' in str(version).lower():
                # MariaDB added support in 10.6.0.
                if self.database.server_version < (10, 6):
                    self.for_update = 'FOR UPDATE'
            elif self.database.server_version < (8, 0, 1):
                # MySQL added support in 8.0.1.
                self.for_update = 'FOR UPDATE'
        else:
            self.for_update = None

    def create_models(self):
        class Base(Model):
            class Meta:
                database = self.database

        class KV(Base):
            queue = CharField()
            key = CharField()
            value = BytesBlobField()
            class Meta:
                primary_key = CompositeKey('queue', 'key')

        class Schedule(Base):
            queue = CharField()
            data = BytesBlobField()
            timestamp = TimestampField(resolution=1000)
            class Meta:
                indexes = ((('queue', 'timestamp'), False),)

        class Task(Base):
            queue = CharField()
            data = BytesBlobField()
            priority = FloatField(default=0.0)

        Task.add_index(Task.priority.desc(), Task.id)

        return (KV, Schedule, Task)

    def create_tables(self):
        with self.database:
            self.database.create_tables([self.KV, self.Schedule, self.Task])

    def drop_tables(self):
        with self.database:
            self.database.drop_tables([self.KV, self.Schedule, self.Task])

    def close(self):
        return self.database.close()

    def tasks(self, *columns):
        return self.Task.select(*columns).where(self.Task.queue == self.name)

    def schedule(self, *columns):
        return (self.Schedule.select(*columns)
                .where(self.Schedule.queue == self.name))

    def kv(self, *columns):
        return self.KV.select(*columns).where(self.KV.queue == self.name)

    def check_conn(self):
        if not self.database.is_connection_usable():
            self.database.close()
            self.database.connect()

    def enqueue(self, data, priority=None):
        self.check_conn()
        self.Task.create(queue=self.name, data=data, priority=priority or 0)

    def dequeue(self):
        self.check_conn()
        query = (self.tasks(self.Task.id, self.Task.data)
                 .order_by(self.Task.priority.desc(), self.Task.id)
                 .limit(1))
        if self.for_update:
            query = query.for_update(self.for_update)

        with self.database.atomic():
            try:
                task = query.get()
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
        return list(map(operator.itemgetter(0), query.tuples()))

    def flush_queue(self):
        self.Task.delete().where(self.Task.queue == self.name).execute()

    def add_to_schedule(self, data, timestamp):
        self.check_conn()
        self.Schedule.create(queue=self.name, data=data, timestamp=timestamp)

    def read_schedule(self, timestamp):
        self.check_conn()
        query = (self.schedule(self.Schedule.id, self.Schedule.data)
                 .where(self.Schedule.timestamp <= timestamp)
                 .tuples())
        if self.for_update:
            query = query.for_update(self.for_update)

        with self.database.atomic():
            results = list(query)
            if not results:
                return []

            id_list, data = zip(*results)
            (self.Schedule
             .delete()
             .where(self.Schedule.id.in_(id_list))
             .execute())

            return list(data)

    def schedule_size(self):
        return self.schedule().count()

    def scheduled_items(self, limit=None):
        tasks = (self.schedule(self.Schedule.data)
                 .order_by(self.Schedule.timestamp)
                 .tuples())
        if limit:
            tasks = tasks.limit(limit)
        return list(map(operator.itemgetter(0), tasks))

    def flush_schedule(self):
        (self.Schedule
         .delete()
         .where(self.Schedule.queue == self.name)
         .execute())

    def put_data(self, key, value, is_result=False):
        self.check_conn()
        if isinstance(self.database, PostgresqlDatabase):
            (self.KV
             .insert(queue=self.name, key=key, value=value)
             .on_conflict(conflict_target=[self.KV.queue, self.KV.key],
                          preserve=[self.KV.value])
             .execute())
        else:
            self.KV.replace(queue=self.name, key=key, value=value).execute()

    def peek_data(self, key):
        self.check_conn()
        try:
            kv = self.kv(self.KV.value).where(self.KV.key == key).get()
        except self.KV.DoesNotExist:
            return EmptyData
        else:
            return kv.value

    def pop_data(self, key):
        self.check_conn()
        query = self.kv().where(self.KV.key == key)
        if self.for_update:
            query = query.for_update(self.for_update)

        with self.database.atomic():
            try:
                kv = query.get()
            except self.KV.DoesNotExist:
                return EmptyData
            else:
                dq = self.KV.delete().where(
                    (self.KV.queue == self.name) &
                    (self.KV.key == key))
                return kv.value if dq.execute() == 1 else EmptyData

    def has_data_for_key(self, key):
        self.check_conn()
        return self.kv().where(self.KV.key == key).exists()

    def put_if_empty(self, key, value):
        self.check_conn()
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


SqlHuey = partial(Huey, storage_class=SqlStorage)
