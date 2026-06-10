import datetime
import os
import shutil
import time
import unittest
try:
    import fcntl
except ImportError:
    fcntl = None

from huey.exceptions import TaskTimeout
from huey.utils import FileLock
from huey.utils import UTC
from huey.utils import normalize_expire_time
from huey.utils import normalize_time
from huey.utils import process_timeout
from huey.utils import utcnow


class FakePacific(datetime.tzinfo):
    def utcoffset(self, dt):
        return datetime.timedelta(hours=-8)
    def tzname(self, dt):
        return 'America/Los_Angeles'
    def dst(self, dt):
        return datetime.timedelta(0)


class TestNormalizeTime(unittest.TestCase):
    def setUp(self):
        self._orig_tz = os.environ.get('TZ')
        os.environ['TZ'] = 'America/Los_Angeles'
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

    def test_zero_delay(self):
        # A delay of zero means "now" -- it is not treated as missing.
        for utc in (False, True):
            ref = utcnow() if utc else datetime.datetime.now()
            for delay in (0, datetime.timedelta(seconds=0)):
                eta = normalize_time(delay=delay, utc=utc)
                self.assertTrue(eta is not None)
                self.assertTrue(abs((eta - ref).total_seconds()) < 5)

            # Same for expiration: expires=0 means "expires immediately",
            # not "never expires".
            expires = normalize_expire_time(0, utc=utc)
            self.assertTrue(abs((expires - ref).total_seconds()) < 5)

        # Omitting both eta and delay is still an error.
        self.assertRaises(ValueError, normalize_time)


class TestFileLock(unittest.TestCase):
    lock_file = '/tmp/huey-test-filelock/.lock'

    def tearDown(self):
        dirname = os.path.dirname(self.lock_file)
        if os.path.exists(dirname):
            shutil.rmtree(dirname)

    @unittest.skipIf(fcntl is None, 'requires fcntl')
    def test_construct_preserves_lock_file(self):
        lock1 = FileLock(self.lock_file)
        lock1.acquire()
        try:
            inode = os.stat(self.lock_file).st_ino

            # Constructing a second lock on the same path (e.g. another
            # storage instance starting up) must not unlink the file the
            # first lock is holding.
            FileLock(self.lock_file)
            self.assertTrue(os.path.exists(self.lock_file))
            self.assertEqual(os.stat(self.lock_file).st_ino, inode)
        finally:
            lock1.release()


class TestProcessTimeout(unittest.TestCase):
    def test_subsecond_timeout(self):
        # Sub-second timeouts fire. Previously alarm(int(0.15)) == alarm(0),
        # which cancelled the timer, silently disabling the timeout.
        with self.assertRaises(TaskTimeout):
            with process_timeout(0.15):
                time.sleep(2)

    def test_timeout_cancel(self):
        with process_timeout(0.15):
            pass
        time.sleep(0.2)  # No stray alarm fires after the context exits.
