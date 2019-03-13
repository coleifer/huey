import datetime

from h2.api import PeriodicTask
from h2.api import Result
from h2.api import Task
from h2.api import TaskWrapper
from h2.api import crontab
from h2.storage import MemoryHuey
from h2.tests.base import BaseTestCase


class APITestCase(BaseTestCase):
    def setUp(self):
        super(APITestCase, self).setUp()
        self.huey = MemoryHuey(utc=False)


class TestQueue(APITestCase):
    def test_workflow(self):
        @self.huey.task()
        def task_a(n):
            return n + 1

        result = task_a(3)
        self.assertTrue(isinstance(result, Result))
        self.assertEqual(len(self.huey), 1)  # One item in queue.
        task = self.huey.dequeue()
        self.assertEqual(len(self.huey), 0)  # No items in queue.
        self.assertEqual(self.huey.result_count(), 0)  # No results.

        self.assertEqual(result.id, task.id)  # Result points to task.
        self.assertTrue(result.get() is None)

        # Execute task, placing result in result store and returning the value
        # produced by the task.
        self.assertEqual(self.huey.execute(task), 4)

        # Data is present in result store, we can read it from the result
        # instance, and after reading the value is removed.
        self.assertEqual(self.huey.result_count(), 1)
        self.assertEqual(result.get(), 4)
        self.assertEqual(self.huey.result_count(), 0)

    def test_scheduling(self):
        @self.huey.task()
        def task_a(n):
            return n + 1

        result = task_a.schedule((3,), delay=60)
        self.assertEqual(len(self.huey), 1)
        self.assertEqual(self.huey.scheduled_count(), 0)

        task = self.huey.dequeue()
        value = self.huey.execute(task)  # Will not be run, will be scheduled.
        self.assertTrue(value is None)
        self.assertEqual(len(self.huey), 0)
        self.assertEqual(self.huey.scheduled_count(), 1)

        sched = self.huey.scheduled()
        self.assertEqual(len(sched), 1)
        self.assertEqual(sched[0], task)


class TestDecorators(APITestCase):
    def test_task_decorator(self):
        @self.huey.task()
        def task_a(n):
            return n + 1

        self.assertTrue(isinstance(task_a, TaskWrapper))

        task = task_a.s(3)
        self.assertTrue(isinstance(task, Task))

        self.assertEqual(task.retries, 0)
        self.assertEqual(task.retry_delay, 0)
        self.assertEqual(task.args, (3,))
        self.assertEqual(task.kwargs, {})
        self.assertEqual(task.execute(), 4)

    def test_task_parameters(self):
        @self.huey.task(retries=2, retry_delay=1, context=True, name='tb')
        def task_b(n, task=None):
            return (n + 1, task.id, task.retries, task.retry_delay)

        task = task_b.s(2)
        self.assertEqual(task.retries, 2)
        self.assertEqual(task.retry_delay, 1)
        self.assertEqual(task.args, (2,))
        self.assertEqual(task.kwargs, {})

        result, tid, retries, retry_delay = task.execute()
        self.assertEqual(result, 3)
        self.assertEqual(retries, 2)
        self.assertEqual(retry_delay, 1)
        self.assertEqual(tid, task.id)

    def test_periodic_task(self):
        @self.huey.periodic_task(crontab(minute='1'))
        def task_p():
            return 123

        task = task_p.s()
        self.assertTrue(isinstance(task, PeriodicTask))
        self.assertEqual(task.execute(), 123)
