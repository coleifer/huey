import datetime
import hashlib
import itertools
import os
import shutil
import threading
import unittest
try:
    from queue import Queue
except ImportError:
    from Queue import Queue

from redis.connection import ConnectionPool
from redis import Redis

from huey.api import Huey
from huey.api import MemoryHuey
from huey.api import PriorityRedisHuey
from huey.api import RedisExpireHuey
from huey.api import RedisHuey
from huey.api import SqliteHuey
from huey.constants import EmptyData
from huey.consumer import Consumer
from huey.exceptions import ConfigurationError
from huey.storage import FileStorage
from huey.storage import MemoryStorage
from huey.storage import RedisExpireStorage
from huey.tests.base import BaseTestCase
from huey.tests.base import TRAVIS


class StorageTests(object):
    destructive_reads = True

    def setUp(self):
        super(StorageTests, self).setUp()
        self.s = self.huey.storage
        self.s.flush_all()

    def tearDown(self):
        super(StorageTests, self).tearDown()
        self.s.flush_all()

    def test_queue_methods(self):
        for i in range(3):
            self.s.enqueue(b'item-%d' % i)

        # Remove two items (this API is not used, but we'll test it anyways).
        self.assertEqual(self.s.dequeue(), b'item-0')
        self.assertEqual(self.s.queue_size(), 2)
        self.assertEqual(self.s.enqueued_items(), [b'item-1', b'item-2'])
        self.assertEqual(self.s.dequeue(), b'item-1')
        self.assertEqual(self.s.dequeue(), b'item-2')
        self.assertTrue(self.s.dequeue() is None)

        self.assertEqual(self.s.queue_size(), 0)

        # Test flushing the queue.
        self.s.enqueue(b'item-3')
        self.assertEqual(self.s.queue_size(), 1)
        self.s.flush_queue()
        self.assertEqual(self.s.queue_size(), 0)

    def test_schedule_methods(self):
        timestamp = datetime.datetime(2000, 1, 2, 3, 4, 5)
        second = datetime.timedelta(seconds=1)

        items = ((b'p1', timestamp + second),
                 (b'p0', timestamp),
                 (b'n1', timestamp - second),
                 (b'p2', timestamp + second + second))
        for data, ts in items:
            self.s.add_to_schedule(data, ts)

        self.assertEqual(self.s.schedule_size(), 4)

        # Read from the schedule up-to the "p0" timestamp.
        sched = self.s.read_schedule(timestamp)
        self.assertEqual(sched, [b'n1', b'p0'])

        self.assertEqual(self.s.scheduled_items(), [b'p1', b'p2'])
        self.assertEqual(self.s.schedule_size(), 2)
        sched = self.s.read_schedule(datetime.datetime.now())
        self.assertEqual(sched, [b'p1', b'p2'])
        self.assertEqual(self.s.schedule_size(), 0)
        self.assertEqual(self.s.read_schedule(datetime.datetime.now()), [])

    def test_result_store_methods(self):
        # Put and peek at data. Verify missing keys return EmptyData sentinel.
        self.s.put_data(b'k1', b'v1')
        self.s.put_data(b'k2', b'v2')
        self.assertEqual(self.s.peek_data(b'k2'), b'v2')
        self.assertEqual(self.s.peek_data(b'k1'), b'v1')
        self.assertTrue(self.s.peek_data(b'kx') is EmptyData)
        self.assertEqual(self.s.result_store_size(), 2)

        # Verify we can overwrite existing keys and that pop will remove the
        # key/value pair. Subsequent pop on missing key will return EmptyData.
        self.s.put_data(b'k1', b'v1-x')
        self.assertEqual(self.s.peek_data(b'k1'), b'v1-x')
        self.assertEqual(self.s.pop_data(b'k1'), b'v1-x')
        if self.destructive_reads:
            self.assertTrue(self.s.pop_data(b'k1') is EmptyData)
        else:
            self.assertEqual(self.s.pop_data(b'k1'), b'v1-x')
            self.assertTrue(self.s.delete_data(b'k1'))

        self.assertFalse(self.s.has_data_for_key(b'k1'))
        self.assertTrue(self.s.has_data_for_key(b'k2'))
        self.assertEqual(self.s.result_store_size(), 1)

        # Test put-if-empty.
        self.assertTrue(self.s.put_if_empty(b'k1', b'v1-y'))
        self.assertFalse(self.s.put_if_empty(b'k1', b'v1-z'))
        self.assertEqual(self.s.peek_data(b'k1'), b'v1-y')

        # Test deletion.
        self.assertTrue(self.s.put_if_empty(b'k3', b'v3'))
        self.assertTrue(self.s.delete_data(b'k3'))
        self.assertFalse(self.s.delete_data(b'k3'))

        # Test introspection.
        state = self.s.result_items()  # Normalize keys to unicode strings.
        clean = {k.decode('utf8') if isinstance(k, bytes) else k: v
                 for k, v in state.items()}
        self.assertEqual(clean, {'k1': b'v1-y', 'k2': b'v2'})
        self.s.flush_results()
        self.assertEqual(self.s.result_store_size(), 0)
        self.assertEqual(self.s.result_items(), {})

    def test_priority(self):
        if not self.s.priority:
            raise unittest.SkipTest('priority support required')

        priorities = (1, None, 5, None, 3, None, 9, None, 7, 0)
        for i, priority in enumerate(priorities):
            item = 'i%s-%s' % (i, priority)
            self.s.enqueue(item.encode('utf8'), priority)

        expected = [b'i6-9', b'i8-7', b'i2-5', b'i4-3', b'i0-1',
                    b'i1-None', b'i3-None', b'i5-None', b'i7-None', b'i9-0']
        self.assertEqual([self.s.dequeue() for _ in range(10)], expected)

    def test_consumer_integration(self):
        @self.huey.task()
        def task_a(n):
            return n + 1

        with self.consumer_context():
            r1 = task_a(1)
            r2 = task_a(2)
            r3 = task_a(3)

            self.assertEqual(r1.get(blocking=True, timeout=5), 2)
            self.assertEqual(r2.get(blocking=True, timeout=5), 3)
            self.assertEqual(r3.get(blocking=True, timeout=5), 4)

            task_a.revoke()
            self.assertTrue(task_a.is_revoked())
            self.assertTrue(task_a.restore())


