from huey.tests.crontab import *
from huey.tests.queue import *
from huey.tests.consumer import *
from huey.tests.backends import *

import os
if os.environ.get("TEST_CPU", False):
    from huey.tests.cpu import *