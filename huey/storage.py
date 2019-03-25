from collections import deque
import contextlib
import heapq
import json
import re
try:
    import sqlite3
except ImportError:
    sqlite3 = None
import threading
import time

try:
    from redis import ConnectionPool
    try:
        from redis import StrictRedis as Redis
    except ImportError:
        from redis import Redis
    from redis.exceptions import ConnectionError
except ImportError:
    ConnectionPool = Redis = ConnectionError = None

from huey.constants import EmptyData
from huey.exceptions import ConfigurationError
from huey.utils import to_timestamp


class BaseStorage(object):
    blocking = False  # Does dequeue() block until ready, or should we poll?

    def __init__(self, name='huey', **storage_kwargs):
        self.name = name

    def enqueue(self, data):
        """
        Given an opaque chunk of data, add it to the queue.

        :param bytes data: Task data.
        :return: No return value.
        """
        raise NotImplementedError

    def dequeue(self):
        """
        Atomically remove data from the queue. If no data is available, no data
        is returned.

        :return: Opaque binary task data or None if queue is empty.
        """
        raise NotImplementedError

    def unqueue(self, data):
        """
        Atomically remove the given data from the queue, if it is present. This
        method is used to "delete" a task without executing it. It is not
        expected that this method will be used very often. Up to the
        implementation whether more than one instance of the task can be
        deleted, but typically each chunk of data is unique because it has a
        UUID4 task id.

        :param bytes data: Task data to remove.
        :return: Number of tasks deleted.
        """
        raise NotImplementedError

    def queue_size(self):
        """
        Return the length of the queue.

        :return: Number of tasks.
        """
        raise NotImplementedError

    def enqueued_items(self, limit=None):
        """
        Non-destructively read the given number of tasks from the queue. If no
        limit is specified, all tasks will be read.

        :param int limit: Restrict the number of tasks returned.
        :return: A list containing opaque binary task data.
        """
        raise NotImplementedError

    def flush_queue(self):
        """
        Remove all data from the queue.

        :return: No return value.
        """
        raise NotImplementedError

    def add_to_schedule(self, data, ts):
        """
        Add the given task data to the schedule, to be executed at the given
        timestamp.

        :param bytes data: Task data.
        :param datetime ts: Timestamp at which task should be executed.
        :return: No return value.
        """
        raise NotImplementedError

    def read_schedule(self, ts):
        """
        Read all tasks from the schedule that should be executed at or before
        the given timestamp. Once read, the tasks are removed from the
        schedule.

        :param datetime ts: Timestamp
        :return: List containing task data for tasks which should be executed
                 at or before the given timestamp.
        """
        raise NotImplementedError

    def schedule_size(self):
        """
        :return: The number of tasks currently in the schedule.
        """
        raise NotImplementedError

    def scheduled_items(self, limit=None):
        """
        Non-destructively read the given number of tasks from the schedule.

        :param int limit: Restrict the number of tasks returned.
        :return: List of tasks that are in schedule, in order from soonest to
                 latest.
        """
        raise NotImplementedError

    def flush_schedule(self):
        """
        Delete all scheduled tasks.

        :return: No return value.
        """
        raise NotImplementedError

    def put_data(self, key, value):
        """
        Store an arbitrary key/value pair.

        :param bytes key: lookup key
        :param bytes value: value
        :return: No return value.
        """
        raise NotImplementedError

    def peek_data(self, key):
        """
        Non-destructively read the value at the given key, if it exists.

        :param bytes key: Key to read.
        :return: Associated value, if key exists, or ``EmptyData``.
        """
        raise NotImplementedError

    def pop_data(self, key):
        """
        Destructively read the value at the given key, if it exists.

        :param bytes key: Key to read.
        :return: Associated value, if key exists, or ``EmptyData``.
        """
        raise NotImplementedError

    def has_data_for_key(self, key):
        """
        Return whether there is data for the given key.

        :return: Boolean value.
        """
        raise NotImplementedError

    def put_if_empty(self, key, value):
        """
        Atomically write data only if the key is not already set.

        :param bytes key: Key to check/set.
        :param bytes value: Arbitrary data.
        :return: Boolean whether key/value was set.
        """
        if self.has_data_for_key(key):
            return False
        self.put_data(key, value)
        return True

    def result_store_size(self):
        """
        :return: Number of key/value pairs in the result store.
        """
        raise NotImplementedError

    def result_items(self):
        """
        Non-destructively read all the key/value pairs from the data-store.

        :return: Dictionary mapping all key/value pairs in the data-store.
        """
        raise NotImplementedError

    def flush_results(self):
        """
        Delete all key/value pairs from the data-store.

        :return: No return value.
        """
        raise NotImplementedError

    def flush_all(self):
        """
        Remove all persistent or semi-persistent data.

        :return: No return value.
        """
        self.flush_queue()
        self.flush_schedule()
        self.flush_results()