class TestMemoryStorage(StorageTests, BaseTestCase):
    def get_huey(self):
        return MemoryHuey(utc=False)


class TestRedisStorage(StorageTests, BaseTestCase):
    def get_huey(self):
        return RedisHuey(utc=False)

    def test_conflicting_init_args(self):
        options = {'host': 'localhost', 'url': 'redis://localhost',
                   'connection_pool': ConnectionPool()}
        combinations = itertools.combinations(options.items(), 2)
        for kwargs in (dict(item) for item in combinations):
            self.assertRaises(ConfigurationError, lambda: RedisHuey(**kwargs))

        # None values are fine, however.
        RedisHuey(host=None, port=None, db=None, url='redis://localhost')


class TestRedisExpireStorage(StorageTests, BaseTestCase):
    # Note that this does not subclass the StorageTests. This is partly because
    # the functionality should already be covered by the TestRedisStorage, as
    # the RedisExpireStorage is a subclass of RedisStorage -- but also because
    # the way the result store functions is fundamentally different, relying on
    # the database to handle result removal via expiration.
    destructive_reads = False

    def get_huey(self):
        return RedisExpireHuey(expire_time=3600, utc=False, blocking=False)

    def test_expire_results(self):
        self.s.put_data(b'k1', b'v1')
        self.s.put_data(b'k2', b'v2', is_result=True)

        conn = self.s.conn  # Underlying Redis client.

        # By default the put_data() API treats keys as being persistent. If we
        # specifically included the "is_result=True" flag, then the key will be
        # given a TTL.
        self.assertEqual(conn.ttl(self.s.result_key(b'k1')), -1)
        self.assertEqual(conn.ttl(self.s.result_key(b'k2')), 3600)

        # Non-existant keys return -2. See redis docs for TTL command.
        self.assertEqual(conn.ttl(self.s.result_key(b'k3')), -2)

        # Non-expired keys return -1.
        conn.set(self.s.result_key(b'k3'), b'v3')
        self.assertEqual(conn.ttl(self.s.result_key(b'k3')), -1)

        # Verify behavior of put_if_empty and has_data_for_key.
        self.assertTrue(self.s.has_data_for_key(b'k2'))
        self.assertFalse(self.s.put_if_empty(b'k2', b'v2-x'))
        self.assertFalse(self.s.has_data_for_key(b'k4'))
        self.assertTrue(self.s.put_if_empty(b'k4', b'v4'))

        # Verify behavior of delete.
        self.assertTrue(self.s.delete_data(b'k2'))
        self.assertFalse(self.s.delete_data(b'k2'))

        # Check the result items.
        self.assertEqual(self.s.result_items(), {
            b'k1': b'v1',
            b'k3': b'v3',
            b'k4': b'v4'})
        self.assertEqual(self.s.result_store_size(), 3)

    def test_integration_2(self):
        @self.huey.task()
        def task_a(n):
            return n + 1

        r1, r2, r3 = [task_a(i) for i in (1, 2, 3)]
        r2.revoke()
        self.assertTrue(r2.is_revoked())
        self.assertEqual(self.huey.result_count(), 1)  # Revoke key.

        self.assertEqual(self.execute_next(), 2)
        self.assertEqual(self.huey.result_count(), 2)  # Revoke key and r1.

        self.assertTrue(self.execute_next() is None)
        self.assertEqual(self.huey.result_count(), 1)  # Just r1 now.
        self.assertFalse(r2.is_revoked())

        self.assertEqual(self.execute_next(), 4)
        self.assertEqual(self.huey.result_count(), 2)  # r1 and r3.

        for _ in range(3):
            self.assertEqual(r1(), 2)
            self.assertEqual(r3(), 4)
            r1.reset()
            r3.reset()
        self.assertEqual(self.huey.result_count(), 2)  # r1 and r3 still there.


