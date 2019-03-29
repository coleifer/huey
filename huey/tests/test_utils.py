import datetime
import os
import time
import unittest

from huey.utils import UTC
from huey.utils import normalize_time
from huey.utils import reraise_as


class MyException(Exception): pass


class TestReraiseAs(unittest.TestCase):
    def test_wrap_exception(self):
        def raise_keyerror():
            try:
                {}['huey']
            except KeyError as exc:
                reraise_as(MyException)

        self.assertRaises(MyException, raise_keyerror)
        try:
            raise_keyerror()
        except MyException as exc:
            self.assertEqual(str(exc), "KeyError: 'huey'")
        else:
            raise AssertionError('MyException not raised as expected.')


class FakePacific(datetime.tzinfo):
    def utcoffset(self, dt):
        return datetime.timedelta(hours=-8)
    def tzname(self, dt):
        return 'US/Pacific'
    def dst(self, dt):
        return datetime.timedelta(0)


class TestNormalizeTime(unittest.TestCase):
    def setUp(self):
        self._orig_tz = os.environ.get('TZ')
        os.environ['TZ'] = 'US/Pacific'
        time.tzset()

    def tearDown(self):
        del os.environ['TZ']
        if self._orig_tz:
            os.environ['TZ'] = self._orig_tz
        time.tzset()

    def test_normalize_time(self):
        ts_local = datetime.datetime(2000, 1, 1, 12, 0, 0)  # Noon on Jan 1.
        ts_utc = ts_local + datetime.timedelta(hours=8)  # For fake tz.
        ts_inv = ts_local - datetime.timedelta(hours=8)

        # Naive datetime.

        # No conversion is applied, as we treat everything as local time.
        self.assertEqual(normalize_time(ts_local, utc=False), ts_local)

        # So we provided a naive timestamp from the localtime (us/pacific),
        # which is 8 hours behind UTC in January.
        self.assertEqual(normalize_time(ts_local, utc=True), ts_utc)

        # TZ-aware datetime in local timezone (Fake US/Pacific).

        # Here we provide a tz-aware timestamp from the localtime (us/pacific).
        ts = datetime.datetime(2000, 1, 1, 12, 0, 0, tzinfo=FakePacific())

        # No conversion, treated as local time.
        self.assertEqual(normalize_time(ts, utc=False), ts_local)

        # Converted to UTC according to rules from our fake tzinfo, +8 hours.
        self.assertEqual(normalize_time(ts, utc=True), ts_utc)

        # TZ-aware datetime in UTC timezone.

        # Here we provide a tz-aware timestamp using UTC timezone.
        ts = datetime.datetime(2000, 1, 1, 12, 0, 0, tzinfo=UTC())

        # Since we're specifying utc=False, we are dealing with localtimes
        # internally. The timestamp passed in is a tz-aware timestamp in UTC.
        # To convert to a naive localtime, we subtract 8 hours (since UTC is
        # 8 hours ahead of our local time).
        self.assertEqual(normalize_time(ts, utc=False), ts_inv)

        # When utc=True there's no change, since the timestamp is already UTC.
        self.assertEqual(normalize_time(ts, utc=True), ts_local)
