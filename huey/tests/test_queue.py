import datetime
import pickle

from huey import crontab
from huey import exceptions as huey_exceptions
from huey import RedisHuey
from huey.api import Huey
from huey.api import QueueTask
from huey.constants import EmptyData
from huey.registry import registry
from huey.storage import RedisStorage
from huey.tests.base import b
from huey.tests.base import BaseTestCase
from huey.utils import local_to_utc

huey = RedisHuey(result_store=False, events=False, blocking=False)
huey_results = RedisHuey(blocking=False, max_errors=10)
huey_store_none = RedisHuey(store_none=True, blocking=False)

# Global state.
state = {}

@huey.task()
def put_data(key, value):
    state[key] = value

@huey.task(include_task=True)
def put_data_ctx(key, value, task=None):
    state['last_task_class'] = type(task).__name__

@huey_results.task(include_task=True)
def error_testing_task_with_ctx(key, value, task=None):
    bad = 1/0
    state['last_task_class'] = type(task).__name__

class PutTask(QueueTask):
    def execute(self):
        k, v = self.data
        state[k] = v

class TestException(Exception):
    pass

@huey.task()
def _throw_error_task(message=None):
    raise TestException(message or 'bampf')

throw_error_task = huey.task()(_throw_error_task)
throw_error_task_res = huey_results.task()(_throw_error_task)

@huey_results.task()
def add_values(a, b):
    return a + b

@huey_results.periodic_task(crontab(minute='0'))
def hourly_task2():
    state['periodic'] = 2

@huey_results.task()
def returns_none():
    return None

@huey_store_none.task()
def returns_none2():
    return None


class BaseQueueTestCase(BaseTestCase):
    def setUp(self):
        global state
        state = {}
        huey.flush()
        huey_results.flush()
        huey_store_none.flush()
        self.assertEqual(len(huey), 0)

    def tearDown(self):
        huey.flush()
        huey_results.flush()
        huey_store_none.flush()


class TestHueyQueueMetadataAPIs(BaseQueueTestCase):
    def test_queue_metadata(self):
        put_data('k1', 'v1')
        put_data('k2', 'v2')
        cmd2, cmd1 = huey.pending()
        self.assertEqual(cmd2.data, (('k2', 'v2'), {}))
        self.assertEqual(cmd1.data, (('k1', 'v1'), {}))

        huey.dequeue()
        cmd1, = huey.pending()
        self.assertEqual(cmd1.data, (('k2', 'v2'), {}))

    def test_schedule_metadata(self):
        add_values.schedule((1, 2), delay=10)
        add_values.schedule((3, 4), delay=5)
        self.assertEqual(len(huey_results), 2)
        huey_results.add_schedule(huey.dequeue())
        huey_results.add_schedule(huey.dequeue())

        cmd2, cmd1 = huey_results.scheduled()
        self.assertEqual(cmd1.data, ((1, 2), {}))
        self.assertEqual(cmd2.data, ((3, 4), {}))

    def test_results_metadata(self):
        add_values(1, 2)
        add_values(3, 4)
        t1 = huey_results.dequeue()
        t2 = huey_results.dequeue()
        self.assertEqual(huey_results.all_results(), {})

        huey_results.execute(t1)
        self.assertEqual(list(huey_results.all_results()), [b(t1.task_id)])

        huey_results.execute(t2)
        self.assertEqual(sorted(huey_results.all_results().keys()),
                         sorted([b(t1.task_id), b(t2.task_id)]))