class BlackHoleStorage(BaseStorage):
    def enqueue(self, data): pass
    def dequeue(self): pass
    def unqueue(self, data): pass
    def queue_size(self): return 0
    def enqueued_items(self, limit=None): return []
    def flush_queue(self): pass
    def add_to_schedule(self, data, ts): pass
    def read_schedule(self, ts): return []
    def schedule_size(self): return 0
    def scheduled_items(self, limit=None): return []
    def flush_schedule(self): pass
    def put_data(self, key, value): pass
    def peek_data(self, key): return EmptyData
    def pop_data(self, key): return EmptyData
    def has_data_for_key(self, key): return False
    def result_store_size(self): return 0
    def result_items(self): return {}
    def flush_results(self): pass


class MemoryStorage(BaseStorage):
    def __init__(self, *args, **kwargs):
        super(MemoryStorage, self).__init__(*args, **kwargs)
        self._queue = deque()
        self._results = {}
        self._schedule = []
        self._lock = threading.RLock()

    def enqueue(self, data):
        self._queue.append(data)

    def dequeue(self):
        with self._lock:
            if self._queue:
                return self._queue.popleft()

    def unqueue(self, data):
        try:
            self._queue.remove(data)
        except ValueError:
            pass

    def queue_size(self):
        return len(self._queue)

    def enqueued_items(self, limit=None):
        items = list(self._queue)
        if limit:
            items = items[:limit]
        return items

    def flush_queue(self):
        self._queue = deque()

    def add_to_schedule(self, data, ts):
        heapq.heappush(self._schedule, (ts, data))

    def read_schedule(self, ts):
        with self._lock:
            accum = []
            while self._schedule:
                sts, data = heapq.heappop(self._schedule)
                if sts <= ts:
                    accum.append(data)
                else:
                    heapq.heappush(self._schedule, (sts, data))
                    break

        return accum

    def schedule_size(self):
        return len(self._schedule)

    def scheduled_items(self, limit=None):
        items = sorted(data for _, data in self._schedule)
        if limit:
            items = items[:limit]
        return items

    def flush_schedule(self):
        self._schedule = []

    def put_data(self, key, value):
        self._results[key] = value

    def peek_data(self, key):
        return self._results.get(key, EmptyData)

    def pop_data(self, key):
        return self._results.pop(key, EmptyData)

    def has_data_for_key(self, key):
        return key in self._results

    def result_store_size(self):
        return len(self._results)

    def result_items(self):
        return dict(self._results)

    def flush_results(self):
        self._results = {}


# A custom lua script to pass to redis that will read tasks from the schedule
# and atomically pop them from the sorted set and return them. It won't return
# anything if it isn't able to remove the items it reads.
SCHEDULE_POP_LUA = """\
local key = KEYS[1]
local unix_ts = ARGV[1]
local res = redis.call('zrangebyscore', key, '-inf', unix_ts)
if #res and redis.call('zremrangebyscore', key, '-inf', unix_ts) == #res then
    return res
end"""


