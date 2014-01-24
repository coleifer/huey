import logging

INSTALLED_APPS = [
    'huey.djhuey',
    'test_app',
]

HUEY = {
    'name': 'test-django',
    'backend': 'huey.backends.redis_backend',
    'consumer_options': {
        'loglevel': logging.DEBUG,
        'workers': 2,
    }
}

SECRET_KEY = 'foo'
