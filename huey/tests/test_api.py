import datetime
import inspect

from huey.api import MemoryHuey
from huey.api import PeriodicTask
from huey.api import Result
from huey.api import Task
from huey.api import TaskWrapper
from huey.api import crontab
from huey.api import _unsupported
from huey.constants import EmptyData
from huey.exceptions import CancelExecution
from huey.exceptions import ConfigurationError
from huey.exceptions import ResultTimeout
from huey.exceptions import RetryTask
from huey.exceptions import TaskException
from huey.exceptions import TaskLockedException
from huey.serializer import SignedSerializer
from huey.tests.base import BaseTestCase


class TestError(Exception):
    def __init__(self, m=None):
        self._m = m
    def __repr__(self):
        return 'TestError(%s)' % self._m

class ExcCounter(Exception):
    counter = 0
    def __init__(self):
        ExcCounter.counter += 1
        self._v = ExcCounter.counter
    def __repr__(self):
        return 'ExcCounter(%s)' % self._v



class TestQueue(BaseTestCase):
    def setUp(self):
        super(TestQueue, self).setUp()
        ExcCounter.counter = 0

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

    def test_result_store(self):
        @self.huey.task()
        def task_a(n):
            if n == 2:
                return None
            else:
                return n - 1

        r1, r2, r3 = [task_a(i) for i in (1, 2, 3)]
        for _ in range(3):
            self.execute_next()

        self.assertEqual(self.huey.result_count(), 2)  # Didn't store None.
        self.assertEqual(r1(), 0)
        self.assertTrue(r2._get(preserve=True) is EmptyData)
        self.assertTrue(r2() is None)
        self.assertEqual(r3(), 2)

        self.huey.store_none = True
        r4 = task_a(2)
        self.assertTrue(self.execute_next() is None)
        self.assertEqual(self.huey.result_count(), 1)
        self.assertTrue(r4._get() is None)

    def test_result_timeout(self):
        @self.huey.task()
        def task_a(n):
            return n

        r = task_a(1)
        with self.assertRaises(ResultTimeout):
            r.get(blocking=True, timeout=0.01)
        self.assertEqual(self.execute_next(), 1)
        self.assertEqual(self.huey.result_count(), 1)
        self.assertEqual(r(), 1)

    def test_scheduling(self):
        @self.huey.task()
        def task_a(n):
            return n + 1

        result = task_a.schedule((3,), delay=60)
        self.assertEqual(len(self.huey), 1)
        self.assertEqual(self.huey.scheduled_count(), 0)

        task = self.huey.dequeue()
        self.assertFalse(self.huey.ready_to_run(task))
        value = self.huey.execute(task)  # Will not be run, will be scheduled.
        self.assertTrue(value is None)
        self.assertEqual(len(self.huey), 0)
        self.assertEqual(self.huey.scheduled_count(), 1)

        sched = self.huey.scheduled()
        self.assertEqual(len(sched), 1)
        self.assertEqual(sched[0], task)

        # If we set the timestamp ahead, then we can verify the task will be
        # ready to run in 60 seconds (as expected).
        timestamp = datetime.datetime.now() + datetime.timedelta(seconds=60)
        self.assertTrue(self.huey.ready_to_run(task, timestamp))

        # Schedule a task with an old timestamp, it will be run immediately.
        eta = datetime.datetime(2000, 1, 1)  # In the past.
        result = task_a.schedule((4,), eta=eta)
        task2 = self.huey.dequeue()
        self.assertTrue(self.huey.ready_to_run(task2))
        self.assertEqual(self.huey.execute(task2), 5)
        self.assertEqual(result.get(), 5)

        # Original task still scheduled.
        sched = self.huey.scheduled()
        self.assertEqual(len(sched), 1)
        self.assertEqual(sched[0], task)

    def test_schedule_s(self):
        @self.huey.task()
        def add(a, b):
            return a + b

        task = add.s(1, 2, delay=10)
        task = task.then(add, 3, delay=20)
        r1, r2 = self.huey.enqueue(task)
        self.execute_next()

        sched = self.huey.scheduled()
        self.assertEqual(len(sched), 1)
        self.assertEqual(sched[0], task)

        t10 = datetime.datetime.now() + datetime.timedelta(seconds=10)
        self.assertFalse(self.huey.ready_to_run(task))
        self.assertTrue(self.huey.ready_to_run(task, t10))

        t20 = datetime.datetime.now() + datetime.timedelta(seconds=20)
        oc = task.on_complete
        self.assertFalse(self.huey.ready_to_run(oc, t10))
        self.assertTrue(self.huey.ready_to_run(oc, t20))

        r = r1.reschedule()
        self.assertEqual(len(self.huey), 1)
        self.assertEqual(self.execute_next(), 3)

        self.assertEqual(len(self.huey), 1)
        task = self.huey.dequeue()
        self.assertFalse(self.huey.ready_to_run(task))
        self.assertTrue(self.huey.ready_to_run(task, t20))
        self.assertEqual(self.huey.execute(task, t20), 6)

    def test_revoke_task(self):
        state = {}
        @self.huey.task()
        def task_a(n):
            state[n] = n  # Modify some state for extra visibility.
            return n + 1

        self.assertFalse(task_a.is_revoked())
        task_a.revoke()
        self.assertTrue(task_a.is_revoked())

        r1, r2, r3 = task_a(1), task_a(2), task_a(3)
        self.assertEqual(len(self.huey), 3)

        # The result-wrapper will indicate the tasks are revoked.
        for r in (r1, r2, r3):
            self.assertTrue(r.is_revoked())
            self.assertTrue(self.huey.is_revoked(r))
            # We don't have the task class when using an ID so this doesn't
            # work.
            self.assertFalse(self.huey.is_revoked(r.task.id))

        # Task is discarded and not executed, due to being revoked.
        t1 = self.huey.dequeue()
        self.assertTrue(self.huey.execute(t1) is None)
        self.assertTrue(r1.get() is None)
        self.assertEqual(state, {})

        # Next task is also discarded.
        self.assertTrue(r2.is_revoked())
        self.assertTrue(self.execute_next() is None)
        self.assertTrue(r2.get() is None)
        self.assertEqual(state, {})

        # Restore task, we will see side-effects and results of execution.
        self.assertTrue(task_a.is_revoked())  # Still revoked.
        self.assertTrue(r3.is_revoked())
        self.assertTrue(task_a.restore())
        self.assertFalse(task_a.is_revoked())
        self.assertFalse(r3.is_revoked())

        t3 = self.huey.dequeue()
        self.assertEqual(self.huey.execute(t3), 4)
        self.assertEqual(r3.get(), 4)
        self.assertEqual(state, {3: 3})

    def test_revoke_task_instance(self):
        state = {}
        @self.huey.task()
        def task_a(n):
            state[n] = n
            return n + 1

        r1, r2, r3 = [task_a(i) for i in (1, 2, 3)]
        self.assertEqual(len(self.huey), 3)

        r1.revoke()
        r3.revoke()

        self.assertTrue(r1.is_revoked())
        self.assertFalse(r2.is_revoked())
        self.assertTrue(r3.is_revoked())

        self.assertTrue(self.huey.is_revoked(r1))
        self.assertTrue(self.huey.is_revoked(r1.task.id))
        self.assertFalse(self.huey.is_revoked(r2))
        self.assertFalse(self.huey.is_revoked(r2.task.id))

        # Task is discarded and not executed, due to being revoked.
        t1 = self.huey.dequeue()
        self.assertTrue(self.huey.execute(t1) is None)
        self.assertTrue(r1.get() is None)
        self.assertEqual(state, {})

        # Second invocation will be executed normally.
        t2 = self.huey.dequeue()
        self.assertEqual(self.huey.execute(t2), 3)
        self.assertEqual(r2.get(), 3)
        self.assertEqual(state, {2: 2})

        # Third invocation is also revoked, but we will restore it beforehand.
        t3 = self.huey.dequeue()
        r3.restore()
        self.assertFalse(r3.is_revoked())
        self.assertEqual(self.huey.execute(t3), 4)
        self.assertEqual(r3.get(), 4)
        self.assertEqual(state, {2: 2, 3: 3})

        # Attempting to re-enqueue and re-execute the revoked t1 will now work,
        # as it is only revoked once by default.
        self.assertFalse(r1.is_revoked())
        self.huey.enqueue(t1)
        self.assertEqual(self.execute_next(), 2)
        self.assertEqual(state, {1: 1, 2: 2, 3: 3})
        self.assertFalse(r1.is_revoked())  # Still revoked.

    def test_revoke_task_instance_persistent(self):
        state = []
        @self.huey.task()
        def task_a(n):
            state.append(n)
            return n + 1

        r1 = task_a(1)
        r2 = task_a(2)
        r1.revoke(revoke_once=False)
        r2.revoke()
        self.assertTrue(r1.is_revoked())
        self.assertTrue(r2.is_revoked())

        t1 = self.huey.dequeue()
        self.assertTrue(self.huey.execute(t1) is None)
        self.assertTrue(r1.is_revoked())

        t2 = self.huey.dequeue()
        self.assertTrue(self.huey.execute(t2) is None)
        self.assertFalse(r2.is_revoked())  # No longer revoked.
        self.assertEqual(state, [])

        self.huey.enqueue(t1)
        self.huey.enqueue(t2)
        self.assertTrue(self.execute_next() is None)
        self.assertEqual(self.execute_next(), 3)
        self.assertEqual(r2.get(), 3)
        self.assertEqual(state, [2])

        self.assertTrue(r1.is_revoked())
        self.assertFalse(r2.is_revoked())
        self.assertEqual(self.huey.result_count(), 1)  # t1's revoke id.

    def test_revoke_by_id(self):
        state = []
        @self.huey.task()
        def task_a(n):
            state.append(n)
            return n

        r1, r2, r3 = [task_a(i) for i in (1, 2, 3)]
        for r in (r1, r2, r3):
            self.huey.revoke_by_id(r.id)
            self.assertTrue(r.is_revoked())

        self.huey.restore_by_id(r2.id)  # Restore one instance.

        for _ in range(3):
            self.execute_next()

        self.assertEqual(state, [2])
        self.assertEqual(r2(), 2)
        self.assertTrue(r1() is None and r3() is None)

    def test_revoke_once(self):
        @self.huey.task()
        def task_a(n):
            return n + 1

        r1, r2, r3 = [task_a(i) for i in (1, 2, 3)]
        task_a.revoke(revoke_once=True)

        # The task (and all subtasks) now appear* to be revoked.
        self.assertTrue(task_a.is_revoked())
        for result in (r1, r2, r3):
            self.assertTrue(result.is_revoked())

        # However we'll see that this is not the case.
        for _ in range(3):
            self.execute_next()

            # After executing the first task, things are no longer revoked.
            self.assertFalse(task_a.is_revoked())

        self.assertTrue(r1() is None)
        self.assertEqual(r2(), 3)
        self.assertEqual(r3(), 4)

        # Verify everything has been consumed.
        self.assertEqual(len(self.huey), 0)
        self.assertEqual(self.huey.result_count(), 0)

    def test_revoke_until(self):
        @self.huey.task()
        def task_a(n):
            return n + 1

        timestamp = datetime.datetime(2000, 1, 1)
        second = datetime.timedelta(seconds=1)
        zero = datetime.timedelta(seconds=0)
        task_a.revoke(revoke_until=timestamp)

        # The task appears revoked if we specify timestamp 1s prior, and at the
        # timestamp, the task appears to be no longer revoked.
        revoked_ts = timestamp - second
        self.assertFalse(task_a.is_revoked(timestamp=timestamp, peek=True))
        self.assertTrue(task_a.is_revoked(timestamp=revoked_ts, peek=True))

        r1, r2, r3, r4 = [task_a(i) for i in (1, 2, 3, 4)]
        for delta in (-second, zero, second, -second):
            task = self.huey.dequeue()
            self.huey.execute(task, timestamp + delta)

        self.assertTrue(r1() is None)
        self.assertEqual(r2(), 3)
        self.assertEqual(r3(), 4)
        # The execute() code-path will clear the "revoked" flag if it appears
        # that the cutoff-time has been exceeded (we don't expect time to flow
        # backwards), so r4 will run *even though* the "apparent" timestamp
        # when it is executed is prior to the revocation being removed. This
        # happens because the key which contains the revocation metadata is no
        # longer present.
        self.assertEqual(r4(), 5)

        self.assertEqual(len(self.huey), 0)
        self.assertEqual(self.huey.result_count(), 0)

    def test_revoke_periodic(self):
        state = [0]
        @self.huey.periodic_task(crontab(minute='0'))
        def task_p():
            state[0] = state[0] + 1

        task_p.revoke()
        self.assertTrue(task_p.is_revoked())
        self.assertTrue(task_p.is_revoked())  # Verify check is idempotent.

        task_p.restore()
        self.assertFalse(task_p.is_revoked())
        self.assertFalse(task_p.restore())  # It is not revoked.

        task_p.revoke(revoke_once=True)
        self.assertTrue(task_p.is_revoked())
        self.assertTrue(task_p.is_revoked())  # Verify idempotent.

        r = task_p()
        self.execute_next()
        self.assertTrue(r() is None)
        self.assertEqual(state, [0])  # Task was not run, no side-effect.

        self.assertFalse(task_p.is_revoked())  # No longer revoked.

        timestamp = datetime.datetime(2000, 1, 1)
        second = datetime.timedelta(seconds=1)
        task_p.revoke(revoke_until=timestamp)
        self.assertFalse(task_p.is_revoked(timestamp=timestamp))
        self.assertFalse(task_p.is_revoked(timestamp=timestamp + second))
        self.assertTrue(task_p.is_revoked(timestamp=timestamp - second))

        task_p.restore()
        self.assertFalse(task_p.is_revoked())
        self.assertFalse(task_p.is_revoked(timestamp=timestamp - second))

    def test_reschedule(self):
        state = []
        @self.huey.task()
        def task_a(n):
            state.append(n)
            return n + 1

        r = task_a(2)
        self.assertEqual(len(self.huey), 1)

        # Rescheduling the task will revoke the original invocation and enqueue
        # a new task instance.
        eta = datetime.datetime(2000, 1, 1)
        rs = r.reschedule(eta=eta)
        self.assertEqual(len(self.huey), 2)

        # The new task has a new ID.
        self.assertTrue(r.id != rs.id)

        # Attempting to execute the original instance... It is revoked.
        task = self.huey.dequeue()
        self.assertEqual(task.id, r.id)
        self.assertTrue(r.is_revoked())
        self.assertTrue(self.huey.execute(task) is None)
        self.assertEqual(state, [])

        # We can execute the rescheduled instance.
        task = self.huey.dequeue()
        self.assertEqual(task.id, rs.id)
        self.assertFalse(rs.is_revoked())
        self.assertEqual(self.huey.execute(task), 3)
        self.assertEqual(rs.get(), 3)
        self.assertEqual(state, [2])

        # Verify state of internals.
        self.assertEqual(len(self.huey), 0)
        self.assertEqual(self.huey.result_count(), 0)
        self.assertEqual(self.huey.scheduled_count(), 0)

    def test_reschedule_no_delay(self):
        state = []

        @self.huey.task(context=True)
        def task_s(task=None):
            state.append(task.id)
            return True

        res = task_s()
        res2 = res.reschedule()
        self.assertTrue(res.id != res2.id)

        self.assertEqual(len(self.huey), 2)
        self.assertTrue(self.execute_next() is None)
        self.assertTrue(self.execute_next())
        self.assertTrue(res2())

        self.assertEqual(state, [res2.id])
        self.assertEqual(len(self.huey), 0)
        self.assertEqual(self.huey.result_count(), 0)
        self.assertEqual(self.huey.scheduled_count(), 0)

    def test_expires(self):
        state = []
        now = datetime.datetime.now()
        seconds = lambda s: now + datetime.timedelta(seconds=s)

        # Tasks with both relative and absolute expire time.
        @self.huey.task(context=True, expires=10)
        def task_r(task=None):
            state.append(task.id)
            return True

        @self.huey.task(context=True, expires=seconds(10))
        def task_a(task=None):
            state.append(task.id)
            return True

        for exp_task in (task_r, task_a):
            # Task enqueued and executes normally since we're within the 10
            # second window.
            res = exp_task()
            self.assertEqual(len(self.huey), 1)
            self.assertTrue(self.execute_next(timestamp=seconds(1)))
            self.assertTrue(res())
            self.assertEqual(state, [res.id])

            # We'll create another task and attempt to run it, as if 10 seconds
            # had elapsed, and it will be expired.
            r2 = exp_task()
            task = self.huey.dequeue()

            # We'll ensure that the TTL was set for ~10 seconds from now.
            self.assertTrue(seconds(10) <= task.expires_resolved < seconds(12))

            # Attempt to execute with execution timestamp 12s from task
            # creation - the task will be expired.
            self.huey.execute(task, seconds(12))
            self.assertEqual(state, [res.id])

            # Attempt to execute with execution timestamp at 5s.
            self.huey.execute(task, seconds(5))
            self.assertEqual(state, [res.id, r2.id])

            # We can override the expire-time at invocation.
            r3 = exp_task(expires=60)
            task = self.huey.dequeue()
            self.assertTrue(seconds(60) <= task.expires_resolved < seconds(62))

            # Task is expired.
            self.huey.execute(task, seconds(63))
            self.assertEqual(state, [res.id, r2.id])

            # Run within the expiration time.
            self.huey.execute(task, seconds(50))
            self.assertEqual(state, [res.id, r2.id, r3.id])

            # We can also use datetime objects for default and per-task expire.
            r4 = exp_task(expires=seconds(30))
            task = self.huey.dequeue()
            self.assertEqual(task.expires_resolved, seconds(30))
            self.huey.execute(task, seconds(31))
            self.assertEqual(state, [res.id, r2.id, r3.id])
            self.huey.execute(task, seconds(30))
            self.assertEqual(state, [res.id, r2.id, r3.id, r4.id])

            state = []

    def test_scheduling_expires(self):
        @self.huey.task()
        def task_a(n):
            return n + 1

        now = datetime.datetime.now()
        seconds = lambda s: now + datetime.timedelta(seconds=s)

        result = task_a.schedule((3,), eta=seconds(60), expires=5)
        self.assertEqual(len(self.huey), 1)
        self.assertEqual(self.huey.scheduled_count(), 0)

        # Will be added to schedule, since task is not ready to run.
        self.assertTrue(self.execute_next() is None)
        self.assertEqual(len(self.huey), 0)
        self.assertEqual(self.huey.scheduled_count(), 1)

        # Simulate consumer running the scheduler after 60s elapsed.
        task, = self.huey.read_schedule(timestamp=seconds(60))
        self.assertEqual(task.expires, 5)  # Expire time is present.
        self.huey.enqueue(task)

        task = self.huey.dequeue()  # Read our task back.
        task.eta = now  # Simulate the task being ready to run.
        self.assertEqual(self.huey.execute(task, seconds(1)), 4)

    def test_reschedule_expires(self):
        state = []
        now = datetime.datetime.now()
        seconds = lambda s: now + datetime.timedelta(seconds=s)

        @self.huey.task(context=True)
        def task_s(task=None):
            state.append(task.id)
            return True

        res = task_s()
        res2 = res.reschedule(expires=seconds(10))
        self.assertEqual(len(self.huey), 2)
        self.assertTrue(self.execute_next() is None)  # 1st was revoked.

        task = self.huey.dequeue()
        self.assertEqual(task.expires_resolved, seconds(10))
        self.assertTrue(self.huey.execute(task, seconds(11)) is None)
        self.assertEqual(state, [])

        res3 = res2.reschedule(expires=5)
        task = self.huey.dequeue()
        self.assertTrue(seconds(5) < task.expires_resolved < seconds(7))
        self.assertEqual(self.huey.execute(task), True)
        self.assertEqual(state, [res3.id])

    def test_reschedule_priority(self):
        state = []

        @self.huey.task(context=True)
        def task_s(task=None):
            state.append(task.id)
            return True

        res = task_s(priority=10)
        res2 = res.reschedule(priority=99)
        self.assertEqual(len(self.huey), 2)

        task = self.huey.dequeue()
        self.assertEqual(task.priority, 99)
        self.assertTrue(self.huey.execute(task))

        task = self.huey.dequeue()
        self.assertEqual(task.priority, 10)
        self.assertTrue(res.is_revoked())
        self.assertTrue(self.huey.execute(task) is None)

        self.assertEqual(state, [res2.id])

    def test_task_error(self):
        @self.huey.task()
        def task_e(n):
            if n == 0:
                raise TestError('uh-oh')
            return n + 1

        re = task_e(0)
        self.assertTrue(self.execute_next() is None)
        self.assertEqual(self.huey.result_count(), 1)

        err = self.trap_exception(re)
        self.assertEqual(err.metadata['error'], 'TestError(uh-oh)')
        self.assertEqual(err.metadata['retries'], 0)

        self.assertEqual(self.huey.result_count(), 0)
        self.assertEqual(len(self.huey), 0)

    def test_subtask_error(self):
        @self.huey.task()
        def task_i(a):
            raise TestError(a)

        @self.huey.task()
        def task_o(a):
            res = task_i(a)
            self.execute_next()
            return res.get(blocking=True)

        r = task_o(1)
        self.assertTrue(self.execute_next() is None)
        exc = self.trap_exception(r)
        self.assertEqual(exc.metadata['error'], 'TestError(1)')

    def test_retry(self):
        @self.huey.task(retries=1)
        def task_a(n):
            if n < 0:
                raise ExcCounter()
            return n + 1

        # Execute the task normally.
        r = task_a(1)
        self.assertEqual(self.execute_next(), 2)
        self.assertEqual(r.get(), 2)
        self.assertEqual(len(self.huey), 0)

        # Trigger an exception being raised. Since the task has retries, it
        # will be re-enqueued and the number of retries is decremented.
        r = task_a(-1)
        self.assertTrue(self.execute_next() is None)

        # Attempting to resolve the result value will raise a TaskException,
        # which wraps the original error from the task.
        task_error = self.trap_exception(r)
        self.assertEqual(task_error.metadata['error'], 'ExcCounter(1)')
        self.assertEqual(task_error.metadata['retries'], 1)
        self.assertEqual(len(self.huey), 1)
        self.assertEqual(self.huey.result_count(), 0)

        # Dequeue next attempt. Note that the task uses the same ID as the
        # previous invocation, allowing us to reuse the result object.
        task = self.huey.dequeue()
        self.assertEqual(r.id, task.id)
        self.assertTrue(self.huey.execute(task) is None)
        self.assertEqual(self.huey.result_count(), 1)

        # Since the result will cache the task result locally, we need to reset
        # it to re-read. Attempting to read again will just return the cached
        # value.
        task_error = self.trap_exception(r)
        self.assertEqual(task_error.metadata['error'], 'ExcCounter(1)')
        self.assertEqual(self.huey.result_count(), 1)  # No change.

        # Reset the state of the result object in order to be able to read.
        r.reset()

        # As expected, the error occurs again.
        task_error = self.trap_exception(r)
        self.assertEqual(task_error.metadata['error'], 'ExcCounter(2)')
        self.assertEqual(task_error.metadata['retries'], 0)
        self.assertEqual(len(self.huey), 0)  # Not enqueued again.
        self.assertEqual(self.huey.result_count(), 0)

    def test_retries_with_override(self):
        @self.huey.task(retries=1)
        def task_a():
            raise ExcCounter()

        # Override the number of retries so it is not retried.
        r = task_a(retries=0)
        self.assertTrue(self.execute_next() is None)

        # Attempting to resolve the result value will raise a TaskException,
        # which wraps the original error from the task. The task will not be
        # retried, so it is not enqueued again.
        task_error = self.trap_exception(r)
        self.assertEqual(task_error.metadata['error'], 'ExcCounter(1)')
        self.assertEqual(task_error.metadata['retries'], 0)
        self.assertEqual(len(self.huey), 0)
        self.assertEqual(self.huey.result_count(), 0)

        # Override the number of retries.
        r = task_a(retries=2)
        self.assertTrue(self.execute_next() is None)

        # Attempting to resolve the result value will raise a TaskException,
        # which wraps the original error from the task.
        task_error = self.trap_exception(r)
        self.assertEqual(task_error.metadata['error'], 'ExcCounter(2)')
        self.assertEqual(task_error.metadata['retries'], 2)
        self.assertEqual(len(self.huey), 1)
        self.assertEqual(self.huey.result_count(), 0)
        self.huey.dequeue()  # Throw away task.

        # Ensure this works with scheduling as well.
        r = task_a.schedule(delay=-1, retries=3)
        self.assertTrue(self.execute_next() is None)
        task_error = self.trap_exception(r)
        self.assertEqual(task_error.metadata['error'], 'ExcCounter(3)')
        self.assertEqual(task_error.metadata['retries'], 3)
        self.assertEqual(len(self.huey), 1)
        self.assertEqual(self.huey.result_count(), 0)

    def test_retry_periodic(self):
        state = [0]

        @self.huey.periodic_task(crontab(hour='0'), retries=2)
        def task_p():
            if state[0] == 0:
                state[0] = 1
                raise TestError('oops')
            elif state[0] == 1:
                state[0] = 2
            else:
                state[0] = 9  # Should not happen.

        task_p()
        self.assertTrue(self.execute_next() is None)

        # The task is re-enqueued to be retried. Verify retry count is right
        # and execute.
        self.assertEqual(len(self.huey), 1)
        task = self.huey.dequeue()
        self.assertEqual(task.retries, 1)
        self.huey.execute(task)

        self.assertEqual(state, [2])
        self.assertEqual(len(self.huey), 0)

    def test_retry_to_success(self):
        state = [0]
        @self.huey.task(retries=2)
        def task_a():
            state[0] = state[0] + 1
            if state[0] != 3:
                raise ValueError('try again')
            return 1337

        r = task_a()
        self.assertTrue(self.execute_next() is None)
        self.assertTrue(self.execute_next() is None)
        self.assertEqual(self.execute_next(), 1337)
        self.assertEqual(r.get(), 1337)

        self.assertEqual(len(self.huey), 0)
        self.assertEqual(self.huey.result_count(), 0)

    def test_retry_delay(self):
        @self.huey.task(retries=2, retry_delay=60)
        def task_a():
            raise ValueError('try again')

        r = task_a()
        self.assertTrue(self.execute_next() is None)
        self.trap_exception(r)

        self.assertEqual(len(self.huey), 0)
        self.assertEqual(self.huey.scheduled_count(), 1)
        task, = self.huey.scheduled()  # Dequeue the delayed retry.
        self.assertTrue(task.eta is not None)
        self.assertEqual(task.retries, 1)
        self.assertFalse(self.huey.ready_to_run(task))

        dt = datetime.datetime.now() + datetime.timedelta(seconds=61)
        self.assertTrue(self.huey.ready_to_run(task, dt))

    def test_retry_delay_periodic(self):
        @self.huey.periodic_task(crontab(), retries=2, retry_delay=60)
        def task_p():
            raise ValueError('try again')

        r = task_p()
        self.assertTrue(self.execute_next() is None)

        self.assertEqual(len(self.huey), 0)
        self.assertEqual(self.huey.scheduled_count(), 1)
        task, = self.huey.scheduled()  # Dequeue the delayed retry.
        self.assertEqual(task.id, r.id)
        self.assertTrue(task.eta is not None)
        self.assertEqual(task.retries, 1)
        self.assertFalse(self.huey.ready_to_run(task))

        dt = datetime.datetime.now() + datetime.timedelta(seconds=61)
        self.assertTrue(self.huey.ready_to_run(task, dt))

    def test_retrytask_eta_delay(self):
        @self.huey.task(retry_delay=10)
        def task_a(d=None, e=None):
            raise RetryTask(delay=d, eta=e)

        seconds = lambda s: (datetime.datetime.now() +
                             datetime.timedelta(seconds=s))

        def run_iteration(d, e):
            r = task_a(d=d, e=e)
            self.assertTrue(self.execute_next() is None)
            self.assertRaises(TaskException, r.get)
            self.assertEqual(len(self.huey), 0)
            self.assertEqual(len(self.huey.scheduled()), 1)

            task, = self.huey.scheduled()
            self.assertEqual(task.id, r.id)
            self.assertFalse(self.huey.ready_to_run(task))
            if e is not None:
                self.assertEqual(task.eta, e)
            else:
                d = d or 10  # Default.
                self.assertTrue(seconds(d - 3) < task.eta < seconds(d + 3))

            self.huey.flush()

        run_iteration(None, None)
        run_iteration(3, None)
        run_iteration(300, None)
        run_iteration(None, seconds(3))
        run_iteration(None, seconds(300))

    def test_retrytask_explicit(self):
        state = [0]

        @self.huey.task()
        def task_a(n):
            state[0] = state[0] + n
            if state[0] < 2:
                raise RetryTask('asdf')
            return state[0]

        r = task_a(1)
        self.assertTrue(self.execute_next() is None)
        self.assertRaises(TaskException, r.get)
        self.assertEqual(state, [1])
        self.assertEqual(len(self.huey), 1)

        self.assertEqual(self.execute_next(), 2)
        r.reset()
        self.assertEqual(r.get(), 2)
        self.assertEqual(state, [2])
        self.assertEqual(len(self.huey), 0)
        self.assertEqual(self.huey.result_count(), 0)

        # Now run through and verify that if the task has a retry count, that
        # it is decremented as we'd expect normally.
        state = [0]
        t = task_a.s(1)
        t.retries = 2
        r = self.huey.enqueue(t)
        self.assertTrue(self.execute_next() is None)
        self.assertRaises(TaskException, r.get)
        self.assertEqual(state, [1])
        self.assertEqual(len(self.huey), 1)

        task = self.huey.dequeue()
        self.assertEqual(task.retries, 2)  # Unaffected!
        self.assertEqual(self.huey.execute(task), 2)
        r.reset()
        self.assertEqual(r.get(), 2)
        self.assertEqual(state, [2])
        self.assertEqual(len(self.huey), 0)
        self.assertEqual(self.huey.result_count(), 0)

    def test_cancel_execution(self):
        @self.huey.task()
        def task_a(n=None):
            raise CancelExecution(retry=n)

        r = task_a()
        self.assertTrue(self.execute_next() is None)
        self.assertRaises(TaskException, r.get)
        self.assertEqual(len(self.huey), 0)

        r = task_a(False)
        self.assertTrue(self.execute_next() is None)
        self.assertRaises(TaskException, r.get)
        self.assertEqual(len(self.huey), 0)

        r = task_a(True)
        self.assertTrue(self.execute_next() is None)
        self.assertRaises(TaskException, r.get)
        try:
            r.get()
        except TaskException as exc:
            metadata = exc.metadata
        self.assertEqual(metadata['error'], 'CancelExecution()')
        self.assertEqual(metadata['retries'], 1)
        self.assertEqual(len(self.huey), 1)

    def test_cancel_execution_task_retries(self):
        @self.huey.task(retries=2)
        def task_a(n=None):
            raise CancelExecution(retry=n)

        # Even though the task itself declares retries, these retries are
        # ignored when cancel is raised with retry=False.
        r = task_a(False)
        self.assertTrue(self.execute_next() is None)
        self.assertRaises(TaskException, r.get)
        self.assertEqual(len(self.huey), 0)

        # The original task specified 2 retries. When Cancel is raised with
        # retry=None, it proceeds normally.
        r = task_a()
        for retries in (2, 1, 0):
            self.assertTrue(self.execute_next() is None)
            self.assertRaises(TaskException, r.get)
            try:
                r.get()
            except TaskException as exc:
                metadata = exc.metadata
            self.assertEqual(metadata['error'], 'CancelExecution()')
            self.assertEqual(metadata['retries'], retries)
            if retries > 0:
                self.assertEqual(len(self.huey), 1)
            else:
                self.assertEqual(len(self.huey), 0)
            r.reset()

        # The original task specified 2 retries. When Cancel is raised with
        # retry=True, then max(task.retries, 1) will be used.
        r = task_a(True)
        for retries in (2, 1, 1, 1):
            self.assertTrue(self.execute_next() is None)
            self.assertRaises(TaskException, r.get)
            try:
                r.get()
            except TaskException as exc:
                metadata = exc.metadata
            self.assertEqual(metadata['error'], 'CancelExecution()')
            self.assertEqual(metadata['retries'], retries)
            self.assertEqual(len(self.huey), 1)
            r.reset()

    def test_read_schedule(self):
        @self.huey.task()
        def task_a(n):
            return n

        server_time = datetime.datetime(2000, 1, 1)
        timestamp = datetime.datetime(2000, 1, 2, 3, 4, 5)
        second = datetime.timedelta(seconds=1)

        rn1 = task_a.schedule(-1, eta=(timestamp - second))
        r0 = task_a.schedule(0, eta=timestamp)
        rp1 = task_a.schedule(1, eta=(timestamp + second))
        self.assertEqual(self.huey.scheduled_count(), 0)
        self.assertEqual(len(self.huey), 3)

        # Get these tasks added to the schedule.
        for _ in range(3):
            self.huey.execute(self.huey.dequeue(), timestamp=server_time)

        self.assertEqual(self.huey.scheduled_count(), 3)
        self.assertEqual(len(self.huey), 0)

        # Two tasks are ready to run. Reading from the schedule is a
        # destructive operation.
        tn1, t0 = self.huey.read_schedule(timestamp)
        self.assertEqual(tn1.id, rn1.id)
        self.assertEqual(t0.id, r0.id)
        self.assertEqual(self.huey.read_schedule(timestamp), [])

        tp1, = self.huey.read_schedule(datetime.datetime(2010, 1, 1))
        self.assertEqual(tp1.id, rp1.id)

        # Everything is cleared out.
        self.assertEqual(len(self.huey), 0)
        self.assertEqual(self.huey.result_count(), 0)
        self.assertEqual(self.huey.scheduled_count(), 0)

    def test_read_periodic(self):
        @self.huey.periodic_task(crontab(minute='*/15', hour='9-17'))
        def work():
            pass

        @self.huey.periodic_task(crontab(minute='0', hour='21'))
        def sleep():
            pass

        @self.huey.periodic_task(crontab(minute='0-30'))
        def first_half():
            pass

        def assertPeriodic(hour, minute, names):
            dt = datetime.datetime(2000, 1, 1, hour, minute)
            tasks = self.huey.read_periodic(dt)
            self.assertEqual([t.name for t in tasks], names)

        assertPeriodic(0, 0, ['first_half'])
        assertPeriodic(23, 59, [])
        assertPeriodic(9, 0, ['work', 'first_half'])
        assertPeriodic(9, 45, ['work'])
        assertPeriodic(9, 46, [])
        assertPeriodic(21, 0, ['sleep', 'first_half'])
        assertPeriodic(21, 30, ['first_half'])
        assertPeriodic(21, 31, [])


