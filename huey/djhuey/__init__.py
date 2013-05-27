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
setting structure.  The following example uses Redis on localhost:

Simply point to a backend:

HUEY = {
    'backend': 'huey.backends.redis_backend',
    'name': 'unique name',
    'connection': {'host': 'localhost', 'port': 6379}

    'consumer_options': {'workers': 4},
}

If you would like to configure Huey's logger using Django's integrated logging
settings, the logger used by consumer is named "huey.consumer".

For more granular control, you can assign HUEY programmatically:

HUEY = Huey(RedisBlockingQueue('my-queue'))
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
        return load_class(path + '.Components')
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
    Queue, DataStore, Schedule = dynamic_import(HUEY, 'backend')
    name = HUEY.get('name') or default_queue_name()
    conn = HUEY.get('connection', {})
    always_eager = HUEY.get('always_eager', False)
    HUEY = Huey(
        Queue(name, **conn),
        DataStore(name, **conn),
        Schedule(name, **conn),
        always_eager=always_eager)

task = HUEY.task
periodic_task = HUEY.periodic_task
