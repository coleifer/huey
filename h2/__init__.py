__author__ = 'Charles Leifer'
__license__ = 'MIT'
__version__ = '2.0.0'

from h2.api import crontab
from h2.api import Huey

try:
    from h2.storage import RedisHuey
except ImportError:
    class RedisHuey(object):
        def __init__(self, *args, **kwargs):
            raise RuntimeError('Error, "redis" is not installed. Install '
                               'using pip: "pip install redis"')
