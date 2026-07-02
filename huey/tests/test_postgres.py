import gc
import os
import threading
import time
import unittest
import weakref

try:
    import psycopg
except ImportError:
    psycopg = None

from huey.api import PostgresHuey
from huey.tests.base import BaseTestCase
from huey.tests.test_storage import StorageTests


PG_DSN = os.environ.get('HUEY_PG_DSN') or 'postgresql:///huey_test'


def pg_available():
    if psycopg is None:
        return False
    try:
        psycopg.connect(PG_DSN, connect_timeout=2).close()
    except Exception:
        return False
    return True


requires_postgres = unittest.skipIf(not pg_available(),
                                    'requires postgres server')


@requires_postgres
class TestPostgresStorage(StorageTests, BaseTestCase):
    def get_huey(self, **kwargs):
        kwargs.setdefault('read_timeout', 0.1)
        return PostgresHuey('test-pg', dsn=PG_DSN, utc=False, **kwargs)

    def tearDown(self):
        super(TestPostgresStorage, self).tearDown()
        self.huey.storage.close()

    @classmethod
    def tearDownClass(cls):
        super(TestPostgresStorage, cls).tearDownClass()
        conn = psycopg.connect(PG_DSN, autocommit=True)
        for tbl in ('huey_kv', 'huey_schedule', 'huey_task', 'huey_counter'):
            conn.execute('drop table if exists %s' % tbl)
        conn.close()

    def test_blocking_dequeue_notify(self):
        huey = self.get_huey(read_timeout=2)
        storage = huey.storage

        def enqueue():
            time.sleep(0.2)
            self.s.enqueue(b'notified')
        t = threading.Thread(target=enqueue)

        start = time.monotonic()
        t.start()
        try:
            data = storage.dequeue()
        finally:
            t.join()
        elapsed = time.monotonic() - start

        self.assertEqual(data, b'notified')
        self.assertLess(elapsed, 1.5)  # Notify wakes well under read_timeout.
        storage.close()

    def test_concurrent_dequeue_disjoint(self):
        n = 50
        for i in range(n):
            self.s.enqueue(b'task-%03d' % i)

        hueys = [self.get_huey(blocking=False) for _ in range(4)]
        results = [[] for _ in hueys]
        barrier = threading.Barrier(len(hueys))

        def run(idx):
            storage = hueys[idx].storage
            barrier.wait()
            while True:
                data = storage.dequeue()
                if data is None:
                    break
                results[idx].append(data)

        threads = [threading.Thread(target=run, args=(i,))
                   for i in range(len(hueys))]
        for t in threads: t.start()
        for t in threads: t.join()

        # Every task claimed exactly once across concurrent consumers.
        accum = [data for result in results for data in result]
        self.assertEqual(len(accum), n)
        self.assertEqual(sorted(accum), [b'task-%03d' % i for i in range(n)])
        for huey in hueys:
            huey.storage.close()

    def test_long_queue_name(self):
        huey = PostgresHuey('q' * 80, dsn=PG_DSN, utc=False, read_timeout=0.1)
        s = huey.storage
        self.assertTrue(len(s.channel.encode('utf-8')) <= 63)
        s.enqueue(b'data')
        self.assertEqual(s.dequeue(), b'data')
        self.assertTrue(s.dequeue() is None)  # Exercise the listen path.
        s.flush_all()
        s.close()

    def test_dead_thread_listen_conn_released(self):
        refs = []

        def dq():
            self.s.dequeue()
            refs.append(weakref.ref(self.s._listen_local.conn))

        for _ in range(3):
            t = threading.Thread(target=dq)
            t.start()
            t.join()

        gc.collect()
        self.assertEqual(len(refs), 3)
        self.assertTrue(all(r() is None for r in refs))

    @unittest.skipIf(not hasattr(os, 'fork'), 'requires os.fork()')
    def test_fork_reconnect(self):
        self.assertEqual(self.s.queue_size(), 0)  # Open parent connection.

        pid = os.fork()
        if pid == 0:
            try:
                self.s.enqueue(b'from-child')
                ok = self.s.queue_size() == 1
            except Exception:
                ok = False
            os._exit(0 if ok else 1)

        _, status = os.waitpid(pid, 0)
        self.assertEqual(os.WEXITSTATUS(status), 0)

        # Parent connection is intact and sees the child's task.
        self.assertEqual(self.s.dequeue(), b'from-child')
        self.assertEqual(self.s.queue_size(), 0)
