from collections import namedtuple
import datetime
import sys
import time


Error = namedtuple('Error', ('metadata',))


class UTC(datetime.tzinfo):
    """
    UTC implementation taken from Python's docs.
    Used only when pytz isn't available.
    """

    def __repr__(self):
        return "<UTC>"

    def utcoffset(self, dt):
        return datetime.timedelta(0)

    def tzname(self, dt):
        return "UTC"

    def dst(self, dt):
        return datetime.timedelta(0)


def is_naive(dt):
    """
    Determines if a given datetime.datetime is naive.
    The concept is defined in Python's docs:
    http://docs.python.org/library/datetime.html#datetime.tzinfo
    Assuming value.tzinfo is either None or a proper datetime.tzinfo,
    value.utcoffset() implements the appropriate logic.
    """
    return dt.utcoffset() is None


def is_aware(dt):
    return not is_naive(dt)


def load_class(s):
    path, klass = s.rsplit('.', 1)
    __import__(path)
    mod = sys.modules[path]
    return getattr(mod, klass)


def reraise_as(new_exc_class):
    exc_class, exc, tb = sys.exc_info()
    raise new_exc_class('%s: %s' % (exc_class.__name__, exc))


def make_naive(dt):
    """
    Makes an aware datetime.datetime naive in its time zone.
    """
    return dt.replace(tzinfo=None)


def aware_to_utc(dt):
    """
    Converts an aware datetime.datetime in UTC time zone.
    """
    dt = dt.astimezone(UTC())
    assert not is_naive(dt), 'Must be a time zone aware datetime'
    return make_naive(dt)


def local_to_utc(dt):
    """
    Converts a naive local datetime.datetime in UTC time zone.
    """
    return datetime.datetime(*time.gmtime(time.mktime(dt.timetuple()))[:6])


def normalize_time(eta=None, delay=None, utc=True):
    if bool(delay) ^ bool(eta):
        raise ValueError('Specify either an eta (datetime) or delay (seconds)')
    elif delay:
        method = (utc and datetime.datetime.utcnow or
                  datetime.datetime.now)
        return method() + datetime.timedelta(seconds=delay)
    elif eta:
        if is_naive(eta) and utc:
            # Convert naive local datetime into naive UTC datetime.
            eta = local_to_utc(eta)
        elif is_aware(eta) and utc:
            # Convert tz-aware datetime into naive UTC datetime.
            eta = aware_to_utc(eta)
        elif is_aware(eta) and not utc:
            eta = make_naive(eta)
        return eta
