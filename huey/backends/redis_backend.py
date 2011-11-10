import re
import redis
from redis.exceptions import ConnectionError

from huey.backends.base import BaseQueue, BaseDataStore
from huey.utils import EmptyData


class RedisQueue(BaseQueue):
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

        self.conn = redis.Redis(**connection)
    
    def write(self, data):
        self.conn.lpush(self.queue_name, data)
    
    def read(self):
        return self.conn.rpop(self.queue_name)
    
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


class RedisDataStore(BaseDataStore):
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
        self.conn = redis.Redis(**connection)
    
    def put(self, key, value):
        self.conn.hset(self.storage_name, key, value)
    
    def get(self, key):
        val = self.conn.hget(self.storage_name, key)
        if val:
            self.conn.hdel(self.storage_name, key)
        else:
            val = EmptyData
        return val
    
    def flush(self):
        self.conn.delete(self.storage_name)
