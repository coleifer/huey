import datetime

from huey.api import Huey
from huey.api import MemoryHuey
from huey.exceptions import TaskException
from huey.storage import BlackHoleStorage
from huey.tests.base import BaseTestCase


class TestImmediate(BaseTestCase):
    def get_huey(self):
        return MemoryHuey(immediate=True, utc=False)

    def test_immediate(self):
        @self.huey.task()
        def task_a(n):
            return n + 1

        r = task_a(3)

        # Task is not enqueued, but the result *is* stored in the result-store.
        self.assertEqual(len(self.huey), 0)
        self.assertEqual(self.huey.result_count(), 1)
        self.assertEqual(r.get(), 4)

        # After reading, result is removed, as we would expect.
        self.assertEqual(self.huey.result_count(), 0)

        # Cannot add 1 to "None", this produces an error. We get the usual
        # TaskException, which wraps the TypeError.
        r_err = task_a(None)
        self.assertRaises(TaskException, r_err.get)

    def test_immediate_pipeline(self):
        @self.huey.task()
        def add(a, b):
            return a + b

        p = add.s(3, 4).then(add, 5).then(add, 6).then(add, 7)
        result_group = self.huey.enqueue(p)
        self.assertEqual(result_group(), [7, 12, 18, 25])

    def test_immediate_scheduling(self):
        @self.huey.task()
        def task_a(n):
            return n + 1

        r = task_a.schedule((3,), delay=10)

        # Task is not enqueued, no result is generated, the task is added to
        # the schedule, however -- even though the scheduler never runs in
        # immediate mode.
        self.assertEqual(len(self.huey), 0)
        self.assertEqual(self.huey.result_count(), 0)
        self.assertEqual(self.huey.scheduled_count(), 1)
        self.assertTrue(r.get() is None)

    def test_immediate_reschedule(self):
        state = []

        @self.huey.task(context=True)
        def task_s(task=None):
            state.append(task.id)
            return 1

        r = task_s.schedule(delay=60)
        self.assertEqual(len(self.huey), 0)
        self.assertTrue(r() is None)

        r2 = r.reschedule()
        self.assertTrue(r.id != r2.id)
        self.assertEqual(state, [r2.id])
        self.assertEqual(r2(), 1)
        self.assertEqual(len(self.huey), 0)
        self.assertTrue(r.is_revoked())

        # Because the scheduler never picks up the original task (r), its
        # revocation key sits in the result store and the task is in the
        # schedule still.
        self.assertEqual(self.huey.result_count(), 1)
        self.assertEqual(self.huey.scheduled_count(), 1)

    def test_immediate_revoke_restore(self):
        @self.huey.task()
        def task_a(n):
            return n + 1

        task_a.revoke()
        r = task_a(3)
        self.assertEqual(len(self.huey), 0)
        self.assertTrue(r.get() is None)

        self.assertTrue(task_a.restore())
        r = task_a(4)
        self.assertEqual(r.get(), 5)

    def test_swap_immediate(self):
        @self.huey.task()
        def task_a(n):
            return n + 1

        r = task_a(1)
        self.assertEqual(r.get(), 2)

        self.huey.immediate = False
        r = task_a(2)
        self.assertEqual(len(self.huey), 1)
        self.assertEqual(self.huey.result_count(), 0)
        task = self.huey.dequeue()
        self.assertEqual(self.huey.execute(task), 3)
        self.assertEqual(r.get(), 3)

        self.huey.immediate = True
        r = task_a(3)
        self.assertEqual(r.get(), 4)
        self.assertEqual(len(self.huey), 0)
        self.assertEqual(self.huey.result_count(), 0)

    def test_map(self):
        @self.huey.task()
        def task_a(n):
            return n + 1

        result_group = task_a.map(range(8))
        self.assertEqual(result_group(), [1, 2, 3, 4, 5, 6, 7, 8])


class NoUseException(Exception): pass
class NoUseStorage(BlackHoleStorage):
    def enqueue(self, data, priority=None): raise NoUseException()
    def dequeue(self): raise NoUseException()
    def add_to_schedule(self, data, ts, utc): raise NoUseException()
    def read_schedule(self, ts): raise NoUseException()
    def put_data(self, key, value): raise NoUseException()
    def peek_data(self, key): raise NoUseException()
    def pop_data(self, key): raise NoUseException()
    def has_data_for_key(self, key): raise NoUseException()
    def put_if_empty(self, key, value): raise NoUseException()
class NoUseHuey(Huey):
    def get_storage(self, **storage_kwargs):
        return NoUseStorage()


class TestImmediateMemoryStorage(BaseTestCase):
    def get_huey(self):
        return NoUseHuey(utc=False)

    def test_immediate_storage(self):
        @self.huey.task()
        def task_a(n):
            return n + 1

        self.huey.immediate = True

        # If any operation happens to touch the "real" storage engine, an
        # exception will be raised. These tests validate that immediate mode
        # doesn't accidentally interact with the live storage.
        res = task_a(2)
        self.assertEqual(res(), 3)

        task_a.revoke()
        res = task_a(3)
        self.assertTrue(res() is None)
        self.assertTrue(task_a.restore())

        res = task_a(4)
        self.assertEqual(res(), 5)

        eta = datetime.datetime.now() + datetime.timedelta(seconds=60)
        res = task_a.schedule((5,), eta=eta)
        self.assertTrue(res() is None)

        minus_1 = eta - datetime.timedelta(seconds=1)
        self.assertEqual(self.huey.read_schedule(minus_1), [])

        tasks = self.huey.read_schedule(eta)
        self.assertEqual([t.id for t in tasks], [res.id])
        self.assertTrue(res() is None)

        # Switch back to regular storage / non-immediate mode.
        self.huey.immediate = False
        self.assertRaises(NoUseException, task_a, 1)

        # Switch back to immediate mode.
        self.huey.immediate = True
        res = task_a(10)
        self.assertEqual(res(), 11)

    def test_immediate_real_storage(self):
        self.huey.immediate_use_memory = False

        @self.huey.task()
        def task_a(n):
            return n + 1

        self.huey.immediate = True
        self.assertRaises(NoUseException, task_a, 1)

        self.huey.immediate = False
        self.assertRaises(NoUseException, task_a, 2)
