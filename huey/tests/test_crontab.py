import datetime
import unittest

from huey import crontab
from huey import every_between


class TestCrontab(unittest.TestCase):
    def test_crontab_month(self):
        # validates the following months, 1, 4, 7, 8, 9
        valids = [1, 4, 7, 8, 9]
        validate_m = crontab(month='1,4,*/6,8-9')

        for x in range(1, 13):
            res = validate_m(datetime.datetime(2011, x, 1))
            self.assertEqual(res, x in valids)

    def test_crontab_day(self):
        # validates the following days
        valids = [1, 4, 7, 8, 9, 13, 19, 25, 31]
        validate_d = crontab(day='*/6,1,4,8-9')

        for x in range(1, 32):
            res = validate_d(datetime.datetime(2011, 1, x))
            self.assertEqual(res, x in valids)

        valids = [1, 11, 21, 31]
        validate_d = crontab(day='*/10')
        for x in range(1, 32):
            res = validate_d(datetime.datetime(2011, 1, x))
            self.assertEqual(res, x in valids)

        valids.pop()  # Remove 31, as feb only has 28 days.
        for x in range(1, 29):
            res = validate_d(datetime.datetime(2011, 2, x))
            self.assertEqual(res, x in valids)

    def test_crontab_hour(self):
        # validates the following hours
        valids = [0, 1, 4, 6, 8, 9, 12, 18]
        validate_h = crontab(hour='8-9,*/6,1,4')

        for x in range(24):
            res = validate_h(datetime.datetime(2011, 1, 1, x))
            self.assertEqual(res, x in valids)

        edge = crontab(hour=0)
        self.assertTrue(edge(datetime.datetime(2011, 1, 1, 0, 0)))
        self.assertFalse(edge(datetime.datetime(2011, 1, 1, 12, 0)))

    def test_crontab_minute(self):
        # validates the following minutes
        valids = [0, 1, 4, 6, 8, 9, 12, 18, 24, 30, 36, 42, 48, 54]
        validate_m = crontab(minute='4,8-9,*/6,1')

        for x in range(60):
            res = validate_m(datetime.datetime(2011, 1, 1, 1, x))
            self.assertEqual(res, x in valids)

        # We don't ensure *every* X minutes, but just on the given intervals.
        valids = [0, 16, 32, 48]
        validate_m = crontab(minute='*/16')
        for x in range(60):
            res = validate_m(datetime.datetime(2011, 1, 1, 1, x))
            self.assertEqual(res, x in valids)

    def test_crontab_day_of_week(self):
        # validates the following days of week
        # jan, 1, 2011 is a saturday
        valids = [2, 4, 9, 11, 16, 18, 23, 25, 30]
        validate_dow = crontab(day_of_week='0,2')

        for x in range(1, 32):
            res = validate_dow(datetime.datetime(2011, 1, x))
            self.assertEqual(res, x in valids)

    def test_crontab_sunday(self):
        for dow in ('0', '7'):
            validate = crontab(day_of_week=dow, hour='0', minute='0')
            valid = set((2, 9, 16, 23, 30))
            for x in range(1, 32):
                if x in valid:
                    self.assertTrue(validate(datetime.datetime(2011, 1, x)))
                else:
                    self.assertFalse(validate(datetime.datetime(2011, 1, x)))

    def test_crontab_all_together(self):
        # jan 1, 2011 is a saturday
        # may 1, 2011 is a sunday
        validate = crontab(
            month='1,5',
            day='1,4,7',
            day_of_week='0,6',
            hour='*/4',
            minute='1-5,10-15,50'
        )

        self.assertTrue(validate(datetime.datetime(2011, 5, 1, 4, 11)))
        self.assertTrue(validate(datetime.datetime(2011, 5, 7, 20, 50)))
        self.assertTrue(validate(datetime.datetime(2011, 1, 1, 0, 1)))

        # fails validation on month
        self.assertFalse(validate(datetime.datetime(2011, 6, 4, 4, 11)))

        # fails validation on day
        self.assertFalse(validate(datetime.datetime(2011, 1, 6, 4, 11)))

        # fails validation on day_of_week
        self.assertFalse(validate(datetime.datetime(2011, 1, 4, 4, 11)))

        # fails validation on hour
        self.assertFalse(validate(datetime.datetime(2011, 1, 1, 1, 11)))

        # fails validation on minute
        self.assertFalse(validate(datetime.datetime(2011, 1, 1, 4, 6)))

    def test_invalid_crontabs(self):
        # check invalid configurations are detected and reported
        self.assertRaises(ValueError, crontab, minute='61')
        self.assertRaises(ValueError, crontab, minute='0-61')
        self.assertRaises(ValueError, crontab, day_of_week='*/3')


T = datetime.time

