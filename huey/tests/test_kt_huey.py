import os
import unittest

try:
    import ukt
except ImportError:
    ukt = None

try:
    from huey.contrib.kyototycoon import KyotoTycoonHuey
    from huey.contrib.kyototycoon import KyotoTycoonStorage
except ImportError:
    if ukt is not None:
        raise

from huey.tests.base import BaseTestCase
from huey.tests.test_storage import StorageTests


@unittest.skipIf(ukt is None, 'requires ukt')
class TestKyotoTycoonHuey(StorageTests, BaseTestCase):
    @classmethod
    def setUpClass(cls):
        lua_path = os.path.join(os.path.dirname(__file__), 'scripts/')
        lua_script = os.path.join(lua_path, 'kt.lua')
        cls._server = ukt.EmbeddedServer(database='%', serializer=ukt.KT_NONE,
                                         server_args=['-scr', lua_script])
        cls._server.run()
        cls.db = cls._server.client

    @classmethod
    def tearDownClass(cls):
        if cls._server is not None:
            cls._server.stop()
            cls.db.close_all()
            cls.db = None

    def tearDown(self):
        if self.db is not None:
            self.db.clear()

    def get_huey(self):
        return KyotoTycoonHuey(client=self.db, utc=False)