class TestDecorators(BaseTestCase):
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
        self.assertEqual(task.retries, 0)
        self.assertEqual(task.retry_delay, 0)
        self.assertEqual(task.execute(), 123)

        @self.huey.periodic_task(crontab(), retries=3, retry_delay=10)
        def task_p2():
            pass

        task = task_p2.s()
        self.assertEqual(task.retries, 3)
        self.assertEqual(task.retry_delay, 10)

    def test_call_periodic_task(self):
        @self.huey.periodic_task(crontab(minute='1'))
        def task_p():
            return 123

        res = task_p()
        self.assertEqual(len(self.huey), 1)
        self.assertEqual(self.execute_next(), 123)

        # Result-store is not used for periodic task results.
        self.assertTrue(res() is None)

    def test_context_task(self):
        class DB(object):
            def __init__(self):
                self.state = []
            def __enter__(self):
                self.state.append('open')
            def __exit__(self, exc_type, exc_val, exc_tb):
                self.state.append('close')
            def get_state(self):
                self.state, ret = [], self.state
                return ret
        db = DB()
        self.assertEqual(db.get_state(), [])

        @self.huey.context_task(db)
        def task_c(n):
            if n < 0:
                raise ValueError('bad value')
            return n + 1

        res = task_c(2)
        self.assertEqual(self.execute_next(), 3)
        self.assertEqual(db.get_state(), ['open', 'close'])

        res = task_c(-1)
        self.assertEqual(db.get_state(), [])
        self.assertTrue(self.execute_next() is None)
        self.assertEqual(db.get_state(), ['open', 'close'])

    def test_dynamic_periodic_tasks(self):
        def ptask(): pass

        @self.huey.task()
        def make_ptask(every_n):
            name = 'ptask_%s' % every_n
            sched = crontab('*/%s' % every_n)
            self.huey.periodic_task(sched, name=name)(ptask)

        # Create two tasks dynamically.
        make_ptask(5)
        make_ptask(10)

        def assertPeriodic(dt, names):
            ptasks = self.huey.read_periodic(dt)
            self.assertEqual(len(ptasks), len(names))
            self.assertEqual(sorted([t.name for t in ptasks]), names)

        dt = datetime.datetime(2019, 1, 1, 0, 0, 0)
        assertPeriodic(dt, [])

        self.execute_next()
        self.execute_next()

        assertPeriodic(dt, ['ptask_10', 'ptask_5'])
        assertPeriodic(datetime.datetime(2019, 1, 1, 0, 5), ['ptask_5'])
        assertPeriodic(datetime.datetime(2019, 1, 1, 0, 6), [])


