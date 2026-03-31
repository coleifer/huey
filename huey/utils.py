from collections import namedtuple
import calendar
import contextlib
import datetime
import errno
import logging
import os
import signal
import sys
import time
import warnings
try:
    import fcntl
except ImportError:
    fcntl = None

try:
    import gevent
except ImportError:
    gevent = None

from huey.exceptions import TaskTimeout


logger = logging.getLogger(__name__)


if sys.version_info < (3, 12):
    utcnow = datetime.datetime.utcnow
else:
    def utcnow():
        return (datetime.datetime
                .now(datetime.timezone.utc)
                .replace(tzinfo=None))


Error = namedtuple('Error', ('metadata',))


class UTC(datetime.tzinfo):
    zero = datetime.timedelta(0)

    def __repr__(self):
        return "<UTC>"
    def utcoffset(self, dt):
        return self.zero
    def tzname(self, dt):
        return "UTC"
    def dst(self, dt):
        return self.zero
_UTC = UTC()


def load_class(s):
    path, klass = s.rsplit('.', 1)
    __import__(path)
    mod = sys.modules[path]
    return getattr(mod, klass)


def is_naive(dt):
    """
    Determines if a given datetime.datetime is naive.
    The concept is defined in Python's docs:
    http://docs.python.org/library/datetime.html#datetime.tzinfo
    Assuming value.tzinfo is either None or a proper datetime.tzinfo,
    value.utcoffset() implements the appropriate logic.
    """
    return dt.utcoffset() is None


def make_naive(dt):
    """
    Makes an aware datetime.datetime naive in local time zone.
    """
    tt = dt.utctimetuple()
    ts = calendar.timegm(tt)
    local_tt = time.localtime(ts)
    return datetime.datetime(*local_tt[:6])


def aware_to_utc(dt):
    """
    Converts an aware datetime.datetime in UTC time zone.
    """
    return dt.astimezone(_UTC).replace(tzinfo=None)


def local_to_utc(dt):
    """
    Converts a naive local datetime.datetime in UTC time zone.
    """
    return datetime.datetime(*time.gmtime(time.mktime(dt.timetuple()))[:6])


def normalize_expire_time(expires, utc=True):
    if isinstance(expires, datetime.datetime):
        return normalize_time(eta=expires, utc=utc)
    return normalize_time(delay=expires, utc=utc)


def normalize_time(eta=None, delay=None, utc=True):
    if not ((delay is None) ^ (eta is None)):
        raise ValueError('Specify either an eta (datetime) or delay (seconds)')
    elif delay:
        method = (utc and utcnow or
                  datetime.datetime.now)
        if not isinstance(delay, datetime.timedelta):
            delay = datetime.timedelta(seconds=delay)
        return method() + delay
    elif eta:
        has_tz = not is_naive(eta)
        if utc:
            if not has_tz:
                eta = local_to_utc(eta)
            else:
                eta = aware_to_utc(eta)
        elif has_tz:
            # Convert TZ-aware into naive localtime.
            eta = make_naive(eta)
        return eta


def encode(s):
    if isinstance(s, bytes):
        return s
    elif isinstance(s, str):
        return s.encode('utf8')
    elif s is not None:
        return str(s).encode('utf8')


def decode(s):
    if isinstance(s, str):
        return s
    elif isinstance(s, bytes):
        return s.decode('utf8')
    elif s is not None:
        return str(s)


class FileLock(object):
    def __init__(self, filename):
        if fcntl is None:
            warnings.warn('FileLock not supported on this platform. Please '
                          'use a different storage implementation.')
        self.filename = filename
        self.fd = None

        dirname = os.path.dirname(filename)
        if not os.path.exists(dirname):
            os.makedirs(dirname)
        elif os.path.exists(self.filename):
            os.unlink(self.filename)

    def acquire(self):
        flags = os.O_CREAT | os.O_TRUNC | os.O_RDWR
        self.fd = os.open(self.filename, flags)
        if fcntl is not None:
            fcntl.flock(self.fd, fcntl.LOCK_EX)

    def release(self):
        if self.fd is not None:
            fd, self.fd = self.fd, None
            if fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()


@contextlib.contextmanager
def noop_context():
    yield

@contextlib.contextmanager
def process_timeout(seconds):
    def _handle_alrm(signum, frame):
        raise TaskTimeout('timeout (%ss)' % seconds)

    orig = signal.signal(signal.SIGALRM, _handle_alrm)
    signal.alarm(int(seconds))
    try:
        yield
    finally:
        signal.alarm(0)  # Cancel any pending alarm.
        signal.signal(signal.SIGALRM, orig)

@contextlib.contextmanager
def thread_timeout(seconds):
    yield

@contextlib.contextmanager
def greenlet_timeout(seconds):
    if gevent is None:
        logger.warning('gevent is required for greenlet-worker timeout')
        yield

    timer = gevent.Timeout(seconds, TaskTimeout('timeout (%ss)' % seconds))
    timer.start()
    try:
        yield
    finally:
        timer.cancel()
