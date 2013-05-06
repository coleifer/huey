INSTALLED_APPS = [
    'huey.djhuey',
    'test_app',
]

HUEY_CONFIG = {
    'queue': {
        'backend': 'huey.backends.redis_backend.RedisBlockingQueue',
        'name': 'test-queue',
        'connection': {
            'host': 'localhost',
            'port': 6379,
        },
    },
    'result_store': {
        'backend': 'huey.backends.redis_backend.RedisDataStore',
        'connection': {
            'host': 'localhost',
            'port': 6379,
        },
    },
    'periodic': True,
    'workers': 4,
}
