__author__ = 'Charles Leifer'
__license__ = 'MIT'
__version__ = '2.0.0'

from huey.api import crontab
from huey.api import Huey

try:
    from huey.storage import RedisHuey
except ImportError:
    from huey.api import _unsupported
    RedisHuey = _unsupported('RedisHuey', 'redis')

try:
    from huey.contrib.sqlitedb import SqliteHuey
except ImportError:
    from huey.api import _unsupported
    SqliteHuey = _unsupported('SqliteHuey', 'peewee')
