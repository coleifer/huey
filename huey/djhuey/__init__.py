import sys

from django.conf import settings

from huey.api import Huey
from huey.utils import load_class


configuration_message = """
Please configure your queue, example:

HUEY_CONFIG = {
    'queue': {
        'backend': 'huey.backends.redis_backend.RedisQueue',
        'connection': {
            'host': 'localhost',
            'port': 6379,
        },
        'name': 'my-app',
    },
    'result_store': {
        'backend': 'huey.backends.redis_backend.RedisDataStore',
        'connection': {
            'host': 'localhost',
            'port': 6379,
        },
        'name': 'my-app',
    },
    'periodic': True,  # Process cron-like tasks.
    'workers': 4,  # Use up to 4 worker threads.
}

The following settings are required:
------------------------------------

queue (dictionary or Queue instance)
    Either a queue instance or a dictionary containing information for
    configuring your queue.

    Only the "backend" setting is strictly required.

    Example::

        'queue': {
            'backend': 'huey.backends.redis_backend.RedisQueue',
            'connection': {
                'host': 'localhost',
                'port': 6379,
            },
            'name': 'my-app',
        }

The following settings are recommended:
---------------------------------------

result_store (dictionary or DataStore instance)
    Either a DataStore instance or a dictionary containing information for
    configuring your data store.

    Only the "backend" setting is required.

    Example::

        'result_store': {
            'backend': 'huey.backends.redis_backend.RedisDataStore',
            'connection': {
                'host': 'localhost',
                'port': 6379,
            },
            'name': 'my-app',
        }

The following settings are optional:
------------------------------------

periodic (boolean), default = True
    Determines whether or not to the consumer will enqueue periodic commands.
    If you are running multiple consumers, only one of them should be configured
    to enqueue periodic commands.

workers (int), default = 2
    Number of worker threads to use when processing jobs

logfile (string), default = None

loglevel (int), default = logging.INFO

backoff (numeric), default = 1.15
    How much to increase delay when no jobs are present

initial_delay (numeric), default = 0.1
    Initial amount of time to sleep when waiting for jobs

max_delay (numeric), default = 10
    Max amount of time to sleep when waiting for jobs

utc (boolean), default = True

always_eager, default = False
    Whether to skip enqueue-ing and run in-band (useful for debugging)
"""

_default = {
    'queue': {'backend': 'huey.backends.redis_backend.RedisQueue'},
    'result_store': {'backend': 'huey.backends.redis_backend.RedisDataStore'},
    'periodic': True,
    'workers': 2}
config = dict(getattr(settings, 'HUEY_CONFIG', _default))

try:
    backend = config['queue']['backend']
except:
    print configuration_message
    sys.exit(1)

_db = settings.DATABASES
if 'default' in _db and _db['default'].get('NAME'):
    backup_name = _db['default']['NAME'].rsplit('/', 1)[-1]
else:
    backup_name = 'huey'

queue = config.pop('queue')
if isinstance(queue, dict):
    QueueClass = load_class(queue['backend'])
    queue = QueueClass(
        queue.get('name', backup_name),
        **queue.get('connection', {})
    )

result_store = config.pop('result_store', None)

if isinstance(result_store, dict):
    DataStoreClass = load_class(result_store['backend'])
    result_store = DataStoreClass(
        result_store.get('name', backup_name),
        **result_store.get('connection', {})
    )

always_eager = config.pop('always_eager', False)
huey = Huey(queue, result_store, always_eager=always_eager)
