import logging

INSTALLED_APPS = [
    'huey.contrib.djhuey',
    'djangoex.test_app',
]

HUEY = {
    'first_queue': {
        'default': True,
        'consumer': {
            'loglevel': logging.DEBUG,
            'workers': 2,
            'scheduler_interval': 5,
        },
    },
    'second_queue': {
        'consumer': {
            'loglevel': logging.DEBUG,
            'workers': 2,
            'scheduler_interval': 5,
        },
    }
}

SECRET_KEY = 'foo'