class TestTaskHooks(BaseTestCase):
    def test_task_hooks(self):
        @self.huey.task()
        def task_a(n):
            return n + 1

        allow_tasks = [True]
        pre_state = []
        post_state = []

        @self.huey.pre_execute()
        def pre_execute_cancel(task):
            if not allow_tasks[0]:
                raise CancelExecution()

        @self.huey.pre_execute()
        def pre_execute(task):
            pre_state.append(task.id)

        @self.huey.post_execute()
        def post_execute(task, task_value, exc):
            if exc is not None:
                exc = type(exc).__name__
            post_state.append((task.id, task_value, exc))

        result = task_a(3)
        self.assertEqual(self.execute_next(), 4)
        self.assertEqual(pre_state, [result.id])
        self.assertEqual(post_state, [(result.id, 4, None)])

        # Cancel execution.
        task_a(5)
        allow_tasks[0] = False  # Disable execution.
        self.assertTrue(self.execute_next() is None)
        self.assertEqual(len(pre_state), 1)
        self.assertEqual(len(post_state), 1)

        # Errors are passed to post-execute hook.
        allow_tasks[0] = True  # Re-enable.
        err_result = task_a(None)  # Can't add 1 to None!
        self.assertTrue(self.execute_next() is None)
        self.assertEqual(pre_state, [result.id, err_result.id])
        self.assertEqual(post_state, [(result.id, 4, None),
                                      (err_result.id, None, 'TypeError')])

    def test_hook_unregister(self):
        @self.huey.task()
        def task_a(n):
            return n + 1

        pre_state = []
        post_state = []

        @self.huey.pre_execute()
        def test_pre_exec(task):
            pre_state.append(task.id)
        @self.huey.post_execute()
        def test_post_exec(task, val, exc):
            post_state.append(task.id)

        # Verify hooks in place. Sanity check.
        r = task_a(3)
        self.assertEqual(self.execute_next(), 4)
        self.assertEqual(pre_state, [r.id])
        self.assertEqual(post_state, [r.id])

        self.assertTrue(self.huey.unregister_pre_execute('test_pre_exec'))
        self.assertTrue(self.huey.unregister_post_execute('test_post_exec'))

        r2 = task_a(4)
        self.assertEqual(self.execute_next(), 5)
        self.assertEqual(len(pre_state), 1)
        self.assertEqual(len(post_state), 1)

        # Already unregistered, returns False.
        self.assertFalse(self.huey.unregister_pre_execute('test_pre_exec'))
        self.assertFalse(self.huey.unregister_post_execute('test_post_exec'))

    def test_task_hook_errors(self):
        @self.huey.task()
        def task_a(n):
            return n + 1

        pre_state = []
        post_state = []

        @self.huey.pre_execute()
        def test_pre_exec1(task):
            raise ValueError('flaky pre hook')
        @self.huey.pre_execute()
        def test_pre_exec2(task):
            pre_state.append(task.id)

        @self.huey.post_execute()
        def test_post_exec1(task, val, exc):
            raise ValueError('flaky post hook')
        @self.huey.post_execute()
        def test_post_exec2(task, val, exc):
            post_state.append(task.id)

        # One flaky callback will not prevent other callbacks, nor will it
        # prevent the task from being executed.
        r = task_a(3)
        self.assertEqual(self.execute_next(), 4)
        self.assertEqual(pre_state, [r.id])
        self.assertEqual(post_state, [r.id])


