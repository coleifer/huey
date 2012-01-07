import datetime
import unittest

from huey.exceptions import QueueException
from huey.registry import registry


class HueyRegistryTestCase(unittest.TestCase):
    def test_get_command_class(self):
        klass_str = 'huey.tests.test_cmd.queuecmd_test_command_xxx'

        # ensure it has not been imported or seen yet
        self.assertFalse(klass_str in registry._registry)

        # this will import the module dynamically
        test_cmd = registry.get_command_class(klass_str)
        self.assertEqual(test_cmd(((1,), {})).execute(), 1)

        # this will raise a QueueException, even though the module is valid
        self.assertRaises(QueueException, registry.get_command_class, 'huey.tests.test_cmd.queuecmd_does_not_exist')

        # this will raise a QueueException after the import fails
        self.assertRaises(QueueException, registry.get_command_class, 'huey.does.not.exist')
