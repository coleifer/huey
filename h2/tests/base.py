import logging
import unittest

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