class TestTaskChaining(BaseTestCase):
    def test_pipeline_tuple(self):
        @self.huey.task()
        def fib(a, b=1):
            a, b = a + b, a
            return a, b

        pipe = fib.s(1).then(fib).then(fib).then(fib)
        self.assertPipe(pipe, [(2, 1), (3, 2), (5, 3), (8, 5)])

    def test_pipeline_dict(self):
        @self.huey.task()
        def stateful(v1=None, v2=None, v3=None):
            state = {
                'v1': v1 + 1 if v1 is not None else 0,
                'v2': v2 + 2 if v2 is not None else 0,
                'v3': v3 + 3 if v3 is not None else 0}
            return state

        pipe = stateful.s().then(stateful).then(stateful)
        self.assertPipe(pipe, [
            {'v1': 0, 'v2': 0, 'v3': 0},
            {'v1': 1, 'v2': 2, 'v3': 3},
            {'v1': 2, 'v2': 4, 'v3': 6}])

        pipe = stateful.s(v1=4).then(stateful, v2=6).then(stateful, v2=1, v3=8)
        self.assertPipe(pipe, [
            {'v1': 5, 'v2': 0, 'v3': 0},
            {'v1': 6, 'v2': 8, 'v3': 3},
            {'v1': 7, 'v2': 3, 'v3': 11}])

    def test_partial(self):
        @self.huey.task()
        def add(a, b):
            return a + b

        @self.huey.task()
        def mul(a, b):
            return a * b

        pipe = add.s(1, 2).then(add, 3).then(add, 4).then(add, 5)
        self.assertPipe(pipe, [3, 6, 10, 15])

        pipe = add.s(1, 2).then(mul, 4).then(add, -5).then(mul, 3).then(add, 8)
        self.assertPipe(pipe, [3, 12, 7, 21, 29])

    def test_mixed_tasks_instances(self):
        @self.huey.task()
        def add(a, b):
            return a + b
        @self.huey.task()
        def mul(a, b):
            return a * b

        t1 = add.s(1, 2)
        t2 = add.s(3)
        t3 = mul.s(4)
        t4 = mul.s()
        p1 = t1.then(t2)
        p2 = p1.then(t3).then(t4, 5)
        self.assertPipe(p2, [3, 6, 24, 120])

    def test_task_instances_args_kwargs(self):
        @self.huey.task()
        def add(a, b, c=None):
            s = a + b
            if c is not None:
                s += c
            return s

        t1 = add.s(1, 2)
        t2 = add.s()
        t3 = add.s()
        p1 = t1.then(t2, 3).then(t3, 4, c=5)
        self.assertPipe(p1, [3, 6, 15])

    def assertPipe(self, pipeline, expected):
        results = self.huey.enqueue(pipeline)
        for _ in range(len(results)):
            self.assertEqual(len(self.huey), 1)
            self.execute_next()

        self.assertEqual(len(self.huey), 0)
        self.assertEqual(len(results), len(expected))
        self.assertEqual([r() for r in results], expected)

    def test_error_callback(self):
        state = []
        @self.huey.task()
        def task_a(n):
            raise TestError(n)

        @self.huey.task()
        def task_e(err):
            state.append(repr(err))
            return 1337

        task = task_a.s(0).error(task_e)
        result = self.huey.enqueue(task)
        self.assertTrue(self.execute_next() is None)
        self.assertRaises(TaskException, result.get)
        self.assertEqual(len(self.huey), 1)
        self.assertEqual(self.execute_next(), 1337)
        self.assertEqual(state, ['TestError(0)'])

    def test_pipeline_error_midway(self):
        @self.huey.task()
        def task_a(n):
            if n < 0:
                raise TestError('below zero')
            return n - 1

        # 1, 0, -1, ??.
        pipe = task_a.s(1).then(task_a).then(task_a).then(task_a)
        r1, r2, r3, r4 = self.huey.enqueue(pipe)
        self.assertEqual(self.execute_next(), 0)
        self.assertEqual(self.execute_next(), -1)
        self.assertTrue(self.execute_next() is None)
        self.assertRaises(TaskException, r3.get)

        # Was r4 enqueued? -- No.
        self.assertEqual(len(self.huey), 0)

    def test_pipeline_revoke_midway(self):
        @self.huey.task()
        def task_a(n):
            return n + 1

        pipe = task_a.s(1).then(task_a).then(task_a).then(task_a)
        r1, r2, r3, r4 = self.huey.enqueue(pipe)
        r3.revoke()
        self.assertEqual(self.execute_next(), 2)
        self.assertEqual(self.execute_next(), 3)
        self.assertTrue(r3.is_revoked())
        self.assertTrue(self.execute_next() is None)
        self.assertEqual(len(self.huey), 0)
        self.assertFalse(r3.is_revoked())  # Cleared when it was handled.

    def test_chain_errors(self):
        state1, state2 = [], []

        @self.huey.task()
        def task_a(n):
            if n < 1:
                raise TestError(n)
            return n - 1

        @self.huey.task()
        def task_e1(n, err):
            state1.append(repr(err))
            if n < 1:
                raise TestError(n)

        @self.huey.task()
        def task_e2(n, err):
            state2.append((n, repr(err)))
            return n

        pipe = task_a.s(1).then(task_a)
        pipe.on_complete.error(task_e1, 0).error(task_e2, 3)

        # We get result wrappers for the invocations of task_a.
        r1, r2 = self.huey.enqueue(pipe)
        self.execute_next()  # First invocation, returns 0.
        self.execute_next()  # Second, raises error.

        self.assertEqual(len(self.huey), 1)
        self.execute_next()  # Error handler (also fails).
        self.assertEqual(len(self.huey), 1)

        self.assertEqual(self.execute_next(), 3)  # Second error handler.

        self.assertEqual(state1, ['TestError(0)'])
        self.assertEqual(state2, [(3, 'TestError(0)')])

        self.assertEqual(r1(), 0)
        self.assertRaises(TaskException, r2.get)
        self.assertEqual(len(self.huey), 0)


