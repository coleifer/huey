import sys

from django.conf import settings

from huey.queue import Invoker
from huey.utils import load_class


configuration_message = """
Please configure your queue, example:

HUEY_CONFIG = {
    'QUEUE': 'huey.backends.redis_backend.RedisQueue',
    'QUEUE_CONNECTION': 'localhost:6379:0',
    'THREADS': 4,
}

The following settings are required:
------------------------------------

QUEUE (string or Queue instance)
    Either a queue instance or a string pointing to the module path and class
    name of the queue.  If a string is used, you may also need to specify a
    connection string.
    
    Example: 'huey.backends.redis_backend.RedisQueue'


The following settings are recommended:
---------------------------------------

QUEUE_NAME (string), default = database name

QUEUE_CONNECTION (dictionary)
    If the HUEY_QUEUE was specified using a string, use this parameter to
    instruct the queue class how to connect.
    
    Example: 'localhost:6379:0' # for the RedisQueue

RESULT_STORE (string or DataStore instance)
    Either a DataStore instance or a string pointing to the module path and
    class name of the result store.
    
    Example: 'huey.backends.redis_backend.RedisDataStore'

RESULT_STORE_NAME (string), default = database name

RESULT_STORE_CONNECTION (string)
    See notes for QUEUE_CONNECTION

TASK_STORE
    Follows same pattern as RESULT_STORE


The following settings are optional:
------------------------------------

PERIODIC (boolean), default = False
    Determines whether or not to the consumer will enqueue periodic commands.
    If you are running multiple consumers, only one of them should be configured
    to enqueue periodic commands.

THREADS (int), default = 1
    Number of worker threads to use when processing jobs

LOGFILE (string), default = None

LOGLEVEL (int), default = logging.INFO

BACKOFF (numeric), default = 1.15
    How much to increase delay when no jobs are present

INITIAL_DELAY (numeric), default = 0.1
    Initial amount of time to sleep when waiting for jobs

MAX_DELAY (numeric), default = 10
    Max amount of time to sleep when waiting for jobs

ALWAYS_EAGER, default = False
    Whether to skip enqueue-ing and run in-band (useful for debugging)
"""

config = getattr(settings, 'HUEY_CONFIG', None)
if not config or 'QUEUE' not in config:
    print configuration_message
    sys.exit(1)

queue = config['QUEUE']

if 'default' in settings.DATABASES:
    backup_name = settings.DATABASES['default']['NAME'].rsplit('/', 1)[-1]
else:
    backup_name = 'huey'

if isinstance(queue, basestring):
    QueueClass = load_class(queue)
    queue = QueueClass(
        config.get('QUEUE_NAME', backup_name),
        **config.get('QUEUE_CONNECTION', {})
    )
    config['QUEUE'] = queue

result_store = config.get('RESULT_STORE', None)

if isinstance(result_store, basestring):
    DataStoreClass = load_class(result_store)
    result_store = DataStoreClass(
        config.get('RESULT_STORE_NAME', backup_name),
        **config.get('RESULT_STORE_CONNECTION', {})
    )
    config['RESULT_STORE'] = result_store

task_store = config.get('TASK_STORE', None)

if isinstance(task_store, basestring):
    DataStoreClass = load_class(task_store)
    task_store = DataStoreClass(
        config.get('TASK_STORE_NAME', backup_name),
        **config.get('TASK_STORE_CONNECTION', {})
    )
    config['TASK_STORE'] = task_store

invoker = Invoker(queue, result_store, task_store, always_eager=config.get('ALWAYS_EAGER', False))
