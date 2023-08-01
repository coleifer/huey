from functools import wraps
import time
import uuid

from huey import RedisHuey
from huey.exceptions import TaskLockedException


class RedisSemaphore(object):
    """
    Extremely basic semaphore for use with Redis.
    """
    def __init__(self, huey, name, value=1, timeout=None):
        if not isinstance(huey, RedisHuey):
            raise ValueError('Semaphore is only supported for Redis.')
        self.huey = huey
        self.key = '%s.lock.%s' % (huey.name, name)
        self.value = value
        self.timeout = timeout or 86400  # Set a max age for lock holders.

        self.huey._locks.add(self.key)
        self._conn = self.huey.storage.conn

    def acquire(self, name=None):
        name = name or str(uuid.uuid4())
        ts = time.time()
        pipeline = self._conn.pipeline(True)
        pipeline.zremrangebyscore(self.key, '-inf', ts - self.timeout)
        pipeline.zadd(self.key, {name: ts})
        pipeline.zrank(self.key, name)  # See whether we acquired.
        if pipeline.execute()[-1] < self.value:
            return name
        self._conn.zrem(self.key, name)
        return

    def release(self, name):
        return self._conn.zrem(self.key, name)


def lock_task_semaphore(huey, lock_name, value=1, timeout=None):
    """
    Lock which can be acquired multiple times (default = 1).

    NOTE: no provisions are made for blocking, waiting, or notifying. This is
    just a lock which can be acquired a configurable number of times.

    Example:

    # Allow up to 3 workers to run this task concurrently. If the task is
    # locked, retry up to 2 times with a delay of 60s.
    @huey.task(retries=2, retry_delay=60)
    @lock_task_semaphore(huey, 'my-lock', 3)
    def my_task():
        ...
    """
    sem = RedisSemaphore(huey, lock_name, value, timeout)
    def decorator(fn):
        @wraps(fn)
        def inner(*args, **kwargs):
            tid = sem.acquire()
            if tid is None:
                raise TaskLockedException('unable to acquire lock %s' %
                                          lock_name)
            try:
                return fn(*args, **kwargs)
            finally:
                sem.release(tid)
        return inner
    return decorator
