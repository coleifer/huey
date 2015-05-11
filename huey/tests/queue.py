import datetime
import unittest

from huey import crontab
from huey import exceptions as huey_exceptions
from huey import Huey
from huey.api import QueueTask
from huey.backends.dummy import DummyDataStore
from huey.backends.dummy import DummyQueue
from huey.backends.dummy import DummySchedule
from huey.registry import registry
from huey.utils import EmptyData
from huey.utils import local_to_utc


queue_name = 'test-queue'
queue = DummyQueue(queue_name)
schedule = DummySchedule(queue_name)
huey = Huey(queue, schedule=schedule)

res_queue_name = 'test-queue-2'
res_queue = DummyQueue(res_queue_name)
res_store = DummyDataStore(res_queue_name)

res_huey = Huey(res_queue, res_store, schedule)
res_huey_nones = Huey(res_queue, res_store, store_none=True)

# store some global state
state = {}
last_executed_task_class = []

# create a decorated queue command
@huey.task()
def add(key, value):
    state[key] = value

@huey.task(include_task=True)
def self_aware(key, value, task=None):
    last_executed_task_class.append(task.__class__.__name__)

# create a periodic queue command
@huey.periodic_task(crontab(minute='0'))
def add_on_the_hour():
    state['periodic'] = 'x'

# define a command using the class
class AddTask(QueueTask):
    def execute(self):
        k, v = self.data
        state[k] = v

# create a command that raises an exception
class BampfException(Exception):
    pass

@huey.task()
def throw_error():
    raise BampfException('bampf')

@res_huey.task()
def add2(a, b):
    return a + b

@res_huey.periodic_task(crontab(minute='0'))
def add_on_the_hour2():
    state['periodic'] = 'x'

@res_huey.task()
def returns_none():
    return None

@res_huey_nones.task()
def returns_none2():
    return None


