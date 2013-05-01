import sys

from django.conf import settings

from huey.api import Huey
from huey.utils import load_class


configuration_message = """
Please configure your queue, example:

HUEY_CONFIG = {
    'queue': 'huey.backends.redis_backend.RedisQueue',
    'queue_connection': 'localhost:6379:0',
    'threads': 4,
}

The following settings are required:
------------------------------------

queue (string or Queue instance)
    Either a queue instance or a string pointing to the module path and class
    name of the queue.  If a string is used, you may also need to specify a
    connection string.

    Example: 'huey.backends.redis_backend.RedisQueue'


The following settings are recommended:
---------------------------------------

queue_name (string), default = database name

queue_connection (dictionary)
    If the ``queue`` was specified using a string, use this parameter to
    instruct the queue class how to connect.

    Example: 'localhost:6379:0' # for the RedisQueue

result_store (string or DataStore instance)
    Either a DataStore instance or a string pointing to the module path and
    class name of the result store.

    Example: 'huey.backends.redis_backend.RedisDataStore'

result_store_name (string), default = database name

result_store_connection (string)
    See notes for ``queue_connection``


The following settings are optional:
------------------------------------

periodic (boolean), default = False
    Determines whether or not to the consumer will enqueue periodic commands.
    If you are running multiple consumers, only one of them should be configured
    to enqueue periodic commands.

threads (int), default = 1
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

_config = getattr(settings, 'HUEY_CONFIG', None)
config = dict((k.lower(), v) for (k, v) in _config.iteritems())
if not config or 'queue' not in config:
    print configuration_message
    sys.exit(1)

queue = config['queue']

if 'default' in settings.DATABASES:
    backup_name = settings.DATABASES['default']['NAME'].rsplit('/', 1)[-1]
else:
    backup_name = 'huey'

if isinstance(queue, basestring):
    QueueClass = load_class(queue)
    queue = QueueClass(
        config.get('queue_name', backup_name),
        **config.get('queue_connection', {})
    )

result_store = config.get('result_store', None)

if isinstance(result_store, basestring):
    DataStoreClass = load_class(result_store)
    result_store = DataStoreClass(
        config.get('result_store_name', backup_name),
        **config.get('result_store_connection', {})
    )

always_eager = config.pop('always_eager', False)
huey = Huey(queue, result_store, always_eager=always_eager)
