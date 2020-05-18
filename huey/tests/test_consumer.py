import datetime
import time

from huey.api import crontab
from huey.consumer import Consumer
from huey.consumer import Scheduler
from huey.consumer_options import ConsumerConfig
from huey.tests.base import BaseTestCase
from huey.utils import time_clock


class TestConsumer(Consumer):
    class _Scheduler(Scheduler):
        def sleep_for_interval(self, current, interval):
            pass
    scheduler_class = _Scheduler


class TestConsumerIntegration(BaseTestCase):
    consumer_class = TestConsumer

    def test_consumer_minimal(self):
        @self.huey.task()
        def task_a(n):
            return n + 1

        with self.consumer_context():
            result = task_a(1)
            self.assertEqual(result.get(blocking=True, timeout=2), 2)

    def work_on_tasks(self, consumer, n=1, now=None):
        worker, _ = consumer.worker_threads[0]
        for i in range(n):
            self.assertEqual(len(self.huey), n - i)
            worker.loop(now)

    def schedule_tasks(self, consumer, now=None):
        scheduler = consumer._create_scheduler()
        scheduler._next_loop = time_clock() + 60
        scheduler._next_periodic = time_clock() - 60
        scheduler.loop(now)

    def test_consumer_schedule_task(self):
        @self.huey.task()
        def task_a(n):
            return n + 1

        now = datetime.datetime.now()
        eta = now + datetime.timedelta(days=1)
        r60 = task_a.schedule((2,), delay=60)
        rday = task_a.schedule((3,), eta=eta)

        consumer = self.consumer(workers=1)
        self.work_on_tasks(consumer, 2)  # Process the two messages.

        self.assertEqual(len(self.huey), 0)
        self.assertEqual(self.huey.scheduled_count(), 2)

        self.schedule_tasks(consumer, now)
        self.assertEqual(len(self.huey), 0)
        self.assertEqual(self.huey.scheduled_count(), 2)

        # Ensure that the task that had a delay of 60s is read from schedule.
        later = now + datetime.timedelta(seconds=65)
        self.schedule_tasks(consumer, later)
        self.assertEqual(len(self.huey), 1)
        self.assertEqual(self.huey.scheduled_count(), 1)

        # We can now work on our scheduled task.
        self.work_on_tasks(consumer, 1, later)
        self.assertEqual(r60.get(), 3)

        # Verify the task was run and that there is only one task remaining to
        # be scheduled (in a day).
        self.assertEqual(len(self.huey), 0)
        self.assertEqual(self.huey.scheduled_count(), 1)

        tomorrow = now + datetime.timedelta(days=1)
        self.schedule_tasks(consumer, tomorrow)
        self.work_on_tasks(consumer, 1, tomorrow)
        self.assertEqual(rday.get(), 4)
        self.assertEqual(len(self.huey), 0)
        self.assertEqual(self.huey.scheduled_count(), 0)

    def test_consumer_periodic_tasks(self):
        state = []

        @self.huey.periodic_task(crontab(minute='*/10'))
        def task_p1():
            state.append('p1')

        @self.huey.periodic_task(crontab(minute='0', hour='0'))
        def task_p2():
            state.append('p2')

        consumer = self.consumer(workers=1)
        dt = datetime.datetime(2000, 1, 1, 0, 0)
        self.schedule_tasks(consumer, dt)
        self.assertEqual(len(self.huey), 2)
        self.work_on_tasks(consumer, 2)
        self.assertEqual(state, ['p1', 'p2'])

        dt = datetime.datetime(2000, 1, 1, 12, 0)
        self.schedule_tasks(consumer, dt)
        self.assertEqual(len(self.huey), 1)
        self.work_on_tasks(consumer, 1)
        self.assertEqual(state, ['p1', 'p2', 'p1'])

        task_p1.revoke()
        self.schedule_tasks(consumer, dt)
        self.assertEqual(len(self.huey), 1)  # Enqueued despite being revoked.
        self.work_on_tasks(consumer, 1)
        self.assertEqual(state, ['p1', 'p2', 'p1'])  # No change, not executed.


class TestConsumerConfig(BaseTestCase):
    def test_default_config(self):
        cfg = ConsumerConfig()
        cfg.validate()
        consumer = self.huey.create_consumer(**cfg.values)
        self.assertEqual(consumer.workers, 1)
        self.assertEqual(consumer.worker_type, 'thread')
        self.assertTrue(consumer.periodic)
        self.assertEqual(consumer.default_delay, 0.1)
        self.assertEqual(consumer.scheduler_interval, 1)
        self.assertTrue(consumer._health_check)

    def test_consumer_config(self):
        cfg = ConsumerConfig(workers=3, worker_type='process', initial_delay=1,
                             backoff=2, max_delay=4, check_worker_health=False,
                             scheduler_interval=30, periodic=False)
        cfg.validate()
        consumer = self.huey.create_consumer(**cfg.values)

        self.assertEqual(consumer.workers, 3)
        self.assertEqual(consumer.worker_type, 'process')
        self.assertFalse(consumer.periodic)
        self.assertEqual(consumer.default_delay, 1)
        self.assertEqual(consumer.backoff, 2)
        self.assertEqual(consumer.max_delay, 4)
        self.assertEqual(consumer.scheduler_interval, 30)
        self.assertFalse(consumer._health_check)

    def test_invalid_values(self):
        def assertInvalid(**kwargs):
            cfg = ConsumerConfig(**kwargs)
            self.assertRaises(ValueError, cfg.validate)

        assertInvalid(backoff=0.5)
        assertInvalid(scheduler_interval=90)
        assertInvalid(scheduler_interval=7)
        assertInvalid(scheduler_interval=45)
