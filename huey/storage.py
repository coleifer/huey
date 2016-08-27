import json
import re
import sys
import time

import redis
from redis.exceptions import ConnectionError

from huey.api import Huey
from huey.constants import EmptyData


class BaseStorage(object):
    def __init__(self, name='huey', **storage_kwargs):
        self.name = name

    def enqueue(self, data):
        raise NotImplementedError

    def dequeue(self):
        raise NotImplementedError

    def unqueue(self, data):
        raise NotImplementedError

    def queue_size(self):
        raise NotImplementedError

    def enqueued_items(self, limit=None):
        raise NotImplementedError

    def flush_queue(self):
        raise NotImplementedError

    def add_to_schedule(self, data, ts):
        raise NotImplementedError

    def read_schedule(self, ts):
        raise NotImplementedError

    def schedule_size(self):
        raise NotImplementedError

    def scheduled_items(self, limit=None):
        raise NotImplementedError

    def flush_schedule(self):
        raise NotImplementedError

    def put_data(self, key, value):
        raise NotImplementedError

    def peek_data(self, key):
        raise NotImplementedError

    def pop_data(self, key):
        raise NotImplementedError

    def has_data_for_key(self, key):
        raise NotImplementedError

    def result_store_size(self):
        raise NotImplementedError

    def result_items(self):
        raise NotImplementedError

    def flush_results(self):
        raise NotImplementedError

    def put_error(self, metadata):
        raise NotImplementedError

    def get_errors(self, limit=None, offset=0):
        raise NotImplementedError

    def flush_errors(self):
        raise NotImplementedError

    def emit(self, message):
        raise NotImplementedError

    def __iter__(self):
        # Iterate over consumer-sent events.
        raise NotImplementedError

    def flush_all(self):
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
    def __init__(self, name='huey', blocking=False, read_timeout=1,
                 max_errors=1000, connection_pool=None, url=None,
                 **connection_params):
        if sum(1 for p in (url, connection_pool, connection_params) if p) > 1:
            raise ValueError(
                'The connection configuration is over-determined. '
                'Please specify only one of the the following: '
                '"url", "connection_pool", or "connection_params"')

        if url:
            connection_pool = redis.ConnectionPool.from_url(
                url, decode_components=True)
        elif connection_pool is None:
            connection_pool = redis.ConnectionPool(**connection_params)

        self.pool = connection_pool
        self.conn = redis.Redis(connection_pool=connection_pool)
        self.connection_params = connection_params
        self._pop = self.conn.register_script(SCHEDULE_POP_LUA)

        self.name = self.clean_name(name)
        self.queue_key = 'huey.redis.%s' % self.name
        self.schedule_key = 'huey.schedule.%s' % self.name
        self.result_key = 'huey.results.%s' % self.name
        self.error_key = 'huey.errors.%s' % self.name

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
        self.conn.zadd(self.schedule_key, data, self.convert_ts(ts))

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
