import os
import sys
import time
import datetime

class EmptyData(object):
    pass


def load_class(s):
    ldir = os.getcwd()
    if ldir not in sys.path:
        sys.path.insert(0, ldir)
    path, klass = s.rsplit('.', 1)
    __import__(path)
    mod = sys.modules[path]
    return getattr(mod, klass)

def wrap_exception(exc_class):
    exc_class, exc, tb = sys.exc_info()
    raise exc_class(exc.message)

def local_to_utc(dt):
    return datetime.datetime(*time.gmtime(time.mktime(dt.timetuple()))[:6])
