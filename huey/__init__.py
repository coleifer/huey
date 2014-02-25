from huey.api import Huey, crontab
try:
    import redis
    from huey.backends.redis_backend import RedisBlockingQueue
    from huey.backends.redis_backend import RedisDataStore
    from huey.backends.redis_backend import RedisEventEmitter
    from huey.backends.redis_backend import RedisSchedule

    class RedisHuey(Huey):
        def __init__(self, name='huey', store_none=False, always_eager=False,
                     **conn_kwargs):
            queue = RedisBlockingQueue(name, **conn_kwargs)
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
    import plyvel
    from huey.backends.leveldb_backend import LevelDbQueue
    from huey.backends.leveldb_backend import LevelDbDataStore
    from huey.backends.leveldb_backend import LevelDbEventEmitter
    from huey.backends.leveldb_backend import LevelDbSchedule

    class LevelDbHuey(Huey):
        def __init__(self, location, name='huey', sync=False, store_none=False,
                     always_eager=False):
            # NOTE: All backend objects share the same database, this is
            # neccessary since only one LevelDb database instance can exist per
            # process.
            db = plyvel.DB(location, create_if_missing=True).prefixed_db(name)

            queue = LevelDbQueue(name, db, sync)
            result_store = LevelDbDataStore(name, db, sync)
            schedule = LevelDbSchedule(name, db, sync)
            events = LevelDbEventEmitter(name, db, sync)
            super(LevelDbHuey, self).__init__(
                queue=queue,
                result_store=result_store,
                schedule=schedule,
                events=events,
                store_none=store_none,
                always_eager=always_eager)

except ImportError:
    class LevelDbHuey(object):
        def __init__(self, *args, **kwargs):
            raise RuntimeError('Error, "plyvel" is not installed. Install '
                               'using pip: "pip install plyvel"')
