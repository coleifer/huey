from collections import namedtuple
import calendar
import datetime
import sys
import time


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


def reraise_as(new_exc_class):
    exc_class, exc, tb = sys.exc_info()
    raise new_exc_class('%s: %s' % (exc_class.__name__, exc))


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


def normalize_time(eta=None, delay=None, utc=True):
    if not ((delay is None) ^ (eta is None)):
        raise ValueError('Specify either an eta (datetime) or delay (seconds)')
    elif delay:
        method = (utc and datetime.datetime.utcnow or
                  datetime.datetime.now)
        return method() + datetime.timedelta(seconds=delay)
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


if sys.version_info[0] == 2:
    string_type = basestring
    text_type = unicode
    def to_timestamp(dt):
        return time.mktime(dt.timetuple())
else:
    string_type = (bytes, str)
    text_type = str
    def to_timestamp(dt):
        return dt.timestamp()