def get_redis_version():
    return int(Redis().info()['redis_version'].split('.', 1)[0])


@unittest.skipIf(get_redis_version() < 5, 'Requires Redis >= 5.0')
class TestPriorityRedisStorage(TestRedisStorage):
    def get_huey(self):
        return PriorityRedisHuey(utc=False)


@unittest.skipIf(get_redis_version() < 5, 'Requires Redis >= 5.0')
class TestPriorityRedisStorageNotBlocking(TestRedisStorage):
    def get_huey(self):
        return PriorityRedisHuey(utc=False, blocking=False)


class TestSqliteStorage(StorageTests, BaseTestCase):
    def tearDown(self):
        super(TestSqliteStorage, self).tearDown()
        if os.path.exists('huey_storage.db'):
            os.unlink('huey_storage.db')

    def get_huey(self):
        return SqliteHuey(filename='huey_storage.db', timeout=3)

    def test_timeout(self):
        self.assertEqual(self.s._timeout, 3)
        curs = self.s.conn.execute('pragma busy_timeout')
        self.assertEqual(curs.fetchone(), (3000,))


class TestFileStorageMethods(StorageTests, BaseTestCase):
    path = '/tmp/test-huey-storage'
    result_path = '/tmp/test-huey-storage/results'
    queue_path = '/tmp/test-huey-storage/queue'

    def tearDown(self):
        super(TestFileStorageMethods, self).tearDown()
        if os.path.exists(self.path):
            shutil.rmtree(self.path)

    def get_huey(self):
        return Huey('test-file-storage', storage_class=FileStorage,
                    path=self.path, levels=2, use_thread_lock=True)

    def test_filesystem_result_store(self):
        s = self.huey.storage
        self.assertEqual(s.result_items(), {})

        keys = (b'k1', b'k2', b'kx')
        for key in keys:
            checksum = hashlib.md5(key).hexdigest()
            b0, b1 = checksum[0], checksum[1]
            # Default is to use two levels.
            key_path = os.path.join(self.result_path, b0, b1)
            key_filename = os.path.join(key_path, checksum)

            self.assertFalse(os.path.exists(key_filename))
            self.assertFalse(os.path.exists(key_path))

            s.put_data(key, b'test-%s' % key)
            self.assertTrue(os.path.exists(key_path))
            self.assertTrue(os.path.exists(key_filename))

            self.assertEqual(s.pop_data(key), b'test-%s' % key)
            self.assertTrue(os.path.exists(key_path))
            self.assertFalse(os.path.exists(key_filename))

        # Flushing the results blows away everything.
        s.flush_results()
        self.assertTrue(os.path.exists(self.result_path))
        self.assertEqual(os.listdir(self.result_path), [])

    def test_fs_multithreaded(self):
        l = threading.Lock()

        def create_tasks(t, n, q):
            for i in range(n):
                with l:
                    message = str((t * n) + i)
                    self.huey.storage.enqueue(message.encode('utf8'))
                    q.put(message)

        def dequeue_tasks(q):
            while True:
                with l:
                    data = self.huey.storage.dequeue()
                    if data is None:
                        break
                    q.put(data.decode('utf8'))

        nthreads = 10
        ntasks = 50
        in_q = Queue()
        threads = []
        for i in range(nthreads):
            t = threading.Thread(target=create_tasks, args=(i, ntasks, in_q))
            t.daemon = True
            threads.append(t)

        for t in threads: t.start()
        for t in threads: t.join(timeout=10.)

        self.assertEqual(self.huey.pending_count(), nthreads * ntasks)

        out_q = Queue()
        threads = []
        for i in range(nthreads):
            t = threading.Thread(target=dequeue_tasks, args=(out_q,))
            t.daemon = True
            threads.append(t)

        for t in threads: t.start()
        for t in threads: t.join(timeout=10.)

        self.assertEqual(out_q.qsize(), nthreads * ntasks)
        self.assertEqual(self.huey.pending_count(), 0)

        # Ensure that the order in which tasks were enqueued is the order in
        # which they are dequeued.
        for i in range(nthreads * ntasks):
            self.assertEqual(in_q.get(), out_q.get())

    @unittest.skipIf(TRAVIS, 'skipping test that is flaky on travis-ci')
    def test_consumer_integration(self):
        return super(TestFileStorageMethods, self).test_consumer_integration()
