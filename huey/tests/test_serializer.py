import datetime

from huey.api import MemoryHuey
from huey.api import PeriodicTask
from huey.api import Result
from huey.api import Task
from huey.api import TaskWrapper
from huey.api import crontab
from huey.api import _unsupported
from huey.constants import EmptyData
from huey.exceptions import CancelExecution
from huey.exceptions import ConfigurationError
from huey.exceptions import RetryTask
from huey.exceptions import TaskException
from huey.exceptions import TaskLockedException
from huey.serializer import Serializer
from huey.tests.base import BaseTestCase


class TestSerializer(BaseTestCase):
    def test_serialize(self):
        serializer = Serializer()
        data = 1
        serialized_data = serializer.serialize(data)
        self.assertEqual(serializer.deserialize(serialized_data), data)

        serializer = Serializer(compression=True)
        serialized_data = serializer.serialize(data)
        self.assertEqual(serializer.deserialize(serialized_data), data)
