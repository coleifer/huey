from functools import wraps
import threading
import uuid

from huey.exceptions import ConfigurationError
from huey.exceptions import TaskLockedException


ACQUIRE_LUA = """\
local t = redis.call('time')
local now = tonumber(t[1]) + tonumber(t[2]) / 1000000
redis.call('zremrangebyscore', KEYS[1], '-inf', now - tonumber(ARGV[1]))
if redis.call('zscore', KEYS[1], ARGV[3]) == false and
        redis.call('zcard', KEYS[1]) >= tonumber(ARGV[2]) then
    return 0
end
redis.call('zadd', KEYS[1], now, ARGV[3])
return 1"""

RENEW_LUA = """\
local t = redis.call('time')
local now = tonumber(t[1]) + tonumber(t[2]) / 1000000
if redis.call('zscore', KEYS[1], ARGV[1]) == false then
    return 0
end
redis.call('zadd', KEYS[1], now, ARGV[1])
return 1"""


class RedisSemaphore(object):
    """
    Extremely basic semaphore for use with Redis.
    """
    def __init__(self, huey, name, value=1, timeout=None):
        self.huey = huey
        self.key = '%s.lock.%s' % (huey.name, name)
        self.value = value
        # Holders renew while they run, so this bounds how long a dead holder
        # occupies a slot rather than how long a task may take.
        self.timeout = timeout or 300

        self.huey._locks.add(self.key)

    @property
    def conn(self):
        conn = getattr(self.huey.storage, 'conn', None)
        if conn is None:
            raise ConfigurationError('Semaphore requires a Redis storage.')
        return conn

    def acquire(self, name=None):
        name = name or str(uuid.uuid4())
        if self.conn.eval(ACQUIRE_LUA, 1, self.key, self.timeout, self.value,
                          name):
            return name

    def renew(self, name):
        return bool(self.conn.eval(RENEW_LUA, 1, self.key, name))

    def release(self, name):
        return self.conn.zrem(self.key, name)

    def _renew_until(self, name, stop):
        interval = self.timeout / 3.0
        while not stop.wait(interval):
            self.renew(name)


def lock_task_semaphore(huey, lock_name, value=1, timeout=None):
    """
    Lock which can be acquired multiple times (default = 1).

    NOTE: no provisions are made for blocking, waiting, or notifying. This is
    just a lock which can be acquired a configurable number of times.

    The lock is renewed while the task runs, so ``timeout`` (default 300s)
    determines how quickly a slot is reclaimed after a worker dies.

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
            stop = threading.Event()
            renewer = threading.Thread(target=sem._renew_until,
                                       args=(tid, stop), daemon=True)
            renewer.start()
            try:
                return fn(*args, **kwargs)
            finally:
                stop.set()
                renewer.join()
                sem.release(tid)
        return inner
    return decorator
