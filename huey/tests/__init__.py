from huey.tests.test_consumer import *
from huey.tests.test_crontab import *
from huey.tests.test_hooks import *
from huey.tests.test_pipeline import *
from huey.tests.test_queue import *
from huey.tests.test_registry import *
from huey.tests.test_storage import *
from huey.tests.test_utils import *
from huey.tests.test_wrapper import *

try:
    from huey.tests.test_sqlite import *
except ImportError:
    print('skipping sqlite tests, missing dependencies')

try:
    from huey.tests.test_simple import *
except ImportError:
    print('skipping simpledb tests, missing dependencies')