class TestEveryBetween(unittest.TestCase):
    def test_every_between_inside(self):
        fn = every_between(datetime.timedelta(seconds=300), T(1), T(2))

        def assertTS(is_valid, h, m=0, s=0, next_day=False):
            dt = datetime.datetime(2019, 1, 1, h, m, s)
            if next_day:
                dt += datetime.timedelta(days=1)
            self.assertEqual(fn(dt), is_valid)

        # Too early and too late - out-of-bounds.
        assertTS(False, 0, 59, 59)
        assertTS(False, 2, 0, 0)

        assertTS(True, 1)  # Very beginning of valid time window.
        assertTS(False, 1)  # Not valid again for 300 seconds.
        assertTS(False, 1, 1)
        assertTS(False, 1, 4, 59)
        assertTS(True, 1, 5, 30)  # Valid again (as of 1:05:00).
        assertTS(False, 1, 9, 59)  # Not valid again until 1:10:00.
        assertTS(True, 1, 10)
        assertTS(False, 1, 10)  # Not valid again until 1:15:00.

        # Skip an iteration and ensure we don't double-up.
        assertTS(True, 1, 21)  # Valid again at 1:25.
        assertTS(False, 1, 21)
        assertTS(False, 1, 24, 59)
        assertTS(True, 1, 25)

        # We *can*, however, end up with it being called twice in rapid
        # succession under the following circumstances.
        assertTS(True, 1, 49, 59)
        assertTS(False, 1, 49, 59)
        assertTS(True, 1, 50)
        assertTS(False, 1, 50, 1)
        assertTS(True, 1, 59, 58)
        assertTS(False, 1, 59, 59)

        # No longer valid, outside the window.
        assertTS(False, 2)
        assertTS(False, 23)

        # Let's check for tomorrow.
        assertTS(False, 0, 59, 59, True)
        assertTS(True, 1, 8, 0, True)
        assertTS(False, 1, 9, 59, True)
        assertTS(True, 1, 10, 0, True)
        assertTS(False, 2, 0, 0, True)

        # Reset "next" timestamp to test next calculation when within the range
        # of valid timestamps.
        fn._next = None
        assertTS(False, 1, 4, 59)
        assertTS(True, 1, 5, 30)
        assertTS(False, 1, 9, 59)
        assertTS(True, 1, 10, 0)

        # Reset "next" and test behavior right before end ts.
        fn._next = None
        assertTS(False, 1, 55, 1)  # 1s after last valid ts, 1:55:00.
        assertTS(False, 1, 59, 59)
        assertTS(False, 0, 59, 59, True)
        assertTS(True, 1, 0, 0, True)

    def test_every_second(self):
        fn = every_between(datetime.timedelta(seconds=1))
        for h in range(0, 24, 8):
            for m in range(0, 60, 15):
                for s in range(0, 60):
                    dt = datetime.datetime(2000, 1, 1, h, m, s)
                    self.assertTrue(fn(dt))
                    self.assertFalse(fn(dt))

    def test_every_between_invert(self):
        # Valid every 5 minutes between 11PM and 1AM.
        fn = every_between(datetime.timedelta(seconds=300), T(23), T(1))

        def assertTS(is_valid, h, m=0, s=0, next_day=False):
            dt = datetime.datetime(2019, 1, 1, h, m, s)
            if next_day:
                dt += datetime.timedelta(days=1)
            self.assertEqual(fn(dt), is_valid)

        assertTS(False, 22, 59, 59)  # Too early.
        assertTS(False, 1, 0, 0)  # Too late.
        assertTS(False, 1, 0, 0, True)  # Too late.

        assertTS(True, 23)  # Very start of valid time window.
        assertTS(False, 23)  # Not valid again for 300 seconds.
        assertTS(False, 23, 4, 59)
        assertTS(True, 23, 5, 30)
        assertTS(False, 23, 9, 59)  # Not valid again until 23:10:00.
        assertTS(True, 23, 10)
        assertTS(False, 23, 10)  # Not valid again until 23:15:00.

        # Skip an iteration and ensure we don't double-up.
        assertTS(True, 23, 21)  # Valid again at 1:25.
        assertTS(False, 23, 21)
        assertTS(False, 23, 24, 59)
        assertTS(True, 23, 25)

        # We *can*, however, end up with it being called twice in rapid
        # succession under the following circumstances.
        assertTS(True, 23, 49, 59)
        assertTS(False, 23, 49, 59)
        assertTS(True, 23, 50)
        assertTS(False, 23, 50, 1)
        assertTS(True, 23, 59, 58)
        assertTS(False, 23, 59, 59)

        # Let's check for tomorrow.
        assertTS(True, 0, 0, 0, True)
        assertTS(False, 0, 4, 59, True)
        assertTS(True, 0, 5, 0, True)
        assertTS(True, 0, 59, 58, True)
        assertTS(False, 0, 59, 59, True)
        assertTS(False, 1, 0, 0, True)

        # Start of iterations tomorrow evening?
        assertTS(False, 22, 59, 59, True)
        assertTS(True, 23, 15, 30, True)
        assertTS(False, 23, 19, 0, True)
        assertTS(True, 23, 20, 0, True)

        # Reset "next" timestamp to test next calculation when within the range
        # of valid timestamps.
        fn._next = None
        assertTS(False, 23, 4, 59)
        assertTS(True, 23, 5, 30)
        assertTS(False, 23, 9, 59)
        assertTS(True, 23, 10, 0)

        # Reset "next" and test behavior right before end ts.
        fn._next = None
        assertTS(False, 0, 55, 1)  # 1s after last valid ts, 1:55:00.
        assertTS(False, 0, 59, 59)
        assertTS(False, 22, 59, 59)
        assertTS(True, 23, 0, 0)
        assertTS(True, 0, 0, 0, True)

        fn._next = None
        assertTS(False, 0, 5, 1, True)
        assertTS(False, 23, 59, 0)
        assertTS(True, 0, 10, 0, True)
