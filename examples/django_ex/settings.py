INSTALLED_APPS = [
    'huey.djhuey',
    'test_app',
]

HUEY_CONFIG = {
    'QUEUE': 'huey.backends.redis_backend.RedisBlockingQueue',
    'QUEUE_NAME': 'test-queue',
    'QUEUE_CONNECTION': {
        'host': 'localhost',
        'port': 6379,
    },
    'RESULT_STORE': 'huey.backends.redis_backend.RedisDataStore',
    'RESULT_STORE_CONNECTION': {
        'host': 'localhost',
        'port': 6379,
    },
    'PERIODIC': True,
    'THREADS': 4,
}
