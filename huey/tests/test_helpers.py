from huey import RedisHuey
from huey.contrib.helpers import RedisSemaphore
from huey.contrib.helpers import lock_task_semaphore
from huey.exceptions import TaskLockedException
from huey.tests.base import BaseTestCase


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
