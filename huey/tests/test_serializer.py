try:
    import gzip
except ImportError:
    gzip = None
import unittest
try:
    import zlib
except ImportError:
    zlib = None

from huey.serializer import Serializer
from huey.tests.base import BaseTestCase


class TestSerializer(BaseTestCase):
    data = [
        None,
        0, 1,
        b'a' * 1024,
        ['k1', 'k2', 'k3'],
        {'k1': 'v1', 'k2': 'v2', 'k3': 'v3'}]

    def _test_serializer(self, s):
        for item in self.data:
            self.assertEqual(s.deserialize(s.serialize(item)), item)

    def test_serializer(self):
        self._test_serializer(Serializer())

    @unittest.skipIf(gzip is None, 'gzip module not installed')
    def test_serializer_gzip(self):
        self._test_serializer(Serializer(compression=True))

    @unittest.skipIf(zlib is None, 'zlib module not installed')
    def test_serializer_zlib(self):
        self._test_serializer(Serializer(compression=True, use_zlib=True))

    @unittest.skipIf(zlib is None, 'zlib module not installed')
    @unittest.skipIf(gzip is None, 'gzip module not installed')
    def test_mismatched_compression(self):
        for use_zlib in (False, True):
            s = Serializer()
            scomp = Serializer(compression=True, use_zlib=use_zlib)
            for item in self.data:
                self.assertEqual(scomp.deserialize(s.serialize(item)), item)