class HueyTestCase(unittest.TestCase):
    def setUp(self):
        global state
        global last_executed_task_class
        queue.flush()
        res_queue.flush()
        schedule.flush()
        state = {}
        last_executed_task_class = []

    def test_registration(self):
        self.assertTrue('queuecmd_add' in registry)
        self.assertTrue('queuecmd_add_on_the_hour' in registry)
        self.assertTrue('AddTask' in registry)

    def test_enqueue(self):
        # sanity check
        self.assertEqual(len(queue), 0)

        # initializing the command does not enqueue it
        ac = AddTask(('k', 'v'))
        self.assertEqual(len(queue), 0)

        # ok, enqueue it, then check that it was enqueued
        huey.enqueue(ac)
        self.assertEqual(len(queue), 1)

        # it can be enqueued multiple times
        huey.enqueue(ac)
        self.assertEqual(len(queue), 2)

        # no changes to state
        self.assertFalse('k' in state)

    def test_enqueue_decorator(self):
        # sanity check
        self.assertEqual(len(queue), 0)

        add('k', 'v')
        self.assertEqual(len(queue), 1)

        add('k', 'v')
        self.assertEqual(len(queue), 2)

        # no changes to state
        self.assertFalse('k' in state)

    def test_schedule(self):
        dt = datetime.datetime(2011, 1, 1, 0, 1)
        add('k', 'v')
        self.assertEqual(len(queue), 1)

        task = huey.dequeue()
        self.assertEqual(task.execute_time, None)

        add.schedule(args=('k2', 'v2'), eta=dt)
        self.assertEqual(len(queue), 1)
        task = huey.dequeue()
        self.assertEqual(task.execute_time, local_to_utc(dt))

        add.schedule(args=('k3', 'v3'), eta=dt, convert_utc=False)
        self.assertEqual(len(queue), 1)
        task = huey.dequeue()
        self.assertEqual(task.execute_time, dt)

    def test_error_raised(self):
        throw_error()

        # no error
        task = huey.dequeue()

        # error
        self.assertRaises(BampfException, huey.execute, task)

    def test_internal_error(self):
        """
        Verify that exceptions are wrapped with the special "huey"
        exception classes.
        """
        class SpecialException(Exception):
            pass

        class BrokenQueue(DummyQueue):
            def read(self):
                raise SpecialException('read error')

            def write(self, data):
                raise SpecialException('write error')

        class BrokenDataStore(DummyDataStore):
            def get(self, key):
                raise SpecialException('get error')

            def put(self, key, value):
                raise SpecialException('put error')

        class BrokenSchedule(DummySchedule):
            def add(self, data, ts):
                raise SpecialException('add error')

            def read(self, ts):
                raise SpecialException('read error')

        task = AddTask()
        huey = Huey(
            BrokenQueue('q'),
            BrokenDataStore('q'),
            BrokenSchedule('q'))

        self.assertRaises(
            huey_exceptions.QueueWriteException,
            huey.enqueue,
            AddTask())
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

        add('k', 'v')
        task = huey.dequeue()

        self.assertTrue(isinstance(task, QueueTask))
        self.assertEqual(task.get_data(), (('k', 'v'), {}))

    def test_execution(self):
        self.assertFalse('k' in state)
        add('k', 'v')

        task = huey.dequeue()
        self.assertFalse('k' in state)

        huey.execute(task)
        self.assertEqual(state['k'], 'v')

        add('k', 'X')
        self.assertEqual(state['k'], 'v')

        huey.execute(huey.dequeue())
        self.assertEqual(state['k'], 'X')

        self.assertRaises(TypeError, huey.execute, huey.dequeue())

    def test_self_awareness(self):
        self_aware('k', 'v')
        task = huey.dequeue()
        huey.execute(task)
        self.assertEqual(last_executed_task_class.pop(), "queuecmd_self_aware")

        self_aware('k', 'v')
        huey.execute(huey.dequeue())
        self.assertEqual(last_executed_task_class.pop(), "queuecmd_self_aware")

        add('k', 'x')
        huey.execute(huey.dequeue())
        self.assertEqual(len(last_executed_task_class), 0)

    def test_call_local(self):
        self.assertEqual(len(queue), 0)
        self.assertEqual(state, {})
        add.call_local('nugget', 'green')

        self.assertEqual(len(queue), 0)
        self.assertEqual(state['nugget'], 'green')

    def test_revoke(self):
        ac = AddTask(('k', 'v'))
        ac2 = AddTask(('k2', 'v2'))
        ac3 = AddTask(('k3', 'v3'))

        res_huey.enqueue(ac)
        res_huey.enqueue(ac2)
        res_huey.enqueue(ac3)
        res_huey.enqueue(ac2)
        res_huey.enqueue(ac)

        self.assertEqual(len(res_queue), 5)
        res_huey.revoke(ac2)

        while res_queue:
            task = res_huey.dequeue()
            if not res_huey.is_revoked(task):
                res_huey.execute(task)

        self.assertEqual(state, {'k': 'v', 'k3': 'v3'})

    def test_revoke_periodic(self):
        add_on_the_hour2.revoke()
        self.assertTrue(add_on_the_hour2.is_revoked())

        # it is still revoked
        self.assertTrue(add_on_the_hour2.is_revoked())

        add_on_the_hour2.restore()
        self.assertFalse(add_on_the_hour2.is_revoked())

        add_on_the_hour2.revoke(revoke_once=True)
        self.assertTrue(add_on_the_hour2.is_revoked()) # it is revoked once, but we are preserving that state
        self.assertTrue(add_on_the_hour2.is_revoked(peek=False)) # is revoked once, but clear state
        self.assertFalse(add_on_the_hour2.is_revoked()) # no longer revoked

        d = datetime.datetime
        add_on_the_hour2.revoke(revoke_until=d(2011, 1, 1, 11, 0))
        self.assertTrue(add_on_the_hour2.is_revoked(dt=d(2011, 1, 1, 10, 0)))
        self.assertTrue(add_on_the_hour2.is_revoked(dt=d(2011, 1, 1, 10, 59)))
        self.assertFalse(add_on_the_hour2.is_revoked(dt=d(2011, 1, 1, 11, 0)))

        add_on_the_hour2.restore()
        self.assertFalse(add_on_the_hour2.is_revoked())

    def test_result_store(self):
        res = add2(1, 2)
        res2 = add2(4, 5)
        res3 = add2(0, 0)

        # none have been executed as yet
        self.assertEqual(res.get(), None)
        self.assertEqual(res2.get(), None)
        self.assertEqual(res3.get(), None)

        # execute the first task
        res_huey.execute(res_huey.dequeue())
        self.assertEqual(res.get(), 3)
        self.assertEqual(res2.get(), None)
        self.assertEqual(res3.get(), None)

        # execute the second task
        res_huey.execute(res_huey.dequeue())
        self.assertEqual(res.get(), 3)
        self.assertEqual(res2.get(), 9)
        self.assertEqual(res3.get(), None)

        # execute the 3rd, which returns a zero value
        res_huey.execute(res_huey.dequeue())
        self.assertEqual(res.get(), 3)
        self.assertEqual(res2.get(), 9)
        self.assertEqual(res3.get(), 0)

        # check that it returns None when nothing is present
        res = returns_none()
        self.assertEqual(res.get(), None)

        # execute, it will still return None, but underneath it is an EmptyResult
        # indicating its actual result was not persisted
        res_huey.execute(res_huey.dequeue())
        self.assertEqual(res.get(), None)
        self.assertEqual(res._result, EmptyData)

        # execute again, this time note that we're pointing at the invoker
        # that *does* accept None as a store-able result
        res = returns_none2()
        self.assertEqual(res.get(), None)

        # it stores None
        res_huey_nones.execute(res_huey_nones.dequeue())
        self.assertEqual(res.get(), None)
        self.assertEqual(res._result, None)

    def test_task_store(self):
        dt1 = datetime.datetime(2011, 1, 1, 0, 0)
        dt2 = datetime.datetime(2035, 1, 1, 0, 0)

        add2.schedule(args=('k', 'v'), eta=dt1, convert_utc=False)
        task1 = res_huey.dequeue()

        add2.schedule(args=('k2', 'v2'), eta=dt2, convert_utc=False)
        task2 = res_huey.dequeue()

        add2('k3', 'v3')
        task3 = res_huey.dequeue()

        # add the command to the schedule
        res_huey.add_schedule(task1)
        self.assertEqual(len(res_huey.schedule._schedule), 1)

        # add a future-dated command
        res_huey.add_schedule(task2)
        self.assertEqual(len(res_huey.schedule._schedule), 2)

        res_huey.add_schedule(task3)

        tasks = res_huey.read_schedule(dt1)
        self.assertEqual(tasks, [task3, task1])

        tasks = res_huey.read_schedule(dt1)
        self.assertEqual(tasks, [])

        tasks = res_huey.read_schedule(dt2)
        self.assertEqual(tasks, [task2])

    def test_ready_to_run_method(self):
        dt1 = datetime.datetime(2011, 1, 1, 0, 0)
        dt2 = datetime.datetime(2035, 1, 1, 0, 0)

        add2.schedule(args=('k', 'v'), eta=dt1)
        task1 = res_huey.dequeue()

        add2.schedule(args=('k2', 'v2'), eta=dt2)
        task2 = res_huey.dequeue()

        add2('k3', 'v3')
        task3 = res_huey.dequeue()

        add2.schedule(args=('k4', 'v4'), task_id='test_task_id')
        task4 = res_huey.dequeue()

        # sanity check what should be run
        self.assertTrue(res_huey.ready_to_run(task1))
        self.assertFalse(res_huey.ready_to_run(task2))
        self.assertTrue(res_huey.ready_to_run(task3))
        self.assertTrue(res_huey.ready_to_run(task4))
        self.assertEqual('test_task_id', task4.task_id)

    def test_task_delay(self):
        curr = datetime.datetime.utcnow()
        curr50 = curr + datetime.timedelta(seconds=50)
        curr70 = curr + datetime.timedelta(seconds=70)

        add2.schedule(args=('k', 'v'), delay=60)
        task1 = res_huey.dequeue()

        add2.schedule(args=('k2', 'v2'), delay=600)
        task2 = res_huey.dequeue()

        add2('k3', 'v3')
        task3 = res_huey.dequeue()

        # add the command to the schedule
        res_huey.add_schedule(task1)
        res_huey.add_schedule(task2)
        res_huey.add_schedule(task3)

        # sanity check what should be run
        self.assertFalse(res_huey.ready_to_run(task1))
        self.assertFalse(res_huey.ready_to_run(task2))
        self.assertTrue(res_huey.ready_to_run(task3))

        self.assertFalse(res_huey.ready_to_run(task1, curr50))
        self.assertFalse(res_huey.ready_to_run(task2, curr50))
        self.assertTrue(res_huey.ready_to_run(task3, curr50))

        self.assertTrue(res_huey.ready_to_run(task1, curr70))
        self.assertFalse(res_huey.ready_to_run(task2, curr70))
        self.assertTrue(res_huey.ready_to_run(task3, curr70))