class TestHueyQueueAPIs(BaseQueueTestCase):
    def test_enqueue(self):
        # initializing the command does not enqueue it
        task = PutTask(('k', 'v'))
        self.assertEqual(len(huey), 0)

        # ok, enqueue it, then check that it was enqueued
        huey.enqueue(task)
        self.assertEqual(len(huey), 1)
        self.assertEqual(state, {})

        # it can be enqueued multiple times
        huey.enqueue(task)
        self.assertEqual(len(huey), 2)

        # no changes to state
        self.assertEqual(state, {})

    def test_enqueue_decorator(self):
        put_data('k', 'v')
        self.assertEqual(len(huey), 1)

        put_data('k', 'v')
        self.assertEqual(len(huey), 2)

        # no changes to state
        self.assertEqual(state, {})

    def test_scheduled_time(self):
        put_data('k', 'v')

        task = huey.dequeue()
        self.assertEqual(len(huey), 0)
        self.assertEqual(task.execute_time, None)

        dt = datetime.datetime(2011, 1, 1, 0, 1)
        put_data.schedule(args=('k2', 'v2'), eta=dt)

        self.assertEqual(len(huey), 1)
        task = huey.dequeue()
        self.assertEqual(task.execute_time, local_to_utc(dt))

        put_data.schedule(args=('k3', 'v3'), eta=dt, convert_utc=False)
        self.assertEqual(len(huey), 1)
        task = huey.dequeue()
        self.assertEqual(task.execute_time, dt)

    def test_error_raised(self):
        throw_error_task()
        task = huey.dequeue()
        self.assertRaises(TestException, huey.execute, task)

    def test_error_logging(self):
        def call_task():
            throw_error_task_res('nuggie')
            task = huey_results.dequeue()
            self.assertRaises(TestException, huey_results.execute, task)
            return task

        hr = huey_results
        self.assertEqual(len(hr.errors()), 0)

        task = call_task()
        errors = hr.errors()
        self.assertEqual(len(errors), 1)
        error = errors[0]

        self.assertTrue(isinstance(error['error'], TestException))
        self.assertEqual(error['id'], task.task_id)

        for i in range(9):
            call_task()
            self.assertEqual(len(hr.errors()), i + 2)

        self.assertEqual(len(hr.errors()), 10)  # Just to be clear.

        # When we run the task again, the queue will have been trimmed.
        task = call_task()
        self.assertEqual(len(hr.errors()), 10)

        # The first item in the queue is the most recently executed task.
        most_recent_error = hr.errors()[0]
        self.assertEqual(most_recent_error['id'], task.task_id)

    def test_internal_error(self):
        """
        Verify that exceptions are wrapped with the special "huey"
        exception classes.
        """
        class SpecialException(Exception):
            pass

        class BrokenStorage(RedisStorage):
            def enqueue(self):
                raise SpecialException('read error')

            def dequeue(self, data):
                raise SpecialException('write error')

            def pop_data(self, key):
                raise SpecialException('get error')

            def peek_data(self, key):
                raise SpecialException('get error')

            def put_data(self, key, value):
                raise SpecialException('put error')

            def add_to_schedule(self, data, ts):
                raise SpecialException('add error')

            def read_schedule(self, ts):
                raise SpecialException('read error')

        class BrokenHuey(RedisHuey):
            def get_storage(self, **kwargs):
                return BrokenStorage(self.name)

        task = PutTask(('foo', 'bar'))
        huey = BrokenHuey()

        self.assertRaises(
            huey_exceptions.QueueWriteException,
            huey.enqueue,
            task)
        self.assertRaises(
            huey_exceptions.QueueReadException,
            huey.dequeue)
        self.assertRaises(
            huey_exceptions.DataStorePutException,
            huey.revoke,
            task)
        self.assertRaises(
            huey_exceptions.DataStoreGetException,
            huey.restore,
            task)
        self.assertRaises(
            huey_exceptions.ScheduleAddException,
            huey.add_schedule,
            task)
        self.assertRaises(
            huey_exceptions.ScheduleReadException,
            huey.read_schedule,
            1)

    def test_dequeueing(self):
        res = huey.dequeue() # no error raised if queue is empty
        self.assertEqual(res, None)

        put_data('k', 'v')
        task = huey.dequeue()

        self.assertTrue(isinstance(task, QueueTask))
        self.assertEqual(task.get_data(), (('k', 'v'), {}))

    def test_execution(self):
        self.assertEqual(state, {})
        put_data('k', 'v')

        task = huey.dequeue()
        self.assertFalse('k' in state)

        huey.execute(task)
        self.assertEqual(state, {'k': 'v'})

        put_data('k', 'X')
        self.assertEqual(state, {'k': 'v'})

        huey.execute(huey.dequeue())
        self.assertEqual(state, {'k': 'X'})

        self.assertRaises(TypeError, huey.execute, huey.dequeue())

    def test_self_awareness(self):
        put_data_ctx('k', 'v')
        task = huey.dequeue()
        huey.execute(task)
        self.assertEqual(state['last_task_class'], 'queuecmd_put_data_ctx')
        del state['last_task_class']

        put_data('k', 'x')
        huey.execute(huey.dequeue())
        self.assertFalse('last_task_class' in state)

    def test_self_aware_error_handler(self):
        error_testing_task_with_ctx('k', 'v')
        task = huey_results.dequeue()
        self.assertRaises(ZeroDivisionError, huey_results.execute, task)

    def test_call_local(self):
        self.assertEqual(len(huey), 0)
        self.assertEqual(state, {})
        put_data.call_local('nugget', 'green')

        self.assertEqual(len(huey), 0)
        self.assertEqual(state, {'nugget': 'green'})

    def test_revoke(self):
        ac = PutTask(('k', 'v'))
        ac2 = PutTask(('k2', 'v2'))
        ac3 = PutTask(('k3', 'v3'))

        huey_results.enqueue(ac)
        huey_results.enqueue(ac2)
        huey_results.enqueue(ac3)
        huey_results.enqueue(ac2)
        huey_results.enqueue(ac)

        self.assertEqual(len(huey_results), 5)
        huey_results.revoke(ac2)

        while huey_results:
            task = huey_results.dequeue()
            if not huey_results.is_revoked(task):
                huey_results.execute(task)

        self.assertEqual(state, {'k': 'v', 'k3': 'v3'})

    def test_revoke_restore_by_id(self):
        t1 = PutTask(('k1', 'v1'))
        t2 = PutTask(('k2', 'v2'))
        t3 = PutTask(('k3', 'v3'))
        for task in (t1, t2, t3):
            huey_results.enqueue(task)

        huey_results.revoke_by_id(t3.task_id)
        huey_results.revoke_by_id(t2.task_id)
        huey_results.restore_by_id(t3.task_id)

        self.assertFalse(huey_results.is_revoked(huey_results.dequeue()))
        self.assertTrue(huey_results.is_revoked(huey_results.dequeue()))
        self.assertFalse(huey_results.is_revoked(huey_results.dequeue()))

    def test_revoke_periodic(self):
        hourly_task2.revoke()
        self.assertTrue(hourly_task2.is_revoked())

        # it is still revoked
        self.assertTrue(hourly_task2.is_revoked())

        self.assertTrue(hourly_task2.restore())
        self.assertFalse(hourly_task2.is_revoked())
        self.assertFalse(hourly_task2.restore())  # It is not revoked.

        hourly_task2.revoke(revoke_once=True)
        self.assertTrue(hourly_task2.is_revoked()) # it is revoked once, but we are preserving that state
        self.assertTrue(hourly_task2.is_revoked(peek=False)) # is revoked once, but clear state
        self.assertFalse(hourly_task2.is_revoked()) # no longer revoked

        d = datetime.datetime
        hourly_task2.revoke(revoke_until=d(2011, 1, 1, 11, 0))
        self.assertTrue(hourly_task2.is_revoked(dt=d(2011, 1, 1, 10, 0)))
        self.assertTrue(hourly_task2.is_revoked(dt=d(2011, 1, 1, 10, 59)))
        self.assertFalse(hourly_task2.is_revoked(dt=d(2011, 1, 1, 11, 0)))

        hourly_task2.restore()
        self.assertFalse(hourly_task2.is_revoked())

    def test_result_store(self):
        res = add_values(1, 2)
        res2 = add_values(4, 5)
        res3 = add_values(0, 0)

        # none have been executed as yet
        self.assertEqual(res.get(), None)
        self.assertEqual(res2.get(), None)
        self.assertEqual(res3.get(), None)

        # execute the first task
        huey_results.execute(huey_results.dequeue())
        self.assertEqual(res.get(), 3)
        self.assertEqual(res2.get(), None)
        self.assertEqual(res3.get(), None)

        # We can also call the result object.
        self.assertEqual(res(), 3)
        self.assertEqual(res2(), None)

        # execute the second task
        huey_results.execute(huey_results.dequeue())
        self.assertEqual(res.get(), 3)
        self.assertEqual(res2.get(), 9)
        self.assertEqual(res3.get(), None)

        # execute the 3rd, which returns a zero value
        huey_results.execute(huey_results.dequeue())
        self.assertEqual(res.get(), 3)
        self.assertEqual(res2.get(), 9)
        self.assertEqual(res3.get(), 0)

        # check that it returns None when nothing is present
        res = returns_none()
        self.assertEqual(res.get(), None)

        # execute, it will still return None, but underneath it is an EmptyResult
        # indicating its actual result was not persisted
        huey_results.execute(huey_results.dequeue())
        self.assertEqual(res.get(), None)
        self.assertEqual(res._result, EmptyData)

        # execute again, this time note that we're pointing at the invoker
        # that *does* accept None as a store-able result
        res = returns_none2()
        self.assertEqual(res.get(), None)

        # it stores None
        huey_store_none.execute(huey_store_none.dequeue())
        self.assertEqual(res.get(), None)
        self.assertEqual(res._result, None)

    def test_huey_result_method(self):
        res = add_values(1, 2)
        tid = res.task.task_id

        res2 = add_values(0, 0)
        tid2 = res2.task.task_id

        self.assertTrue(huey_results.result(tid) is None)
        self.assertTrue(huey_results.result(tid2) is None)

        # Execute the first task
        huey_results.execute(huey_results.dequeue())
        self.assertEqual(huey_results.result(tid), 3)
        self.assertTrue(huey_results.result(tid2) is None)

        # Execute the second task, which returns a zero value.
        huey_results.execute(huey_results.dequeue())
        self.assertEqual(huey_results.result(tid2), 0)

    def test_task_store(self):
        dt1 = datetime.datetime(2011, 1, 1, 0, 0)
        dt2 = datetime.datetime(2035, 1, 1, 0, 0)

        add_values.schedule(args=('k', 'v'), eta=dt1, convert_utc=False)
        task1 = huey_results.dequeue()

        add_values.schedule(args=('k2', 'v2'), eta=dt2, convert_utc=False)
        task2 = huey_results.dequeue()

        add_values('k3', 'v3')
        task3 = huey_results.dequeue()

        # add the command to the schedule
        huey_results.add_schedule(task1)
        self.assertEqual(huey_results.scheduled_count(), 1)

        # add a future-dated command
        huey_results.add_schedule(task2)
        self.assertEqual(huey_results.scheduled_count(), 2)

        huey_results.add_schedule(task3)

        tasks = huey_results.read_schedule(dt1)
        self.assertEqual(tasks, [task3, task1])

        tasks = huey_results.read_schedule(dt1)
        self.assertEqual(tasks, [])

        tasks = huey_results.read_schedule(dt2)
        self.assertEqual(tasks, [task2])

    def test_ready_to_run_method(self):
        dt1 = datetime.datetime(2011, 1, 1, 0, 0)
        dt2 = datetime.datetime(2035, 1, 1, 0, 0)

        add_values.schedule(args=('k', 'v'), eta=dt1)
        task1 = huey_results.dequeue()

        add_values.schedule(args=('k2', 'v2'), eta=dt2)
        task2 = huey_results.dequeue()

        add_values('k3', 'v3')
        task3 = huey_results.dequeue()

        add_values.schedule(args=('k4', 'v4'), task_id='test_task_id')
        task4 = huey_results.dequeue()

        # sanity check what should be run
        self.assertTrue(huey_results.ready_to_run(task1))
        self.assertFalse(huey_results.ready_to_run(task2))
        self.assertTrue(huey_results.ready_to_run(task3))
        self.assertTrue(huey_results.ready_to_run(task4))
        self.assertEqual('test_task_id', task4.task_id)

    def test_task_delay(self):
        curr = datetime.datetime.utcnow()
        curr50 = curr + datetime.timedelta(seconds=50)
        curr70 = curr + datetime.timedelta(seconds=70)

        add_values.schedule(args=('k', 'v'), delay=60)
        task1 = huey_results.dequeue()

        add_values.schedule(args=('k2', 'v2'), delay=600)
        task2 = huey_results.dequeue()

        add_values('k3', 'v3')
        task3 = huey_results.dequeue()

        # add the command to the schedule
        huey_results.add_schedule(task1)
        huey_results.add_schedule(task2)
        huey_results.add_schedule(task3)

        # sanity check what should be run
        self.assertFalse(huey_results.ready_to_run(task1))
        self.assertFalse(huey_results.ready_to_run(task2))
        self.assertTrue(huey_results.ready_to_run(task3))

        self.assertFalse(huey_results.ready_to_run(task1, curr50))
        self.assertFalse(huey_results.ready_to_run(task2, curr50))
        self.assertTrue(huey_results.ready_to_run(task3, curr50))

        self.assertTrue(huey_results.ready_to_run(task1, curr70))
        self.assertFalse(huey_results.ready_to_run(task2, curr70))
        self.assertTrue(huey_results.ready_to_run(task3, curr70))