class TestTaskLocking(BaseTestCase):
    def test_task_locking(self):
        @self.huey.task(retries=1)
        @self.huey.lock_task('lock_a')
        def task_a(n):
            return n + 1

        task_a(3)
        self.assertEqual(self.execute_next(), 4)

        task_a(4)
        with self.huey.lock_task('lock_x'):
            self.assertFalse(self.huey.is_locked('lock_a'))
            self.assertTrue(self.huey.is_locked('lock_x'))
            self.assertEqual(self.execute_next(), 5)

        # Ensure locks were cleared.
        self.assertFalse(self.huey.is_locked('lock_a'))
        self.assertFalse(self.huey.is_locked('lock_x'))

        r = task_a(5)
        with self.huey.lock_task('lock_a'):
            self.assertTrue(self.huey.is_locked('lock_a'))
            self.assertTrue(self.execute_next() is None)

        exc = self.trap_exception(r)
        self.assertTrue('unable to acquire' in str(exc))

        # Task failed due to lock, will be retried, which succeeds now that the
        # lock is released.
        self.assertEqual(self.execute_next(), 6)


class TestHueyAPIs(BaseTestCase):
    def test_flush_locks(self):
        with self.huey.lock_task('lock1'):
            with self.huey.lock_task('lock2'):
                flushed = self.huey.flush_locks()

        self.assertEqual(flushed, set(['lock1', 'lock2']))
        self.assertEqual(self.huey.flush_locks(), set())

    def test_flush_named_locks(self):
        self.huey.put_if_empty('%s.lock.lock1' % self.huey.name, '1')
        self.huey.put_if_empty('%s.lock.lock2' % self.huey.name, '1')
        with self.huey.lock_task('lock3'):
            flushed = self.huey.flush_locks('lock1', 'lock2', 'lockx')

        self.assertEqual(flushed, set(['lock1', 'lock2', 'lock3']))
        self.assertEqual(self.huey.flush_locks(), set())

    def test_serialize_deserialize(self):
        @self.huey.task()
        def task_a(n):
            return n
        @self.huey.task()
        def task_b(n):
            return n
        @self.huey.periodic_task(crontab(minute='1'))
        def task_p():
            return

        ta = task_a.s(1)
        tb = task_b.s(2)
        tp = task_p.s()
        S = lambda t: self.huey.deserialize_task(self.huey.serialize_task(t))
        self.assertEqual(ta, S(ta))
        self.assertEqual(tb, S(tb))
        self.assertEqual(tp, S(tp))

    def test_serialize_deserialize_signed(self):
        self.huey.serializer = SignedSerializer(secret='test secret')
        self.test_serialize_deserialize()

    def test_put_get(self):
        tests = ('v1', 1, 1., 0, None,
                 [0, 1, 2],
                 (2, 3, 4),
                 {'k1': 'v1', 'k2': 'v2'},
                 set('abc'))
        for test in tests:
            self.huey.put('key', test)
            self.assertEqual(self.huey.get('key'), test)

    def test_unsupported(self):
        FooHuey = _unsupported('FooHuey', 'foo')
        self.assertRaises(ConfigurationError, FooHuey)


