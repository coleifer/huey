import logging

INSTALLED_APPS = [
    'huey.contrib.djhuey',
    'djangoex.test_app',
]

HUEY = {
    'name': 'test-django',
    'consumer': {
        'loglevel': logging.DEBUG,
        'workers': 2,
        'scheduler_interval': 5,
    },
}

SECRET_KEY = 'foo'
