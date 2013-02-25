import re
import redis
from redis.exceptions import ConnectionError
from UserDict import DictMixin

from huey.backends.base import BaseQueue, BaseDataStore
from huey.utils import EmptyData


class RedisPicklable(object):
    @property
    def conn(self):
        conn = getattr(self, '_conn', None)
        if not conn:
            self._conn = redis.Redis(**self.conn_info)
        return self._conn

    # skip self.conn on pickle
    def __getstate__(self):
        state = self.__dict__.copy()
        if '_conn' in state:
            del state['_conn']
        return state

class RedisQueue(RedisPicklable, BaseQueue):
    """
    A simple Queue that uses the redis to store messages
    """
    def __init__(self, name, **connection):
        """
        QUEUE_CONNECTION = {
            'host': 'localhost',
            'port': 6379,
            'db': 0,
        }
        """
        super(RedisQueue, self).__init__(name, **connection)

        self.queue_name = 'huey.redis.%s' % re.sub('[^a-z0-9]', '', name)

        self.conn_info = connection

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

    def read(self):
        try:
            return self.conn.brpop(self.queue_name)[1]
        except ConnectionError:
            # unfortunately, there is no way to differentiate a socket timing
            # out and a host being unreachable
            return None


class RedisDataStore(RedisPicklable, BaseDataStore):
    def __init__(self, name, **connection):
        """
        RESULT_STORE_CONNECTION = {
            'host': 'localhost',
            'port': 6379,
            'db': 0,
        }
        """
        super(RedisDataStore, self).__init__(name, **connection)

        self.storage_name = 'huey.redis.results.%s' % re.sub('[^a-z0-9]', '', name)

        self.conn_info = connection

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

    def count(self):
        return self.conn.hlen(self.storage_name)

class RedisDict(RedisDataStore, DictMixin):
    def __getitem__(self, key):
        val = self.peek(key)
        if val is EmptyData:
            raise KeyError(key)
        return val

    def __setitem__(self, key, val):
        self.put(key, val)

    def __delitem__(self, key):
        if self.__contains__(key):
            self.conn.hdel(self.storage_name, key)
        else:
            raise KeyError(key)

    def __contains__(self, key):
        return self.conn.hexists(self.storage_name, key)

    def __iter__(self):
        for k in self.conn.hkeys(self.storage_name):
            yield k

    def keys(self):
        return self.conn.hkeys(self.storage_name)

    def iteritems(self):
        return self.conn.hgetall(self.storage_name).iteritems()

    def clear(self):
        return self.flush()