class RedisStorage(BaseStorage):
    redis_client = Redis

    def __init__(self, name='huey', blocking=True, read_timeout=1,
                 max_errors=1000, connection_pool=None, url=None,
                 client_name=None, **connection_params):

        if Redis is None:
            raise ConfigurationError('"redis" python module not found, cannot '
                                     'use Redis storage backend. Run "pip '
                                     'install redis" to install.')

        if sum(1 for p in (url, connection_pool, connection_params) if p) > 1:
            raise ConfigurationError(
                'The connection configuration is over-determined. '
                'Please specify only one of the the following: '
                '"url", "connection_pool", or "connection_params"')

        if url:
            connection_pool = ConnectionPool.from_url(
                url, decode_components=True)
        elif connection_pool is None:
            connection_pool = ConnectionPool(**connection_params)

        self.pool = connection_pool
        self.conn = self.redis_client(connection_pool=connection_pool)
        self.connection_params = connection_params
        self._pop = self.conn.register_script(SCHEDULE_POP_LUA)

        self.name = self.clean_name(name)
        self.queue_key = 'huey.redis.%s' % self.name
        self.schedule_key = 'huey.schedule.%s' % self.name
        self.result_key = 'huey.results.%s' % self.name
        self.error_key = 'huey.errors.%s' % self.name

        if client_name is not None:
            self.conn.client_setname(client_name)

        self.blocking = blocking
        self.read_timeout = read_timeout
        self.max_errors = max_errors

    def clean_name(self, name):
        return re.sub('[^a-z0-9]', '', name)

    def convert_ts(self, ts):
        return time.mktime(ts.timetuple())

    def enqueue(self, data):
        self.conn.lpush(self.queue_key, data)

    def dequeue(self):
        if self.blocking:
            try:
                return self.conn.brpop(
                    self.queue_key,
                    timeout=self.read_timeout)[1]
            except (ConnectionError, TypeError, IndexError):
                # Unfortunately, there is no way to differentiate a socket
                # timing out and a host being unreachable.
                return None
        else:
            return self.conn.rpop(self.queue_key)

    def unqueue(self, data):
        return self.conn.lrem(self.queue_key, 0, data)

    def queue_size(self):
        return self.conn.llen(self.queue_key)

    def enqueued_items(self, limit=None):
        limit = limit or -1
        return self.conn.lrange(self.queue_key, 0, limit)[::-1]

    def flush_queue(self):
        self.conn.delete(self.queue_key)

    def add_to_schedule(self, data, ts):
        self.conn.zadd(self.schedule_key, {data: self.convert_ts(ts)})

    def read_schedule(self, ts):
        unix_ts = self.convert_ts(ts)
        # invoke the redis lua script that will atomically pop off
        # all the tasks older than the given timestamp
        tasks = self._pop(keys=[self.schedule_key], args=[unix_ts])
        return [] if tasks is None else tasks

    def schedule_size(self):
        return self.conn.zcard(self.schedule_key)

    def scheduled_items(self, limit=None):
        limit = limit or -1
        return self.conn.zrange(self.schedule_key, 0, limit, withscores=False)

    def flush_schedule(self):
        self.conn.delete(self.schedule_key)

    def put_data(self, key, value):
        self.conn.hset(self.result_key, key, value)

    def peek_data(self, key):
        pipe = self.conn.pipeline()
        pipe.hexists(self.result_key, key)
        pipe.hget(self.result_key, key)
        exists, val = pipe.execute()
        return EmptyData if not exists else val

    def pop_data(self, key):
        pipe = self.conn.pipeline()
        pipe.hexists(self.result_key, key)
        pipe.hget(self.result_key, key)
        pipe.hdel(self.result_key, key)
        exists, val, n = pipe.execute()
        return EmptyData if not exists else val

    def has_data_for_key(self, key):
        return self.conn.hexists(self.result_key, key)

    def put_if_empty(self, key, value):
        return self.conn.hsetnx(self.result_key, key, value)

    def result_store_size(self):
        return self.conn.hlen(self.result_key)

    def result_items(self):
        return self.conn.hgetall(self.result_key)

    def flush_results(self):
        self.conn.delete(self.result_key)