class TestMultipleHuey(BaseTestCase):
    def test_multiple_huey(self):
        huey1 = self.huey
        huey2 = MemoryHuey('huey2', utc=False)

        @huey1.task()
        def task_a(n):
            return n + 1

        task_a2 = huey2.task(retries=1)(task_a)

        r = task_a(1)
        self.assertEqual(len(huey1), 1)
        self.assertEqual(len(huey2), 0)
        self.assertEqual(self.execute_next(), 2)
        self.assertEqual(r.get(), 2)

        r2 = task_a2(2)
        self.assertEqual(len(huey1), 0)
        self.assertEqual(len(huey2), 1)
        self.assertEqual(huey2.execute(huey2.dequeue()), 3)
        self.assertEqual(r2.get(), 3)


class TestDisableResultStore(BaseTestCase):
    def get_huey(self):
        return MemoryHuey(results=False, utc=False)

    def test_disable_result_store(self):
        state = []

        @self.huey.task()
        def task_a(n):
            state.append(n)
            return n + 1

        res = task_a(2)
        self.assertTrue(res is None)
        self.assertEqual(self.execute_next(), 3)
        self.assertEqual(len(self.huey), 0)
        self.assertEqual(self.huey.result_count(), 0)
        self.assertEqual(state, [2])

        p = task_a.s(3).then(task_a)
        res = self.huey.enqueue(p)
        self.assertTrue(res is None)
        self.assertEqual(self.execute_next(), 4)
        self.assertEqual(self.execute_next(), 5)
        self.assertEqual(state, [2, 3, 4])

        self.huey.immediate = True
        self.assertTrue(task_a(5) is None)
        self.assertEqual(state, [2, 3, 4, 5])

        p = task_a.s(6).then(task_a)
        res = self.huey.enqueue(p)
        self.assertTrue(res is None)
        self.assertEqual(state, [2, 3, 4, 5, 6, 7])

        self.assertEqual(len(self.huey), 0)
        self.assertEqual(self.huey.result_count(), 0)


