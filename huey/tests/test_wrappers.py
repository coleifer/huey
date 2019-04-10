from functools import partial

from huey import api
from huey import storage
from huey.tests.base import BaseTestCase


class TestWrappers(BaseTestCase):
    def test_wrappers(self):
        wrappers = {
            api.BlackHoleHuey: storage.BlackHoleStorage,
            api.MemoryHuey: storage.MemoryStorage,
            api.RedisExpireHuey: storage.RedisExpireStorage,
            api.RedisHuey: storage.RedisStorage,
            api.SqliteHuey: storage.SqliteStorage,
        }
        for huey_wrapper, storage_class in wrappers.items():
            h = huey_wrapper('testhuey')
            self.assertEqual(h.name, 'testhuey')
            self.assertEqual(h.storage.name, 'testhuey')
            self.assertTrue(isinstance(h.storage, storage_class))

    def test_fake_wrapper(self):
        # This is kind-of a silly test, as we're essentially just testing
        # functools.partial(), but let's just make sure that parameters are
        # getting passed to the storage correctly - and that the storage is
        # initialized correctly.
        class BogusStorage(storage.BlackHoleStorage):
            def __init__(self, name, host='127.0.0.1', port=None, db=None):
                super(BogusStorage, self).__init__(name)
                self.host = host
                self.port = port
                self.db = db

        BH = partial(api.Huey, storage_class=BogusStorage, port=1337)

        bh = BH('test')
        self.assertEqual(bh.name, 'test')
        self.assertEqual(bh.storage.name, 'test')
        self.assertTrue(isinstance(bh.storage, BogusStorage))
        self.assertEqual(bh.storage.host, '127.0.0.1')
        self.assertEqual(bh.storage.port, 1337)
        self.assertTrue(bh.storage.db is None)

        bh2 = BH('test2', host='localhost', port=31337, db=15)
        self.assertEqual(bh2.storage.host, 'localhost')
        self.assertEqual(bh2.storage.port, 31337)
        self.assertEqual(bh2.storage.db, 15)
