from functools import wraps
from importlib import import_module
import sys
import traceback

from django.conf import settings
from django.db import close_old_connections

from huey.contrib.djhuey.configuration import HueySettingsReader


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
        ret = task(*args, **kwargs)(close_db(fn))
        ret.call_local = fn
        return ret
    return decorator


def db_periodic_task(*args, **kwargs):
    def decorator(fn):
        return periodic_task(*args, **kwargs)(close_db(fn))
    return decorator
