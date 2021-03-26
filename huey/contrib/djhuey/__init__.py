from functools import wraps
from importlib import import_module
import sys
import traceback

from django.conf import settings
from django.db import close_old_connections

from huey.contrib.djhuey.config import DjangoHueySettingsReader


HUEY = getattr(settings, 'HUEY', None)
HUEYS = getattr(settings, 'HUEYS', None)

config = DjangoHueySettingsReader(HUEY, HUEYS)
config.configure()

def get_close_db_for_queue(queue):
    def close_db(fn):
        """Decorator to be used with tasks that may operate on the database."""
        @wraps(fn)
        def inner(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            finally:
                instance = default_queue(queue)
                if not instance.immediate:
                    close_old_connections()
        return inner

    return close_db

def default_queue(queue):
    return config.default_queue(queue)

def task(*args, queue=None, **kwargs):
    return default_queue(queue).task(*args, **kwargs)

def periodic_task(*args, queue=None, **kwargs):
    return default_queue(queue).periodic_task(*args, **kwargs)
    
def lock_task(*args, queue=None, **kwargs):
    return default_queue(queue).lock_task(*args, **kwargs)
    
# Task management.
    
def enqueue(*args, queue=None, **kwargs):
    return default_queue(queue).enqueue(*args, **kwargs)
    
def restore(*args, queue=None, **kwargs):
    return default_queue(queue).restore(*args, **kwargs)
    
def restore_all(*args, queue=None, **kwargs):
    return default_queue(queue).restore_all(*args, **kwargs)
    
def restore_by_id(*args, queue=None, **kwargs):
    return default_queue(queue).restore_by_id(*args, **kwargs)
    
def revoke(*args, queue=None, **kwargs):
    return default_queue(queue).revoke(*args, **kwargs)
    
def revoke_all(*args, queue=None, **kwargs):
    return default_queue(queue).revoke_all(*args, **kwargs)
    
def revoke_by_id(*args, queue=None, **kwargs):
    return default_queue(queue).revoke_by_id(*args, **kwargs)
    
def is_revoked(*args, queue=None, **kwargs):
    return default_queue(queue).is_revoked(*args, **kwargs)
    
def result(*args, queue=None, **kwargs):
    return default_queue(queue).result(*args, **kwargs)
    
def scheduled(*args, queue=None, **kwargs):
    return default_queue(queue).scheduled(*args, **kwargs)
    
# Hooks.
def on_startup(*args, queue=None, **kwargs):
    return default_queue(queue).on_startup(*args, **kwargs)
    
def on_shutdown(*args, queue=None, **kwargs):
    return default_queue(queue).on_shutdown(*args, **kwargs)
    
def pre_execute(*args, queue=None, **kwargs):
    return default_queue(queue).pre_execute(*args, **kwargs)
    
def post_execute(*args, queue=None, **kwargs):
    return default_queue(queue).post_execute(*args, **kwargs)
    
def signal(*args, queue=None, **kwargs):
    return default_queue(queue).signal(*args, **kwargs)
    
def disconnect_signal(*args, queue=None, **kwargs):
    return default_queue(queue).disconnect_signal(*args, **kwargs)


def db_task(*args, **kwargs):
    queue = kwargs.get('queue')
    def decorator(fn):
        ret = task(*args, **kwargs)(get_close_db_for_queue(queue)(fn))
        ret.call_local = fn
        return ret
    return decorator

def db_periodic_task(*args, **kwargs):
    queue = kwargs.get('queue')
    def decorator(fn):
        ret = periodic_task(*args, **kwargs)(get_close_db_for_queue(queue)(fn))
        ret.call_local = fn
        return ret
    return decorator