class _ConnectionState(object):
    def __init__(self, **kwargs):
        super(_ConnectionState, self).__init__(**kwargs)
        self.reset()
    def reset(self):
        self.conn = None
        self.closed = True
    def set_connection(self, conn):
        self.conn = conn
        self.closed = False
class _ConnectionLocal(_ConnectionState, threading.local): pass

# Python 2.x may return <buffer> object for BLOB columns.
to_bytes = lambda b: bytes(b) if not isinstance(b, bytes) else b
to_blob = lambda b: sqlite3.Binary(b)


class SqliteStorage(BaseStorage):
    table_kv = ('create table if not exists kv ('
                'queue text not null, key text not null, value blob not null, '
                'primary key(queue, key))')
    table_sched = ('create table if not exists schedule ('
                   'id integer not null primary key, queue text not null, '
                   'data blob not null, timestamp real not null)')
    index_sched = ('create index if not exists schedule_queue_timestamp '
                   'on schedule (queue, timestamp)')
    table_task = ('create table if not exists task ('
                  'id integer not null primary key, queue text not null, '
                  'data blob not null)')
    ddl = [table_kv, table_sched, index_sched, table_task]

    def __init__(self, filename='huey.db', name='huey', cache_mb=8,
                 fsync=False, **kwargs):
        super(SqliteStorage, self).__init__(name)
        self.filename = filename
        self._cache_mb = cache_mb
        self._fsync = fsync
        self._conn_kwargs = kwargs
        self._state = _ConnectionLocal()
        self.initialize_schema()

    def close(self):
        if self._state.closed: return False
        self._state.conn.close()
        self._state.reset()
        return True

    @property
    def conn(self):
        if self._state.closed:
            self._state.set_connection(self._create_connection())
        return self._state.conn

    def _create_connection(self):
        conn = sqlite3.connect(self.filename, timeout=5, **self._conn_kwargs)
        conn.isolation_level = None  # Autocommit mode.
        if self._cache_mb:
            conn.execute('pragma cache_size=%s' % (-1000 * self._cache_mb))
        conn.execute('pragma synchronous=%s' % (2 if self._fsync else 0))
        return conn

    @contextlib.contextmanager
    def db(self, commit=False, close=False):
        conn = self.conn
        try:
            if commit: conn.execute('begin exclusive')
            yield conn
        except Exception:
            if commit: conn.rollback()
            raise
        else:
            if commit: conn.commit()
        finally:
            if close:
                conn.close()
                self._state.reset()

    def initialize_schema(self):
        with self.db(commit=True, close=True) as conn:
            for sql in self.ddl:
                conn.execute(sql)

    def enqueue(self, data):
        with self.db(commit=True) as conn:
            conn.execute('insert into task (queue, data) values (?, ?)',
                         (self.name, to_blob(data)))

    def dequeue(self):
        with self.db(commit=True) as conn:
            curs = conn.execute('select id, data from task where queue = ? '
                                'order by id limit 1', (self.name,))
            result = curs.fetchone()
            if result is not None:
                tid, data = result
                curs = conn.execute('delete from task where id = ?', (tid,))
                if curs.rowcount == 1:
                    return to_bytes(data)

    def unqueue(self, data):
        with self.db(commit=True) as conn:
            conn.execute('delete from task where queue = ? and data = ?',
                         (self.name, to_blob(data)))

    def queue_size(self):
        with self.db() as conn:
            curs = conn.execute('select count(id) from task where queue = ?',
                                (self.name,))
            return curs.fetchone()[0]

    def enqueued_items(self, limit=None):
        with self.db() as conn:
            sql = 'select data from task where queue = ? order by id'
            if limit is None:
                params = (self.name,)
            else:
                sql += ' limit ?'
                params = (self.name, limit)
            curs = conn.execute(sql, params)
            return [to_bytes(data) for data, in curs.fetchall()]

    def flush_queue(self):
        with self.db(commit=True) as conn:
            conn.execute('delete from task where queue = ?', (self.name,))

    def add_to_schedule(self, data, ts):
        with self.db(commit=True) as conn:
            data = to_blob(data)
            ts = to_timestamp(ts)
            conn.execute('insert into schedule (queue, data, timestamp) '
                         'values (?, ?, ?)', (self.name, data, ts))

    def read_schedule(self, ts):
        with self.db(commit=True) as conn:
            params = (self.name, to_timestamp(ts))
            curs = conn.execute('select id, data from schedule where '
                                'queue = ? and timestamp <= ?', params)
            id_list, data = [], []
            for task_id, task_data in curs.fetchall():
                id_list.append(task_id)
                data.append(to_bytes(task_data))
            if id_list:
                plist = ','.join('?' * len(id_list))
                conn.execute('delete from schedule where id IN (%s)' % plist,
                             id_list)
            return data

    def schedule_size(self):
        with self.db() as conn:
            curs = conn.execute('select count(id) from schedule '
                                'where queue = ?', (self.name,))
            return curs.fetchone()[0]

    def scheduled_items(self, limit=None):
        with self.db() as conn:
            sql = 'select data from schedule where queue=? order by timestamp'
            if limit is None:
                params = (self.name,)
            else:
                params = (self.name, limit)
                sql += ' limit ?'
            curs = conn.execute(sql, params)
            return [to_bytes(data) for data, in curs.fetchall()]

    def flush_schedule(self):
        with self.db(commit=True) as conn:
            conn.execute('delete from schedule where queue = ?', (self.name,))

    def put_data(self, key, value):
        with self.db(commit=True) as conn:
            conn.execute('insert or replace into kv (queue, key, value) '
                         'values (?, ?, ?)', (self.name, key, to_blob(value)))

    def peek_data(self, key):
        with self.db() as conn:
            curs = conn.execute('select value from kv where queue = ? '
                                'and key = ?', (self.name, key))
            result = curs.fetchone()
            if result is None:
                return EmptyData
            return to_bytes(result[0])

    def pop_data(self, key):
        with self.db(commit=True) as conn:
            curs = conn.execute('select value from kv where queue = ? '
                                'and key = ?', (self.name, key))
            result = curs.fetchone()
            if result is not None:
                curs = conn.execute('delete from kv where queue=? and key=?',
                                    (self.name, key))
                if curs.rowcount == 1:
                    return to_bytes(result[0])
            return EmptyData

    def has_data_for_key(self, key):
        with self.db() as conn:
            curs = conn.execute('select 1 from kv where queue=? and key=?',
                                (self.name, key))
            return curs.fetchone() is not None

    def put_if_empty(self, key, value):
        try:
            with self.db(commit=True) as conn:
                conn.execute('insert or abort into kv '
                             '(queue, key, value) values (?, ?, ?)',
                             (self.name, key, to_blob(value)))
        except sqlite3.IntegrityError:
            return False
        else:
            return True

    def result_store_size(self):
        with self.db() as conn:
            curs = conn.execute('select count(*) from kv where queue = ?',
                                (self.name,))
            return curs.fetchone()[0]

    def result_items(self):
        with self.db() as conn:
            curs = conn.execute('select key, value from kv where queue = ?',
                                (self.name,))
            return dict((k, to_bytes(v)) for k, v in curs.fetchall())

    def flush_results(self):
        with self.db(commit=True) as conn:
            conn.execute('delete from kv where queue = ?', (self.name,))
