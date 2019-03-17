from huey.api import MemoryHuey
from huey.exceptions import TaskException
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

    def test_immediate_revoke_restore(self):
        @self.huey.task()
        def task_a(n):
            return n + 1

        task_a.revoke()
        r = task_a(3)
        self.assertEqual(len(self.huey), 0)
        self.assertEqual(self.huey.result_count(), 0)
        self.assertTrue(r.get() is None)

        task_a.restore()
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
