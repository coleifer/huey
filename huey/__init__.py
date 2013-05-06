from huey.api import Huey, crontab
try:
    import redis
    from huey.backends.redis_backend import RedisBlockingQueue
    from huey.backends.redis_backend import RedisDataStore

    class RedisHuey(Huey):
        def __init__(self, name='huey', **conn_kwargs):
            queue = RedisBlockingQueue(name, **conn_kwargs)
            result_store = RedisDataStore(name, **conn_kwargs)
            super(RedisHuey, self).__init__(queue, result_store)
except ImportError:
    pass
