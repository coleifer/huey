import re
import time

import redis
from redis.exceptions import ConnectionError

from huey.backends.base import BaseDataStore
from huey.backends.base import BaseEventEmitter
from huey.backends.base import BaseQueue
from huey.backends.base import BaseSchedule
from huey.utils import EmptyData

def clean_name(name):
    return re.sub('[^a-z0-9]', '', name)


def loop_conn(self):
    try:
        self.conn.ping()
    except:
        self.conn = redis.Redis(**self.queue_conn)
    return self.conn
    

class RedisQueue(BaseQueue):
    """
    A simple Queue that uses the redis to store messages
    """
    def __init__(self, name, **connection):
        """
        connection = {
            'host': 'localhost',
            'port': 6379,
            'db': 0,
        }
        """
        super(RedisQueue, self).__init__(name, **connection)

        self.queue_name = 'huey.redis.%s' % clean_name(name)
        self.queue_conn = connection
        self.loop_conn = loop_conn

    def write(self, data):
        self.loop_conn(self).lpush(self.queue_name, data)

    def read(self):
        return self.loop_conn(self).rpop(self.queue_name)

    def remove(self, data):
        return self.loop_conn(self).lrem(self.queue_name, data)

    def flush(self):
        self.loop_conn(self).delete(self.queue_name)

    def __len__(self):
        return self.loop_conn(self).llen(self.queue_name)


class RedisBlockingQueue(RedisQueue):
    """
    Use the blocking right pop, should result in messages getting
    executed close to immediately by the consumer as opposed to
    being polled for
    """
    blocking = True

    def read(self):
        try:
            return self.loop_conn(self).brpop(self.queue_name)[1]
        except ConnectionError:
            # unfortunately, there is no way to differentiate a socket timing
            # out and a host being unreachable
            return None


class RedisSchedule(BaseSchedule):
    def __init__(self, name, **connection):
        super(RedisSchedule, self).__init__(name, **connection)

        self.key = 'huey.schedule.%s' % clean_name(name)
        self.queue_conn = connection
        self.loop_conn = loop_conn

    def convert_ts(self, ts):
        return time.mktime(ts.timetuple())

    def add(self, data, ts):
        self.loop_conn(self).zadd(self.key, data, self.convert_ts(ts))

    def read(self, ts):
        unix_ts = self.convert_ts(ts)
        tasks = self.loop_conn(self).zrangebyscore(self.key, 0, unix_ts)
        if len(tasks):
            self.loop_conn(self).zremrangebyscore(self.key, 0, unix_ts)
        return tasks

    def flush(self):
        self.loop_conn(self).delete(self.key)


class RedisDataStore(BaseDataStore):
    def __init__(self, name, **connection):
        super(RedisDataStore, self).__init__(name, **connection)

        self.storage_name = 'huey.results.%s' % clean_name(name)
        self.queue_conn = connection
        self.loop_conn = loop_conn

    def put(self, key, value):
        self.loop_conn(self).hset(self.storage_name, key, value)

    def peek(self, key):
        if self.loop_conn(self).hexists(self.storage_name, key):
            return self.loop_conn(self).hget(self.storage_name, key)
        return EmptyData

    def get(self, key):
        val = self.peek(key)
        if val is not EmptyData:
            self.loop_conn(self).hdel(self.storage_name, key)
        return val

    def flush(self):
        self.loop_conn(self).delete(self.storage_name)


class RedisEventEmitter(BaseEventEmitter):
    def __init__(self, channel, **connection):
        super(RedisEventEmitter, self).__init__(channel, **connection)
        self.queue_conn = connection
        self.loop_conn = loop_conn

    def emit(self, message):
        self.loop_conn(self).publish(self.channel, message)


Components = (RedisBlockingQueue, RedisDataStore, RedisSchedule,
              RedisEventEmitter)
