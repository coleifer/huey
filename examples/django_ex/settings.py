import logging

INSTALLED_APPS = [
    'huey.djhuey',
    'test_app',
]

HUEY = {
    'queue_name': 'test-django',
    'queue': 'huey.backends.redis_backend.RedisBlockingQueue',
    'result_store': 'huey.backends.redis_backend.RedisDataStore',
    'consumer_options': {
        'loglevel': logging.DEBUG,
        'workers': 2,
    }
}
