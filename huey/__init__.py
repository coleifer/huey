__author__ = 'Charles Leifer'
__license__ = 'MIT'
__version__ = '0.4.9'

from huey.api import Huey, crontab

try:
    import redis
    from huey.backends.redis_backend import RedisBlockingQueue
    from huey.backends.redis_backend import RedisDataStore
    from huey.backends.redis_backend import RedisEventEmitter
    from huey.backends.redis_backend import RedisSchedule

    class RedisHuey(Huey):
        def __init__(self, name='huey', store_none=False, always_eager=False,
                     read_timeout=None, **conn_kwargs):
            queue = RedisBlockingQueue(
                name,
                read_timeout=read_timeout,
                **conn_kwargs)
            result_store = RedisDataStore(name, **conn_kwargs)
            schedule = RedisSchedule(name, **conn_kwargs)
            events = RedisEventEmitter(name, **conn_kwargs)
            super(RedisHuey, self).__init__(
                queue=queue,
                result_store=result_store,
                schedule=schedule,
                events=events,
                store_none=store_none,
                always_eager=always_eager)

except ImportError:
    class RedisHuey(object):
        def __init__(self, *args, **kwargs):
            raise RuntimeError('Error, "redis" is not installed. Install '
                               'using pip: "pip install redis"')

try:
    from huey.backends.sqlite_backend import SqliteQueue
    from huey.backends.sqlite_backend import SqliteDataStore
    from huey.backends.sqlite_backend import SqliteSchedule

    class SqliteHuey(Huey):
        def __init__(self, name='huey', store_none=False, always_eager=False,
                     location=None):
            if location is None:
                raise ValueError("Please specify a database file with the "
                                 "'location' parameter")
            queue = SqliteQueue(name, location)
            result_store = SqliteDataStore(name, location)
            schedule = SqliteSchedule(name, location)
            super(SqliteHuey, self).__init__(
                queue=queue,
                result_store=result_store,
                schedule=schedule,
                events=None,
                store_none=store_none,
                always_eager=always_eager)
except ImportError:
    class SqliteHuey(object):
        def __init__(self, *args, **kwargs):
            raise RuntimeError('Error, "sqlite" is not installed.')
