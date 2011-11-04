import sys

from django.conf import settings

from skew.queue import Invoker
from skew.utils import load_class


configuration_message = """
Please configure your queue, example:

SKEW_CONFIG = {
    'QUEUE': 'skew.backends.redis_backend.RedisQueue',
    'QUEUE_CONNECTION': 'localhost:6379:0',
    'THREADS': 4,
}

The following settings are required:
------------------------------------

QUEUE (string or Queue instance)
    Either a queue instance or a string pointing to the module path and class
    name of the queue.  If a string is used, you may also need to specify a
    connection string.
    
    Example: 'skew.backends.redis_backend.RedisQueue'


The following settings are recommended:
---------------------------------------

QUEUE_NAME (string), default = database name

QUEUE_CONNECTION (string)
    If the SKEW_QUEUE was specified using a string, use this parameter to
    instruct the queue class how to connect.
    
    Example: 'localhost:6379:0' # for the RedisQueue

RESULT_STORE (string or ResultStore instance)
    Either a ResultStore instance or a string pointing to the module path and
    class name of the result store.
    
    Example: 'skew.backends.redis_backend.RedisResultStore'

RESULT_STORE_NAME (string), default = database name

RESULT_STORE_CONNECTION (string)
    See notes for QUEUE_CONNECTION


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
"""

config = getattr(settings, 'SKEW_CONFIG', None)
if not config or 'QUEUE' not in config:
    print configuration_message
    sys.exit(1)

queue = config['QUEUE']

db_name = settings.DATABASES['default']['NAME'].rsplit('/', 1)[-1]

if isinstance(queue, basestring):
    QueueClass = load_class(queue)
    queue = QueueClass(
        config.get('QUEUE_NAME', db_name),
        config.get('QUEUE_CONNECTION', None),
        **config.get('QUEUE_CONNECTION_EXTRA', {})
    )
    config['QUEUE'] = queue

result_store = config.get('RESULT_STORE', None)

if isinstance(result_store, basestring):
    ResultStoreClass = load_class(result_store)
    result_store = ResultStoreClass(
        config.get('RESULT_STORE_NAME', db_name),
        config.get('RESULT_STORE_CONNECTION', None),
        **config.get('RESULT_STORE_CONNECTION_EXTRA', {})
    )
    config['RESULT_STORE'] = result_store

invoker = Invoker(queue, result_store)
