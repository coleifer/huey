import re
import time

import redis
from redis.exceptions import ConnectionError

from huey.api import Huey
from huey.registry import registry
from huey.utils import EmptyData


def clean_name(name):
    return re.sub('[^a-z0-9]', '', name)


class RedisComponent(object):
    def __init__(self, name, connection_pool, **connection):
        self.name = name
        self.conn = redis.Redis(
            connection_pool=connection_pool,
            **connection)
        self._conn_kwargs = connection

    def convert_ts(self, ts):
        return time.mktime(ts.timetuple())


class RedisQueue(RedisComponent):
    """
    A simple Queue that uses the redis to store messages
    """
    blocking = False

    def __init__(self, name, connection_pool, **connection):
        """
        connection = {
            'host': 'localhost',
            'port': 6379,
            'db': 0,
        }
        """
        super(RedisQueue, self).__init__(name, connection_pool, **connection)
        self.queue_name = 'huey.redis.%s' % clean_name(name)

    def write(self, data):
        self.conn.lpush(self.queue_name, data)

    def read(self):
        return self.conn.rpop(self.queue_name)

    def remove(self, data):
        return self.conn.lrem(self.queue_name, data)

    def flush(self):
        self.conn.delete(self.queue_name)

    def __len__(self):
        return self.conn.llen(self.queue_name)


class RedisBlockingQueue(RedisQueue):
    """
    Use the blocking right pop, should result in messages getting
    executed close to immediately by the consumer as opposed to
    being polled for
    """
    blocking = True

    def __init__(self, name, connection_pool, read_timeout=None, **connection):
        """
        connection = {
            'host': 'localhost',
            'port': 6379,
            'db': 0,
        }
        """
        super(RedisBlockingQueue, self).__init__(
            name, connection_pool, **connection)
        self.read_timeout = read_timeout

    def read(self):
        try:
            return self.conn.brpop(
                self.queue_name,
                timeout=self.read_timeout)[1]
        except (ConnectionError, TypeError, IndexError):
            # unfortunately, there is no way to differentiate a socket timing
            # out and a host being unreachable
            return None


# a custom lua script to pass to redis that will read tasks from the schedule
# and atomically pop them from the sorted set and return them.
# it won't return anything if it isn't able to remove the items it reads.
SCHEDULE_POP_LUA = """
local key = KEYS[1]
local unix_ts = ARGV[1]
local res = redis.call('zrangebyscore', key, '-inf', unix_ts)
if #res and redis.call('zremrangebyscore', key, '-inf', unix_ts) == #res then
    return res
end
"""

class RedisSchedule(RedisComponent):
    def __init__(self, name, connection_pool, **connection):
        super(RedisSchedule, self).__init__(
            name, connection_pool, **connection)

        self.key = 'huey.schedule.%s' % clean_name(name)
        self._pop = self.conn.register_script(SCHEDULE_POP_LUA)

    def add(self, data, ts):
        self.conn.zadd(self.key, data, self.convert_ts(ts))

    def read(self, ts):
        unix_ts = self.convert_ts(ts)
        # invoke the redis lua script that will atomically pop off
        # all the tasks older than the given timestamp
        tasks = self._pop(keys=[self.key], args=[unix_ts])
        return [] if tasks is None else tasks

    def __len__(self):
        return self.conn.zcard(self.key)

    def flush(self):
        self.conn.delete(self.key)


class RedisDataStore(RedisComponent):
    def __init__(self, name, connection_pool, **connection):
        super(RedisDataStore, self).__init__(
            name, connection_pool, **connection)

        self.storage_name = 'huey.results.%s' % clean_name(name)

    def put(self, key, value):
        self.conn.hset(self.storage_name, key, value)

    def peek(self, key):
        if self.conn.hexists(self.storage_name, key):
            return self.conn.hget(self.storage_name, key)
        return EmptyData

    def get(self, key):
        val = self.peek(key)
        if val is not EmptyData:
            self.conn.hdel(self.storage_name, key)
        return val

    def flush(self):
        self.conn.delete(self.storage_name)


class RedisEventEmitter(RedisComponent):
    def __init__(self, name, connection_pool, **connection):
        super(RedisEventEmitter, self).__init__(
            name, connection_pool, **connection)
        self.channel = name

    def emit(self, message):
        self.conn.publish(self.channel, message)

    def listener(self):
        pubsub = self.conn.pubsub()
        pubsub.subscribe([self.channel])
        return pubsub


class RedisHuey(Huey):
    def __init__(self, name='huey', store_none=False, always_eager=False,
                 read_timeout=None, **conn_kwargs):
        self._conn_kwargs = conn_kwargs
        pool = redis.ConnectionPool(**conn_kwargs)
        queue = RedisBlockingQueue(
            name,
            read_timeout=read_timeout,
            connection_pool=pool)
        result_store = RedisDataStore(name, connection_pool=pool)
        schedule = RedisSchedule(name, connection_pool=pool)
        events = RedisEventEmitter(name, connection_pool=pool)
        super(RedisHuey, self).__init__(
            queue=queue,
            result_store=result_store,
            schedule=schedule,
            events=events,
            store_none=store_none,
            always_eager=always_eager)
