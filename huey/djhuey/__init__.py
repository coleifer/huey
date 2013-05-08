"""
This module contains a lot of cruft to handle instantiating a "Huey" object
using Django settings.  Unlike more flexible python apps, the huey django
integration consists of a single global Huey instance configured via the
settings module.
"""
import sys

from django.conf import settings

from huey import crontab
from huey import Huey
from huey.utils import load_class


configuration_message = """
Configuring Huey for use with Django
====================================

Huey was designed to be simple to configure in the general case.  For that
reason, huey will "just work" with no configuration at all provided you have
Redis installed and running locally.

On the other hand, you can configure huey manually using the following
setting structure.  The only required setting is 'queue'.  The following
example uses Redis on localhost:

.. note::
    Huey settings are optional.  If not provided, Huey will default to using
    Redis running locally.

HUEY = {
    'queue': 'huey.backends.redis_backend.RedisBlockingQueue',  # required.
    'queue_name': 'unique name',
    'queue_connection': {'host': 'localhost', 'port': 6379},

    # Options for configuring a result store -- *recommended*
    'result_store': 'huey.backends.redis_backend.RedisDataStore',
    'result_store_name': 'defaults to queue name',
    'result_store_connection': {'host': 'localhost', 'port': 6379},

    # Options to pass into the consumer when running ``manage.py run_huey``
    'consumer_options': {'workers': 4},
}

If you would like to configure Huey's logger using Django's integrated logging
settings, the logger used by consumer is named "huey.consumer".
"""

def default_queue_name():
    try:
        return settings.DATABASE_NAME
    except AttributeError:
        return settings.DATABASES['default']['NAME']
    except KeyError:
        return 'huey'

def config_error(msg):
    print configuration_message
    print '\n\n'
    print msg
    sys.exit(1)

def dynamic_import(obj, key, required=False):
    try:
        path = obj[key]
    except KeyError:
        if required:
            config_error('Missing required configuration: "%s"' % key)
        return None
    try:
        return load_class(path)
    except ImportError:
        config_error('Unable to import %s: "%s"' % (key, path))

try:
    HUEY = getattr(settings, 'HUEY', None)
except:
    config_error('Error encountered reading settings.HUEY')

if HUEY is None:
    try:
        from huey import RedisHuey
    except ImportError:
        config_error('Error: Huey could not import the redis backend. '
                     'Install `redis-py`.')
    HUEY = RedisHuey(default_queue_name())

if not isinstance(HUEY, Huey):
    Queue = dynamic_import(HUEY, 'queue')
    ResultStore = dynamic_import(HUEY, 'result_store')
    if Queue is None:
        try:
            from huey.backends.redis_backend import RedisBlockingQueue
            Queue = RedisBlockingQueue
        except ImportError:
            config_error('Redis not found.')
    queue_name = HUEY.get('queue_name') or default_queue_name()
    result_store_name = HUEY.get('result_store_name') or queue_name
    queue = Queue(queue_name, **HUEY.get('queue_connection', {}))
    if ResultStore:
        result_store = ResultStore(result_store_name,
                                   **HUEY.get('result_store_connection', {}))
    else:
        result_store = None
    HUEY = Huey(queue, result_store, always_eager=settings.DEBUG)


task = HUEY.task
periodic_task = HUEY.periodic_task
