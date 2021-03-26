from huey.tests.test_api import *
from huey.tests.test_consumer import *
from huey.tests.test_crontab import *
from huey.tests.test_immediate import *
from huey.tests.test_kt_huey import *
from huey.tests.test_priority import *
from huey.tests.test_registry import *
from huey.tests.test_serializer import *
from huey.tests.test_signals import *
from huey.tests.test_sql_huey import *
from huey.tests.test_storage import *
from huey.tests.test_utils import *
from huey.tests.test_wrappers import *

import os 

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "huey.contrib.djhuey.tests.settings")
from huey.contrib.djhuey.tests import *