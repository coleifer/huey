from functools import wraps
from importlib import import_module
import sys
import traceback

from django.conf import settings
from django.db import close_old_connections

from huey.contrib.djhuey.configuration import HueySettingsReader



configuration_message = """
Configuring Huey for use with Django
====================================

Huey was designed to be simple to configure in the general case.  For that
reason, huey will "just work" with no configuration at all provided you have
Redis installed and running locally.

On the other hand, you can configure huey manually using the following
setting structure.

The following example uses Redis on localhost, and will run four worker
processes:

HUEY = {
    'my-app': {
        'default': True,
        'backend': 'huey.backends.redis_backend',
        'connection': {'host': 'localhost', 'port': 6379},
            'consumer': {
                'workers': 4,
                'worker_type': 'process',
        }
    },
    'my-app2': {
        'backend': 'huey.backends.sqlite_backend',
        'connection': {'location': 'sqlite filename'},
            'consumer': {
                'workers': 4,
                'worker_type': 'process',
        }
    },
}

Additionally the old configuration variant is still usable:

HUEY = {
    'name': 'my-app',
    'connection': {'host': 'localhost', 'port': 6379},
    'consumer': {
        'workers': 4,
        'worker_type': 'process',  # "thread" or "greenlet" are other options
    },
}

If you would like to configure Huey's logger using Django's integrated logging
settings, the logger used by consumer is named "huey.consumer".

Alternatively you can simply assign `settings.HUEY` to an actual `Huey`
object instance:

from huey import RedisHuey
HUEY = RedisHuey('my-app')
"""

_huey_settings = getattr(settings, 'HUEY', None)

_django_huey = HueySettingsReader(_huey_settings)
_django_huey.start()

HUEY = _django_huey.huey
hueys = _django_huey.hueys

consumer = _django_huey.consumer
consumers = _django_huey.consumers

task = _django_huey.task
periodic_task = _django_huey.periodic_task


def close_db(fn):
    """Decorator to be used with tasks that may operate on the database."""
    @wraps(fn)
    def inner(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        finally:
            if not HUEY.always_eager:
                close_old_connections()
    return inner


def db_task(*args, **kwargs):
    def decorator(fn):
        return task(*args, **kwargs)(close_db(fn))
    return decorator


def db_periodic_task(*args, **kwargs):
    def decorator(fn):
        return periodic_task(*args, **kwargs)(close_db(fn))
    return decorator
