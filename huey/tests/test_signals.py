import datetime

from huey.signals import *
from huey.tests.base import BaseTestCase


class TestSignals(BaseTestCase):
    def setUp(self):
        super(TestSignals, self).setUp()
        self._state = []

        @self.huey.signal()
        def signal_handle(signal, task, *args):
            self._state.append((signal, task, args))

    def assertSignals(self, expected):
        self.assertEqual([s[0] for s in self._state], expected)
        self._state = []

    def test_signals_simple(self):
        @self.huey.task()
        def task_a(n):
            return n + 1

        r = task_a(3)
        self.assertSignals([SIGNAL_ENQUEUED])
        self.assertEqual(self.execute_next(), 4)
        self.assertSignals([SIGNAL_EXECUTING, SIGNAL_COMPLETE])

        r = task_a.schedule((2,), delay=60)
        self.assertSignals([SIGNAL_ENQUEUED])
        self.assertTrue(self.execute_next() is None)
        self.assertSignals([SIGNAL_SCHEDULED])

        r = task_a(None)
        self.assertSignals([SIGNAL_ENQUEUED])
        self.assertTrue(self.execute_next() is None)
        self.assertSignals([SIGNAL_EXECUTING, SIGNAL_ERROR])

    def test_signal_complete_result_ready(self):
        @self.huey.task()
        def task_a(n):
            return n + 1

        results = []

        @self.huey.signal(SIGNAL_COMPLETE)
        def on_complete(sig, task, *_):
            results.append(self.huey.result(task.id))

        r = task_a(2)
        self.assertEqual(self.execute_next(), 3)
        self.assertEqual(results, [3])

    def test_signals_on_retry(self):
        @self.huey.task(retries=1)
        def task_a(n):
            return n + 1

        r = task_a(None)
        self.assertSignals([SIGNAL_ENQUEUED])
        self.assertTrue(self.execute_next() is None)
        self.assertSignals([SIGNAL_EXECUTING, SIGNAL_ERROR, SIGNAL_RETRYING,
                            SIGNAL_ENQUEUED])
        self.assertTrue(self.execute_next() is None)
        self.assertSignals([SIGNAL_EXECUTING, SIGNAL_ERROR])

        @self.huey.task(retries=1, retry_delay=60)
        def task_b(n):
            return n + 1

        r = task_b(None)
        self.assertSignals([SIGNAL_ENQUEUED])
        self.assertTrue(self.execute_next() is None)
        self.assertSignals([SIGNAL_EXECUTING, SIGNAL_ERROR, SIGNAL_RETRYING,
                            SIGNAL_SCHEDULED])

    def test_signals_revoked(self):
        @self.huey.task()
        def task_a(n):
            return n + 1

        task_a.revoke(revoke_once=True)
        r = task_a(2)
        self.assertSignals([SIGNAL_ENQUEUED])
        self.assertTrue(self.execute_next() is None)
        self.assertSignals([SIGNAL_REVOKED])

        r = task_a(3)
        self.assertEqual(self.execute_next(), 4)
        self.assertSignals([SIGNAL_ENQUEUED, SIGNAL_EXECUTING,
                            SIGNAL_COMPLETE])

    def test_signals_locked(self):
        @self.huey.task()
        @self.huey.lock_task('lock-a')
        def task_a(n):
            return n + 1

        r = task_a(1)
        self.assertSignals([SIGNAL_ENQUEUED])
        self.assertEqual(self.execute_next(), 2)
        self.assertSignals([SIGNAL_EXECUTING, SIGNAL_COMPLETE])

        with self.huey.lock_task('lock-a'):
            r = task_a(2)
            self.assertSignals([SIGNAL_ENQUEUED])
            self.assertTrue(self.execute_next() is None)
            self.assertSignals([SIGNAL_EXECUTING, SIGNAL_LOCKED])

    def test_signal_expired(self):
        @self.huey.task(expires=10)
        def task_a(n):
            return n + 1

        now = datetime.datetime.now()
        expires = now + datetime.timedelta(seconds=15)
        r = task_a(2)
        self.assertSignals([SIGNAL_ENQUEUED])
        self.assertTrue(self.execute_next(expires) is None)
        self.assertSignals([SIGNAL_EXPIRED])

        r = task_a(3)
        self.assertSignals([SIGNAL_ENQUEUED])
        self.assertTrue(self.execute_next(), 4)
        self.assertSignals([SIGNAL_EXECUTING, SIGNAL_COMPLETE])

    def test_specific_handler(self):
        extra_state = []

        @self.huey.signal(SIGNAL_EXECUTING)
        def extra_handler(signal, task):
            extra_state.append(task.args[0])

        @self.huey.task()
        def task_a(n):
            return n + 1

        r = task_a(3)
        self.assertEqual(extra_state, [])
        self.assertEqual(self.execute_next(), 4)
        self.assertEqual(extra_state, [3])
        self.assertSignals([SIGNAL_ENQUEUED, SIGNAL_EXECUTING,
                            SIGNAL_COMPLETE])

        r2 = task_a(1)
        self.assertEqual(self.execute_next(), 2)
        self.assertEqual(extra_state, [3, 1])
        self.assertSignals([SIGNAL_ENQUEUED, SIGNAL_EXECUTING,
                            SIGNAL_COMPLETE])

        self.huey.disconnect_signal(extra_handler, SIGNAL_EXECUTING)
        r3 = task_a(2)
        self.assertEqual(self.execute_next(), 3)
        self.assertEqual(extra_state, [3, 1])
        self.assertSignals([SIGNAL_ENQUEUED, SIGNAL_EXECUTING,
                            SIGNAL_COMPLETE])

    def test_multi_handlers(self):
        state1 = []
        state2 = []

        @self.huey.signal(SIGNAL_EXECUTING, SIGNAL_COMPLETE)
        def handler1(signal, task):
            state1.append(signal)

        @self.huey.signal(SIGNAL_EXECUTING, SIGNAL_COMPLETE)
        def handler2(signal, task):
            state2.append(signal)

        @self.huey.task()
        def task_a(n):
            return n + 1

        r = task_a(1)
        self.assertEqual(self.execute_next(), 2)
        self.assertEqual(state1, ['executing', 'complete'])
        self.assertEqual(state2, ['executing', 'complete'])

        self.huey.disconnect_signal(handler1, SIGNAL_COMPLETE)
        self.huey.disconnect_signal(handler2)

        r2 = task_a(2)
        self.assertEqual(self.execute_next(), 3)
        self.assertEqual(state1, ['executing', 'complete', 'executing'])
        self.assertEqual(state2, ['executing', 'complete'])
