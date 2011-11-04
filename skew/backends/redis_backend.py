import re
import redis
from redis.exceptions import ConnectionError

from skew.backends.base import BaseQueue, BaseResultStore


class RedisQueue(BaseQueue):
    """
    A simple Queue that uses the redis to store messages
    """
    def __init__(self, name, connection, **connection_kwargs):
        """
        QUEUE_CONNECTION = 'host:port:database' or defaults to localhost:6379:0
        """
        super(RedisQueue, self).__init__(name, connection)
        
        if not connection:
            connection = 'localhost:6379:0'
        
        self.queue_name = 'skew.redis.%s' % re.sub('[^a-z0-9]', '', name)
        host, port, db = connection.split(':')

        self.conn = redis.Redis(
            host=host, port=int(port), db=int(db), **connection_kwargs
        )
    
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
            return self.conn.brpop(self.queue_name)
        except ConnectionError:
            # unfortunately, there is no way to differentiate a socket timing
            # out and a host being unreachable
            return None


class RedisResultStore(BaseResultStore):
    def __init__(self, name, connection, **connection_kwargs):
        super(RedisResultStore, self).__init__(name, connection)
        
        if not connection:
            connection = 'localhost:6379:0'
        
        self.storage_name = 'skew.redis.results.%s' % re.sub('[^a-z0-9]', '', name)
        host, port, db = connection.split(':')

        self.conn = redis.Redis(
            host=host, port=int(port), db=int(db), **connection_kwargs
        )
    
    def put(self, task_id, value):
        self.conn.hset(self.storage_name, task_id, value)
    
    def get(self, task_id):
        val = self.conn.hget(self.storage_name, task_id)
        if val:
            self.conn.hdel(self.storage_name, task_id)
        else:
            val = EmptyResult
        return val
