import threading
import time

from huey import Huey
from huey import MemoryHuey
from huey import RedisHuey
from huey.contrib.helpers import RedisSemaphore
from huey.contrib.helpers import lock_task_semaphore
from huey.exceptions import ConfigurationError
from huey.storage import RedisStorage
from huey.tests.base import BaseTestCase
from huey.tests.test_storage import requires_redis


@requires_redis
class TestLockTaskSemaphore(BaseTestCase):
    def setUp(self):
        super(TestLockTaskSemaphore, self).setUp()
        self.semaphore = RedisSemaphore(self.huey, 'lock_a', 2)
        self.huey.storage.conn.delete(self.semaphore.key)

    def tearDown(self):
        self.huey.storage.conn.delete(self.semaphore.key)
        super(TestLockTaskSemaphore, self).tearDown()

    def get_huey(self):
        return RedisHuey()

    def test_redis_semaphore(self):
        s = self.semaphore
        aid1 = s.acquire()
        self.assertTrue(aid1 is not None)
        aid2 = s.acquire()
        self.assertTrue(aid2 is not None)  # We can acquire it twice.
        self.assertTrue(s.acquire() is None)  # Cannot acquire 3 times.
        self.assertEqual(s.release(aid2), 1)  # Release succeeded.
        self.assertEqual(s.release(aid2), 0)  # Already released.
        self.assertEqual(s.acquire(aid2), aid2)  # Re-acquired.
        self.assertEqual(s.acquire(aid2), aid2)  # No-op (still acquired).

        self.assertEqual(s.release(aid2), 1)  # Release succeeded.
        self.assertEqual(s.release(aid1), 1)  # Release succeeded.

        self.assertTrue(s.acquire() is not None)  # Acquire twice.
        self.assertTrue(s.acquire() is not None)
        self.assertTrue(s.acquire() is None)  # Cannot acquire 3 times.
        self.huey.storage.conn.delete(s.key)

    def test_semaphore_contention(self):
        s = RedisSemaphore(self.huey, 'lock_c', 5)
        self.huey.storage.conn.delete(s.key)
        acquired = []
        lock = threading.Lock()
        barrier = threading.Barrier(20)

        def acquire():
            barrier.wait()
            name = s.acquire()
            if name is not None:
                with lock:
                    acquired.append(name)

        threads = [threading.Thread(target=acquire) for _ in range(20)]
        for t in threads: t.start()
        for t in threads: t.join()

        self.assertEqual(len(acquired), 5)
        self.assertEqual(self.huey.storage.conn.zcard(s.key), 5)
        self.huey.storage.conn.delete(s.key)

    def test_semaphore_expiration(self):
        s = RedisSemaphore(self.huey, 'lock_e', 1, timeout=1)
        self.huey.storage.conn.delete(s.key)
        name = s.acquire()
        self.assertTrue(name is not None)
        self.assertTrue(s.acquire() is None)

        time.sleep(1.1)
        other = s.acquire()
        self.assertTrue(other is not None)

        # The expired holder cannot renew its way back in.
        self.assertFalse(s.renew(name))
        self.assertTrue(s.renew(other))
        self.assertEqual(self.huey.storage.conn.zcard(s.key), 1)
        self.huey.storage.conn.delete(s.key)

    def test_semaphore_renewed_while_running(self):
        @lock_task_semaphore(self.huey, 'lock_r', 1, timeout=1)
        def slow():
            time.sleep(1.5)
            return 'done'

        s = RedisSemaphore(self.huey, 'lock_r', 1, timeout=1)
        self.huey.storage.conn.delete(s.key)
        result = {}
        t = threading.Thread(target=lambda: result.update(v=slow()))
        t.start()
        time.sleep(1.2)
        self.assertTrue(s.acquire() is None)
        t.join()
        self.assertEqual(result['v'], 'done')
        self.assertEqual(self.huey.storage.conn.zcard(s.key), 0)

    def test_semaphore_storage_types(self):
        huey = Huey('test-sem-storage', storage_class=RedisStorage)
        s = RedisSemaphore(huey, 'lock_s', 1)
        huey.storage.conn.delete(s.key)
        name = s.acquire()
        self.assertTrue(name is not None)
        self.assertEqual(s.release(name), 1)

        # Constructing against a non-redis storage is deferred to first use.
        memory = RedisSemaphore(MemoryHuey('test-sem-memory'), 'lock_m', 1)
        self.assertRaises(ConfigurationError, memory.acquire)
