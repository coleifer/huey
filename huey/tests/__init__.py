from huey.tests.backends import *
from huey.tests.consumer import *
from huey.tests.crontab import *
from huey.tests.queue import *
from huey.tests.utils import *
try:
    import peewee
    from huey.tests.peewee_tests import *
except ImportError:
    pass
