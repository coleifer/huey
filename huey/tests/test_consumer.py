import datetime
import threading
import time

from huey import crontab
from huey.consumer import Consumer
from huey.consumer import Scheduler
from huey.consumer import Worker
from huey.tests.base import b
from huey.tests.base import BrokenHuey
from huey.tests.base import CaptureLogs
from huey.tests.base import HueyTestCase
from huey.tests.base import test_huey


# Store some global state.
state = {}

lock = threading.Lock()

# Create some test tasks.
@test_huey.task()
def modify_state(k, v):
    with lock:
        state[k] = v
    return v

@test_huey.task()
def blow_up():
    raise Exception('blowed up')

@test_huey.task(retries=3)
def retry_task(k, always_fail=True):
    if k not in state:
        if not always_fail:
            state[k] = 'fixed'
        raise Exception('fappsk')
    return state[k]

@test_huey.task(retries=3, retry_delay=10)
def retry_task_delay(k, always_fail=True):
    if k not in state:
        if not always_fail:
            state[k] = 'fixed'
        raise Exception('fappsk')
    return state[k]

@test_huey.periodic_task(crontab(minute='2'))
def hourly_task():
    state['p'] = 'y'


class TestExecution(HueyTestCase):
    def create_consumer(self, worker_type='thread'):
        return Consumer(
            self.huey,
            max_delay=0.1,
            workers=2,
            worker_type=worker_type)

    def test_threaded_execution(self):
        consumer = self.create_consumer()
        r1 = modify_state('k1', 'v1')
        r2 = modify_state('k2', 'v2')
        r3 = modify_state('k3', 'v3')

        with CaptureLogs() as capture:
            consumer.start()

            r1.get(blocking=True)
            r2.get(blocking=True)
            r3.get(blocking=True)

            consumer.stop()
            for worker in consumer.worker_threads:
                worker.join()

        self.assertEqual(state, {'k1': 'v1', 'k2': 'v2', 'k3': 'v3'})


