__author__ = 'Charles Leifer'
__license__ = 'MIT'
__version__ = '2.0.0'

from h2.api import crontab
from h2.api import Huey

try:
    from h2.storage import RedisHuey
except ImportError:
    from h2.api import _unsupported
    RedisHuey = _unsupported('RedisHuey', 'redis')

try:
    from h2.contrib.sqlitedb import SqliteHuey
except ImportError:
    from h2.api import _unsupported
    SqliteHuey = _unsupported('SqliteHuey', 'peewee')
