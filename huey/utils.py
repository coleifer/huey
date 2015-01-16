import datetime
import sys
import time


class EmptyData(object):
    pass


def load_class(s):
    path, klass = s.rsplit('.', 1)
    __import__(path)
    mod = sys.modules[path]
    return getattr(mod, klass)

def wrap_exception(new_exc_class):
    exc_class, exc, tb = sys.exc_info()
    raise new_exc_class(exc.message)

def local_to_utc(dt):
    return datetime.datetime(*time.gmtime(time.mktime(dt.timetuple()))[:6])
