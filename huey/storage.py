import json
import re
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

from huey.api import Huey
from huey.constants import EmptyData


class BaseStorage(object):
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

    def put_error(self, metadata):
        """
        Log an error in the error store. The ``max_errors`` parameter is used
        to prevent the error store from growing without bounds.

        :param metadata: Store the metadata in the error store.
        :return: No return value.
        """
        raise NotImplementedError

    def get_errors(self, limit=None, offset=0):
        """
        Non-destructively read error data from the error store.

        :param int limit: Restrict number of rows returned.
        :param int offset: Start reading at the given offset.
        :return: List of error metadata.
        """
        raise NotImplementedError

    def flush_errors(self):
        """
        Delete all error metadata from the error store.

        :return: No return value.
        """
        raise NotImplementedError

    def emit(self, message):
        """
        Publish a message from the consumer.
        """
        raise NotImplementedError

    def __iter__(self):
        """
        Successively yield events emitted by the huey consumer(s).

        :return: Iterator that yields consumer event metadata.
        """
        # Iterate over consumer-sent events.
        raise NotImplementedError

    def flush_all(self):
        """
        Remove all persistent or semi-persistent data.

        :return: No return value.
        """
        self.flush_queue()
        self.flush_schedule()
        self.flush_results()
        self.flush_errors()


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

    def __init__(self, name='huey', blocking=False, read_timeout=1,
                 max_errors=1000, connection_pool=None, url=None,
                 client_name=None, **connection_params):

        if Redis is None:
            raise ImportError('"redis" python module not found, cannot use '
                              'Redis storage backend. Run "pip install redis" '
                              'to install.')

        if sum(1 for p in (url, connection_pool, connection_params) if p) > 1:
            raise ValueError(
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
        return self.conn.lrem(self.queue_key, data)

    def queue_size(self):
        return self.conn.llen(self.queue_key)

    def enqueued_items(self, limit=None):
        limit = limit or -1
        return self.conn.lrange(self.queue_key, 0, limit)

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

    def put_error(self, metadata):
        self.conn.lpush(self.error_key, metadata)
        if self.conn.llen(self.error_key) > self.max_errors:
            self.conn.ltrim(self.error_key, 0, int(self.max_errors * .9))

    def get_errors(self, limit=None, offset=0):
        if limit is None:
            limit = -1
        return self.conn.lrange(self.error_key, offset, limit)

    def flush_errors(self):
        self.conn.delete(self.error_key)

    def emit(self, message):
        self.conn.publish(self.name, message)

    def listener(self):
        """
        Create a channel for listening to raw event data.

        :return: a Redis pubsub object.
        """
        pubsub = self.conn.pubsub()
        pubsub.subscribe([self.name])
        return pubsub

    def __iter__(self):
        return _EventIterator(self.listener())


class _EventIterator(object):
    def __init__(self, pubsub):
        self.listener = pubsub.listen()
        next(self.listener)

    def next(self):
        return json.loads(next(self.listener)['data'].decode('utf-8'))

    __next__ = next


class RedisHuey(Huey):
    def get_storage(self, read_timeout=1, max_errors=1000,
                    connection_pool=None, url=None, **connection_params):
        return RedisStorage(
            name=self.name,
            blocking=self.blocking,
            read_timeout=read_timeout,
            max_errors=max_errors,
            connection_pool=connection_pool,
            url=url,
            **connection_params)
