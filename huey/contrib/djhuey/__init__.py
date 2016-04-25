from functools import wraps
import sys

from django.conf import settings
from django.db import connection

from huey import crontab
from huey import RedisHuey
from huey.utils import load_class


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
settings, the logger used by consumer is named "huey.consumer".

Alternatively you can simply assign `settings.HUEY` to an actual `Huey`
object instance:

from huey import RedisHuey
HUEY = RedisHuey('my-app')
"""

def default_queue_name():
    try:
        return settings.DATABASE_NAME
    except AttributeError:
        try:
            return settings.DATABASES['default']['NAME']
        except KeyError:
            return 'huey'

def config_error(msg):
    print(configuration_message)
    print('\n\n')
    print(msg)
    sys.exit(1)

HUEY = getattr(settings, 'HUEY', None)
if HUEY is None:
    try:
        from huey import RedisHuey
    except ImportError:
        config_error('Error: Huey could not import the redis backend. '
                     'Install `redis-py`.')
    else:
        HUEY = RedisHuey(default_queue_name())

if isinstance(HUEY, dict):
    huey_config = HUEY.copy()  # Operate on a copy.
    name = huey_config.pop('name', default_queue_name())
    conn_kwargs = huey_config.pop('connection', {})
    try:
        del huey_config['consumer']  # Don't need consumer opts here.
    except KeyError:
        pass
    if 'always_eager' not in huey_config:
        huey_config['always_eager'] = settings.DEBUG
    huey_config.update(conn_kwargs)
    HUEY = RedisHuey(name, **huey_config)

task = HUEY.task
periodic_task = HUEY.periodic_task

def close_db(fn):
    """Decorator to be used with tasks that may operate on the database."""
    @wraps(fn)
    def inner(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        finally:
            if not HUEY.always_eager:
                connection.close()
    return inner

def db_task(*args, **kwargs):
    def decorator(fn):
        return task(*args, **kwargs)(close_db(fn))
    return decorator

def db_periodic_task(*args, **kwargs):
    def decorator(fn):
        return periodic_task(*args, **kwargs)(close_db(fn))
    return decorator
