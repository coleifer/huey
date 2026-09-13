import asyncio

from huey.api import Result
from huey.api import ResultGroup
from huey.api import Task
from huey.contrib.asyncio import aget_result
from huey.contrib.asyncio import aget_result_group
from huey.exceptions import ResultTimeout
from huey.exceptions import TaskException
from huey.tests.base import BaseTestCase


class TestAsyncioHelpers(BaseTestCase):
    def setUp(self):
        super(TestAsyncioHelpers, self).setUp()
        self.huey.immediate = True

    def test_aget_result(self):
        @self.huey.task()
        def task_a(n):
            return n + 1

        async def main():
            return await aget_result(task_a(1))
        self.assertEqual(asyncio.run(main()), 2)

    def test_aget_result_error(self):
        @self.huey.task()
        def task_e():
            raise ValueError('uh-oh')

        async def main():
            return await aget_result(task_e())
        self.assertRaises(TaskException, asyncio.run, main())

    def test_aget_result_timeout(self):
        res = Result(self.huey, Task(id='missing'))

        async def main():
            return await aget_result(res, timeout=0.05)
        self.assertRaises(ResultTimeout, asyncio.run, main())

    def test_aget_result_group(self):
        @self.huey.task()
        def task_a(n):
            return n + 1

        async def main():
            return await aget_result_group(task_a.map([1, 2, 3]))
        self.assertEqual(asyncio.run(main()), [2, 3, 4])

    def test_aget_result_group_failure_stops_pending_results(self):
        @self.huey.task()
        def fail():
            raise ValueError('uh-oh')

        @self.huey.task()
        def value():
            return 42

        self.huey.immediate = False
        failed = fail()
        self.execute_next()
        pending = value()

        async def main():
            existing_tasks = asyncio.all_tasks()
            try:
                with self.assertRaises(TaskException):
                    await aget_result_group(ResultGroup([failed, pending]))

                # Returning from a failed group must leave no polling behind.
                pollers = asyncio.all_tasks() - existing_tasks
                self.assertFalse(pollers)
                # Stopping result polling must not revoke the actual task.
                self.assertFalse(pending.is_revoked())
                self.execute_next()
                self.assertEqual(pending.get(), 42)
            finally:
                # Also clean up the broken implementation when this test fails.
                remaining = asyncio.all_tasks() - existing_tasks
                for task in remaining:
                    task.cancel()
                await asyncio.gather(*remaining, return_exceptions=True)

        asyncio.run(main())

    def test_aget_result_group_cancelled(self):
        results = ResultGroup([
            Result(self.huey, Task(id='pending-a')),
            Result(self.huey, Task(id='pending-b'))])

        async def main():
            existing_tasks = asyncio.all_tasks()
            group = asyncio.create_task(aget_result_group(results))
            # Let the group start and submit both result waiters.
            started = asyncio.get_running_loop().create_future()
            asyncio.get_running_loop().call_soon(started.set_result, None)
            await started
            group.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await group
            self.assertFalse(asyncio.all_tasks() - existing_tasks)

        asyncio.run(main())
