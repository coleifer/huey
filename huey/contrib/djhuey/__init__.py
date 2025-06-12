from functools import wraps
from importlib import import_module
import sys
import traceback

from django.conf import settings
from django.db import close_old_connections
from django.db import transaction


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
            return str(settings.DATABASES['default']['NAME'])
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


HUEY = getattr(settings, 'HUEY', None)
if HUEY is None:
    try:
        RedisHuey = get_backend(default_backend_path)
    except ImportError:
        config_error('Error: Huey could not import the redis backend. '
                     'Install `redis-py`.')
    else:
        HUEY = RedisHuey(default_queue_name())

if isinstance(HUEY, dict):
    huey_config = HUEY.copy()  # Operate on a copy.
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

    HUEY = backend_cls(name, **huey_config)

# Function decorators.
task = HUEY.task
periodic_task = HUEY.periodic_task
lock_task = HUEY.lock_task

# Task management.
enqueue = HUEY.enqueue
restore = HUEY.restore
restore_all = HUEY.restore_all
restore_by_id = HUEY.restore_by_id
revoke = HUEY.revoke
revoke_all = HUEY.revoke_all
revoke_by_id = HUEY.revoke_by_id
is_revoked = HUEY.is_revoked
result = HUEY.result
scheduled = HUEY.scheduled

# Hooks.
on_startup = HUEY.on_startup
on_shutdown = HUEY.on_shutdown
pre_execute = HUEY.pre_execute
post_execute = HUEY.post_execute
signal = HUEY.signal
disconnect_signal = HUEY.disconnect_signal


def close_db(fn):
    """Decorator to be used with tasks that may operate on the database."""
    @wraps(fn)
    def inner(*args, **kwargs):
        if not HUEY.immediate:
            close_old_connections()
        try:
            return fn(*args, **kwargs)
        finally:
            if not HUEY.immediate:
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
        ret = periodic_task(*args, **kwargs)(close_db(fn))
        ret.call_local = fn
        return ret
    return decorator


def on_commit_task(*args, **kwargs):
    """
    This task will register a post-commit callback to enqueue the task. A
    result handle will still be returned immediately, however, even though
    the task may not (ever) be enqueued, subject to whether or not the
    transaction actually commits.

    Because we have to setup the callback within the bit of code that performs
    the actual enqueueing, we cannot expose the full functionality of the
    TaskWrapper. If you anticipate wanting all these methods, you are probably
    best off decorating the same function twice, e.g.:

        def update_data(pk):
            # Do some database operation.
            pass

        my_task = task()(update_data)
        my_on_commit_task = on_commit_task()(update_data)
    """
    def decorator(fn):
        task_wrapper = task(*args, **kwargs)(close_db(fn))

        @wraps(fn)
        def inner(*a, **k):
            task = task_wrapper.s(*a, **k)
            def enqueue_on_commit():
                task_wrapper.huey.enqueue(task)
            transaction.on_commit(enqueue_on_commit)
            return HUEY._result_handle(task)
        inner.call_local = fn
        return inner
    return decorator