class TestStorageWrappers(BaseTestCase):
    def test_storage_wrappers(self):
        @self.huey.task()
        def task_a(n):
            return n + 1

        def assertTasks(tasks, id_list):
            self.assertEqual([t.id for t in tasks], id_list)

        assertTasks(self.huey.pending(), [])
        assertTasks(self.huey.scheduled(), [])
        self.assertEqual(self.huey.all_results(), {})

        r1 = task_a(1)
        r2 = task_a.schedule((2,), delay=60)
        r3 = task_a(3)

        assertTasks(self.huey.pending(), [r1.id, r2.id, r3.id])
        assertTasks(self.huey.scheduled(), [])
        self.assertEqual(self.huey.all_results(), {})

        self.execute_next()
        self.execute_next()

        assertTasks(self.huey.pending(), [r3.id])
        assertTasks(self.huey.scheduled(), [r2.id])
        self.assertEqual(list(self.huey.all_results()), [r1.id])


class TestDocstring(BaseTestCase):
    def test_docstring_preserved(self):
        @self.huey.task()
        def add(a, b):
            'Adds two numbers.'
            return a + b

        @self.huey.periodic_task(crontab(minute='*'))
        def ptask():
            'Sample periodic task.'

        self.assertEqual(inspect.getdoc(add), 'Adds two numbers.')
        self.assertEqual(inspect.getdoc(ptask), 'Sample periodic task.')


class TestCustomErrorMetadata(BaseTestCase):
    def get_huey(self):
        class CustomError(MemoryHuey):
            def build_error_result(self, task, exc):
                err = super(CustomError, self).build_error_result(task, exc)
                err.update(name=task.name, args=task.args)
                return err
        return CustomError(utc=False)

    def test_custom_error(self):
        @self.huey.task()
        def task_e(n):
            raise TestError('uh-oh')

        re = task_e(0)
        self.assertTrue(self.execute_next() is None)
        self.assertEqual(self.huey.result_count(), 1)  # Error result present.

        # Resolves the result handle, which re-raises the error.
        err = self.trap_exception(re)
        self.assertEqual(err.metadata['error'], 'TestError(uh-oh)')
        self.assertEqual(err.metadata['retries'], 0)
        self.assertEqual(err.metadata['name'], 'task_e')
        self.assertEqual(err.metadata['args'], (0,))

        self.assertEqual(self.huey.result_count(), 0)
        self.assertEqual(len(self.huey), 0)
