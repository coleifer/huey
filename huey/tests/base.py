import contextlib
import logging
import os
import unittest

from huey.api import MemoryHuey
from huey.consumer import Consumer
from huey.exceptions import TaskException


class NullHandler(logging.Handler):
    def emit(self, record): pass


logger = logging.getLogger('huey')
logger.addHandler(NullHandler())

TRAVIS = bool(os.environ.get('HUEY_TRAVIS'))


class BaseTestCase(unittest.TestCase):
    consumer_class = Consumer

    def setUp(self):
        super(BaseTestCase, self).setUp()
        self.huey = self.get_huey()

    def get_huey(self):
        return MemoryHuey(utc=False)

    def execute_next(self, timestamp=None):
        task = self.huey.dequeue()
        self.assertTrue(task is not None)
        return self.huey.execute(task, timestamp=timestamp)

    def trap_exception(self, fn, exc_type=TaskException):
        try:
            fn()
        except exc_type as exc_val:
            return exc_val
        raise AssertionError('trap_exception() failed to catch %s' % exc_type)

    def consumer(self, **params):
        params.setdefault('initial_delay', 0.001)
        params.setdefault('max_delay', 0.001)
        params.setdefault('workers', 2)
        params.setdefault('check_worker_health', False)
        return self.consumer_class(self.huey, **params)

    @contextlib.contextmanager
    def consumer_context(self, **kwargs):
        consumer = self.consumer(**kwargs)
        consumer.start()
        try:
            yield
        finally:
            consumer.stop(graceful=True)