class TestConsumerAPIs(HueyTestCase):
    def setUp(self):
        super(TestConsumerAPIs, self).setUp()
        global state
        state = {}

    def get_periodic_tasks(self):
        return [hourly_task.task_class()]

    def test_dequeue_errors(self):
        huey = BrokenHuey()
        consumer = Consumer(huey, max_delay=0.1, workers=2,
                            worker_type='thread')

        worker = consumer._create_worker()
        state = {}

        @huey.task()
        def modify_broken(k, v):
            state[k] = v

        with CaptureLogs() as capture:
            res = modify_broken('k', 'v')
            worker.loop()

        self.assertEqual(capture.messages, ['Error reading from queue'])
        self.assertEqual(state, {})

    def test_scheduler_interval(self):
        consumer = self.get_consumer(scheduler_interval=0.1)
        self.assertEqual(consumer.scheduler_interval, 1)

        consumer = self.get_consumer(scheduler_interval=120)
        self.assertEqual(consumer.scheduler_interval, 60)

        consumer = self.get_consumer(scheduler_interval=10)
        self.assertEqual(consumer.scheduler_interval, 10)

    def test_message_processing(self):
        worker = self.consumer._create_worker()
        self.assertEqual(state, {})

        with CaptureLogs() as capture:
            res = modify_state('k', 'v')
            worker.loop()

        self.assertLogs(capture, ['Executing %s' % res.task])

        self.assertEqual(state, {'k': 'v'})
        self.assertEqual(res.get(), 'v')

        self.assertTaskEvents(
            ('started', res.task),
            ('finished', res.task))

    def test_worker(self):
        modify_state('k', 'w')
        task = test_huey.dequeue()
        self.worker(task)
        self.assertEqual(state, {'k': 'w'})

    def test_worker_exception(self):
        with CaptureLogs() as capture:
            blow_up()
            task = test_huey.dequeue()

        # Nothing happens because the task is not executed.
        self.assertLogs(capture, [])

        with CaptureLogs() as capture:
            self.worker(task)

        self.assertLogs(capture, [
            'Executing',
            'Unhandled exception in worker'])

        self.assertTaskEvents(
            ('started', task),
            ('error-task', task))

    def test_retries_and_logging(self):
        # This will continually fail.
        retry_task('blampf')

        for i in reversed(range(4)):
            task = test_huey.dequeue()
            self.assertEqual(task.retries, i)
            with CaptureLogs() as capture:
                self.worker(task)

            if i > 0:
                self.assertLogs(capture, [
                    'Executing',
                    'Unhandled',
                    'Re-enqueueing'])
                self.assertTaskEvents(
                    ('started', task),
                    ('error-task', task),
                    ('retrying', task))
            else:
                self.assertLogs(capture, [
                    'Executing',
                    'Unhandled'])
                self.assertTaskEvents(
                    ('started', task),
                    ('error-task', task))

        self.assertEqual(len(test_huey), 0)

    def test_retries_with_success(self):
        # this will fail once, then succeed
        retry_task('blampf', False)
        self.assertFalse('blampf' in state)

        task = test_huey.dequeue()
        with CaptureLogs() as capture:
            self.worker(task)

        self.assertLogs(capture, [
            'Executing',
            'Unhandled',
            'Re-enqueueing'])

        task = test_huey.dequeue()
        self.assertEqual(task.retries, 2)
        self.worker(task)

        self.assertEqual(state['blampf'], 'fixed')
        self.assertEqual(len(test_huey), 0)

        self.assertTaskEvents(
            ('started', task),
            ('error-task', task),
            ('retrying', task),
            ('started', task),
            ('finished', task))

    def test_scheduling(self):
        dt = datetime.datetime(2011, 1, 1, 0, 1)
        dt2 = datetime.datetime(2037, 1, 1, 0, 1)
        ad1 = modify_state.schedule(args=('k', 'v'), eta=dt, convert_utc=False)
        ad2 = modify_state.schedule(args=('k2', 'v2'), eta=dt2, convert_utc=False)

        # Dequeue the past-timestamped task and run it.
        worker = self.consumer._create_worker()
        worker.loop()

        self.assertTrue('k' in state)

        # Dequeue the future-timestamped task.
        worker.loop()

        # Verify the task got stored in the schedule instead of executing.
        self.assertFalse('k2' in state)

        self.assertTaskEvents(
            ('started', ad1.task),
            ('finished', ad1.task),
            ('scheduled', ad2.task))

        # run through an iteration of the scheduler
        self.scheduler(dt)

        # our command was not enqueued and no events were emitted.
        self.assertEqual(len(self.huey), 0)

        # run through an iteration of the scheduler
        self.scheduler(dt2)

        # our command was enqueued
        self.assertEqual(len(self.huey), 1)

    def test_retry_scheduling(self):
        # this will continually fail
        retry_task_delay('blampf')
        cur_time = datetime.datetime.utcnow()

        task = self.huey.dequeue()

        with CaptureLogs() as capture:
            self.worker(task, cur_time)

        self.assertLogs(capture, [
            'Executing',
            'Unhandled exception',
            'Re-enqueueing task',
            'Adding'])

        in_8 = cur_time + datetime.timedelta(seconds=8)
        tasks_from_sched = self.huey.read_schedule(in_8)
        self.assertEqual(tasks_from_sched, [])

        in_11 = cur_time + datetime.timedelta(seconds=11)
        tasks_from_sched = self.huey.read_schedule(in_11)
        self.assertEqual(tasks_from_sched, [task])

        task = tasks_from_sched[0]
        self.assertEqual(task.retries, 2)
        exec_time = task.execute_time

        self.assertEqual((exec_time - cur_time).seconds, 10)
        self.assertTaskEvents(
            ('started', task),
            ('error-task', task),
            ('retrying', task),
            ('scheduled', task))

    def test_revoking_normal(self):
        # enqueue 2 normal commands
        r1 = modify_state('k', 'v')
        r2 = modify_state('k2', 'v2')

        # revoke the first *before it has been checked*
        r1.revoke()
        self.assertTrue(test_huey.is_revoked(r1.task))
        self.assertFalse(test_huey.is_revoked(r2.task))

        # dequeue a *single* message (r1)
        task = test_huey.dequeue()
        self.worker(task)

        self.assertTaskEvents(('revoked', r1.task))

        # no changes and the task was not added to the schedule
        self.assertFalse('k' in state)

        # dequeue a *single* message
        task = test_huey.dequeue()
        self.worker(task)

        self.assertTrue('k2' in state)

    def test_revoking_schedule(self):
        global state
        dt = datetime.datetime(2011, 1, 1)
        dt2 = datetime.datetime(2037, 1, 1)

        r1 = modify_state.schedule(args=('k', 'v'), eta=dt, convert_utc=False)
        r2 = modify_state.schedule(args=('k2', 'v2'), eta=dt, convert_utc=False)
        r3 = modify_state.schedule(args=('k3', 'v3'), eta=dt2, convert_utc=False)
        r4 = modify_state.schedule(args=('k4', 'v4'), eta=dt2, convert_utc=False)

        # revoke r1 and r3
        r1.revoke()
        r3.revoke()
        self.assertTrue(test_huey.is_revoked(r1.task))
        self.assertFalse(test_huey.is_revoked(r2.task))
        self.assertTrue(test_huey.is_revoked(r3.task))
        self.assertFalse(test_huey.is_revoked(r4.task))

        expected = [
            #state,        schedule
            ({},           0),
            ({'k2': 'v2'}, 0),
            ({'k2': 'v2'}, 1),
            ({'k2': 'v2'}, 2),
        ]

        for i in range(4):
            curr_state, curr_sched = expected[i]

            # dequeue a *single* message
            task = test_huey.dequeue()
            self.worker(task)

            self.assertEqual(state, curr_state)
            self.assertEqual(test_huey.scheduled_count(), curr_sched)

        # lets pretend its 2037
        future = dt2 + datetime.timedelta(seconds=1)
        self.scheduler(future)
        self.assertEqual(test_huey.scheduled_count(), 0)

        # There are two tasks in the queue now (r3 and r4) -- process both.
        for i in range(2):
            task = test_huey.dequeue()
            self.worker(task, future)

        self.assertEqual(state, {'k2': 'v2', 'k4': 'v4'})

    def test_periodic_scheduler(self):
        dt = datetime.datetime(2011, 1, 3, 3, 7)
        sched = self.scheduler(dt, False)
        self.assertEqual(sched._counter, 1)
        self.assertEqual(sched._q, 5)
        self.assertEqual(len(self.huey), 0)

        dt = datetime.datetime(2011, 1, 1, 0, 2)
        sched = self.scheduler(dt, True)
        self.assertEqual(sched._counter, 0)
        self.assertEqual(sched._q, 5)
        self.assertEqual(state, {})

        for i in range(len(self.huey)):
            task = test_huey.dequeue()
            self.worker(task, dt)

        self.assertEqual(state, {'p': 'y'})

    def test_revoking_periodic(self):
        global state

        def loop_periodic(ts):
            self.scheduler(ts, True)
            for i in range(len(self.huey)):
                task = test_huey.dequeue()
                self.worker(task, ts)

        dt = datetime.datetime(2011, 1, 1, 0, 2)

        # revoke the command once
        hourly_task.revoke(revoke_once=True)
        self.assertTrue(hourly_task.is_revoked())

        # it will be skipped the first go-round
        loop_periodic(dt)

        # it has not been run
        self.assertEqual(state, {})

        # the next go-round it will be enqueued
        loop_periodic(dt)

        # our command was run
        self.assertEqual(state, {'p': 'y'})

        # reset state
        state = {}

        # revoke the command
        hourly_task.revoke()
        self.assertTrue(hourly_task.is_revoked())

        # it will no longer be enqueued
        loop_periodic(dt)
        loop_periodic(dt)
        self.assertEqual(state, {})

        # restore
        hourly_task.restore()
        self.assertFalse(hourly_task.is_revoked())

        # it will now be enqueued
        loop_periodic(dt)
        self.assertEqual(state, {'p': 'y'})

        # reset
        state = {}

        # revoke for an hour
        td = datetime.timedelta(seconds=3600)
        hourly_task.revoke(revoke_until=dt + td)

        loop_periodic(dt)
        self.assertEqual(state, {})

        # after an hour it is back
        loop_periodic(dt + td)
        self.assertEqual(state, {'p': 'y'})

        # our data store should reflect the delay
        task_obj = hourly_task.task_class()
        self.assertEqual(test_huey.result_count(), 1)
        self.assertTrue(test_huey.storage.has_data_for_key(task_obj.revoke_id))

    def test_odd_scheduler_interval(self):
        self.consumer.stop()
        self.consumer = self.get_consumer(scheduler_interval=13)

        curr_time = datetime.datetime(2015, 12, 30, 21, 1, 7)
        scheduler = self.scheduler(curr_time)
        self.assertEqual(scheduler._counter, 1)
        self.assertEqual(scheduler._q, 4)

        scheduler.loop(curr_time.replace(second=20))
        self.assertEqual(scheduler._counter, 2)
        self.assertEqual(scheduler._q, 4)
        self.assertEqual(len(self.huey), 0)

        scheduler.loop(curr_time.replace(second=33))
        self.assertEqual(scheduler._counter, 3)
        self.assertEqual(scheduler._q, 4)
        self.assertEqual(len(self.huey), 0)

        scheduler.loop(curr_time.replace(second=46))
        self.assertEqual(scheduler._counter, 4)
        self.assertEqual(scheduler._q, 4)
        self.assertEqual(scheduler._r, 8)
        self.assertEqual(len(self.huey), 0)

        seconds = (59 + scheduler._r) % 60
        scheduler.loop(curr_time.replace(minute=2, second=seconds))
        self.assertEqual(scheduler._counter, 0)
        self.assertEqual(scheduler._q, 4)
        self.assertEqual(len(self.huey), 1)
