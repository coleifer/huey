import logging

from django.apps import AppConfig
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

import peewee


logger = logging.getLogger('huey')


def stats_database():
    options = dict(getattr(settings, 'HUEY_STATS', None) or {})
    db = options.pop('database', None)
    if isinstance(db, peewee.Database):
        return db, options
    elif isinstance(db, str):
        from playhouse.db_url import connect
        return connect(db), options

    conn = settings.DATABASES['default']
    engine = conn['ENGINE'].rsplit('.', 1)[-1]
    if engine == 'sqlite3':
        return peewee.SqliteDatabase(str(conn['NAME'])), options

    kwargs = {'user': conn.get('USER'), 'password': conn.get('PASSWORD'),
              'host': conn.get('HOST'), 'port': conn.get('PORT')}
    kwargs = {k: v for k, v in kwargs.items() if v}
    if 'port' in kwargs:
        kwargs['port'] = int(kwargs['port'])
    if engine in ('postgresql', 'postgresql_psycopg2', 'postgis'):
        return peewee.PostgresqlDatabase(conn['NAME'], **kwargs), options
    elif engine == 'mysql':
        return peewee.MySQLDatabase(conn['NAME'], **kwargs), options
    raise ImproperlyConfigured(
        'huey stats cannot map DATABASES["default"] (%s) to a peewee '
        'database. Set HUEY_STATS["database"] to a peewee Database instance '
        'or db-url string.' % conn['ENGINE'])


class HueyStatsConfig(AppConfig):
    name = 'huey.contrib.djhuey.stats'
    label = 'hueystats'
    verbose_name = 'Huey'
    default_auto_field = 'django.db.models.AutoField'

    def ready(self):
        from huey.contrib.djhuey import HUEY
        from huey.contrib.stats import enable_stats
        db, options = stats_database()
        try:
            enable_stats(HUEY, db, **options)
        except Exception:
            logger.exception('huey stats recorder failed to start.')
