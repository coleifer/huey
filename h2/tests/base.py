import logging
import unittest


class NullHandler(logging.Handler):
    def emit(self, record): pass


logger = logging.getLogger('huey')
logger.addHandler(NullHandler())


class BaseTestCase(unittest.TestCase):
    pass
