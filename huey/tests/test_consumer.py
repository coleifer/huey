import datetime
import time

from huey.consumer import Consumer
from huey.consumer import Scheduler
from huey.tests.base import BaseTestCase


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
            self.assertEqual(result.get(blocking=True), 2)

    def work_on_tasks(self, consumer, n=1, now=None):
        worker, _ = consumer.worker_threads[0]
        for i in range(n):
            self.assertEqual(len(self.huey), n - i)
            worker.loop(now)

    def schedule_tasks(self, consumer, now=None):
        scheduler = consumer._create_scheduler()
        scheduler._next_loop = time.time() + 60
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
