import logging
import unittest

from h2.exceptions import TaskException
from h2.storage import MemoryHuey


class NullHandler(logging.Handler):
    def emit(self, record): pass


logger = logging.getLogger('huey')
logger.addHandler(NullHandler())


class BaseTestCase(unittest.TestCase):
    def setUp(self):
        super(BaseTestCase, self).setUp()
        self.huey = self.get_huey()

    def get_huey(self):
        return MemoryHuey(utc=False)

    def execute_next(self):
        task = self.huey.dequeue()
        self.assertTrue(task is not None)
        return self.huey.execute(task)

    def trap_exception(self, fn, exc_type=TaskException):
        try:
            fn()
        except exc_type as exc_val:
            return exc_val
        raise AssertionError('trap_exception() failed to catch %s' % exc_type)
