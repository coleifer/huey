from functools import wraps
from importlib import import_module
import sys
import traceback

from django.conf import settings
from django.db import close_old_connections


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
    'name': 'my-app',
    'connection': {'host': 'localhost', 'port': 6379},
    'consumer': {
        'workers': 4,
        'worker_type': 'process',  # "thread" or "greenlet" are other options
    },
}

Sometimes you need to configure multiple queues, you can use HUEYS setting for that.

The following example provides two queues. One of them uses Redis on localhost, and will run four worker
processes. The other one will run two worker processes and its intended to be used for emails:

HUEYS = {
    'first': {
        'name': 'my-app',
        'connection': {'host': 'localhost', 'port': 6379},
        'consumer': {
            'workers': 4,
            'worker_type': 'process',  # "thread" or "greenlet" are other options
        }
    },
    'emails': {
        'name': 'email',
        'connection': {'host': 'localhost', 'port': 6379},
        'consumer': {
            'workers': 2,
            'worker_type': 'process',  # "thread" or "greenlet" are other options
        },
    },
}

If you would like to configure Huey's logger using Django's integrated logging
settings, the logger used by consumer is named "huey".

Alternatively you can simply assign `settings.HUEY` to an actual `Huey`
object instance:

from huey import RedisHuey
HUEY = RedisHuey('my-app')
"""


default_backend_path = 'huey.RedisHuey'

def default_queue_name():
    try:
        return settings.DATABASE_NAME
    except AttributeError:
        try:
            return settings.DATABASES['default']['NAME']
        except KeyError:
            return 'huey'


def get_backend(import_path=default_backend_path):
    module_path, class_name = import_path.rsplit('.', 1)
    module = import_module(module_path)
    return getattr(module, class_name)


def config_error(msg):
    print(configuration_message)
    print('\n\n')
    print(msg)
    sys.exit(1)

def configure_instance(huey_config):
    name = huey_config.pop('name', default_queue_name())
    if 'backend_class' in huey_config:
        huey_config['huey_class'] = huey_config.pop('backend_class')
    backend_path = huey_config.pop('huey_class', default_backend_path)
    conn_kwargs = huey_config.pop('connection', {})
    try:
        del huey_config['consumer']  # Don't need consumer opts here.
    except KeyError:
        pass
    if 'immediate' not in huey_config:
        huey_config['immediate'] = settings.DEBUG
    huey_config.update(conn_kwargs)

    try:
        backend_cls = get_backend(backend_path)
    except (ValueError, ImportError, AttributeError):
        config_error('Error: could not import Huey backend:\n%s'
                     % traceback.format_exc())

    return backend_cls(name, **huey_config)


HUEY = getattr(settings, 'HUEY', None)
HUEYS = getattr(settings, 'HUEYS', None)

if HUEY is not None and HUEYS is not None:
    config_error('Error: HUEY and HUEYS settings are incompatible!')

if HUEY is None and HUEYS is None:
    try:
        RedisHuey = get_backend(default_backend_path)
    except ImportError:
        config_error('Error: Huey could not import the redis backend. '
                     'Install `redis-py`.')
    else:
        HUEY = RedisHuey(default_queue_name())

if isinstance(HUEY, dict):
    HUEY = configure_instance(HUEY.copy())

if HUEYS is not None:
    if not isinstance(HUEYS, dict):
        config_error('Error: HUEYS must be a dictionary ')

    new_hueys = dict()
    for queue_name, config in HUEYS.items():
        huey_config = config.copy()
        huey_config['name'] = queue_name

        new_hueys[queue_name] = configure_instance(huey_config)

    HUEYS = new_hueys

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
    if HUEYS is not None and queue is None:
        config_error("""
If HUEYS is configured run_huey must receive a --queue parameter
i.e.: 
python manage.py run_huey --queue first
            """)
    return HUEY if HUEY is not None else HUEYS[queue]

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
