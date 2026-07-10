import datetime
import unittest

try:
    import gevent
except ImportError:
    gevent = None
else:
    from huey.contrib.mini import MiniHuey

from huey import crontab
from huey.tests.base import BaseTestCase


@unittest.skipIf(gevent is None, 'requires gevent')
class TestMiniHuey(BaseTestCase):
    def get_huey(self):
        return MiniHuey(interval=0.1)

    def setUp(self):
        super(TestMiniHuey, self).setUp()
        self.huey.start()

    def tearDown(self):
        if self.huey._run_t is not None:
            self.huey.stop()
        super(TestMiniHuey, self).tearDown()

    def make_add(self):
        @self.huey.task()
        def add(a, b):
            return a + b
        return add

    def avoid_minute_boundary(self):
        # Periodic checks fire once per wall-clock minute. Ensure the clock
        # cannot roll over mid-test and trigger a legitimate second check.
        if datetime.datetime.now().second >= 58:
            gevent.sleep(2.5)

    def test_task(self):
        add = self.make_add()
        self.assertEqual(add(1, 2).get(), 3)
        self.assertEqual(add(3, 4)(), 7)

    def test_task_error(self):
        @self.huey.task()
        def failure():
            raise ValueError('nope')

        self.assertRaises(ValueError, failure().get)

    def test_schedule_delay(self):
        add = self.make_add()
        res = add.schedule((1, 2), delay=0.2)
        self.assertEqual(res.get(timeout=5), 3)

    def test_schedule_eta_aware(self):
        add = self.make_add()
        eta = (datetime.datetime.now(datetime.timezone.utc) +
               datetime.timedelta(seconds=0.2))
        res = add.schedule((2, 3), eta=eta)
        self.assertEqual(res.get(timeout=5), 5)

    def test_schedule_validation(self):
        add = self.make_add()
        self.assertRaises(ValueError, add.schedule, (1, 2))
        self.assertRaises(ValueError, add.schedule, (1, 2), delay=1,
                          eta=datetime.datetime.now())

    def test_restart(self):
        add = self.make_add()
        self.huey.stop()
        self.huey.start()
        res = add.schedule((1, 2), delay=0.1)
        self.assertEqual(res.get(timeout=5), 3)

    def test_periodic_task(self):
        state = []

        @self.huey.task(crontab(minute='*'))
        def tick():
            state.append(1)

        self.avoid_minute_boundary()
        self.huey._last_check -= datetime.timedelta(minutes=1)
        gevent.sleep(0.3)
        self.assertEqual(len(state), 1)
        self.assertEqual(self.huey._last_check, datetime.datetime.now()
                         .replace(second=0, microsecond=0))

        gevent.sleep(0.3)
        self.assertEqual(len(state), 1)

    def test_scheduler_error(self):
        add = self.make_add()

        @self.huey.task(lambda now: 1 / 0)
        def broken():
            pass

        self.avoid_minute_boundary()
        self.huey._last_check -= datetime.timedelta(minutes=1)
        gevent.sleep(0.3)
        self.assertFalse(self.huey._run_t.dead)

        res = add.schedule((1, 2), delay=0.1)
        self.assertEqual(res.get(timeout=5), 3)
