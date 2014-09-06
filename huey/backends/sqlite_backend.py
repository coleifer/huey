""" SQLite backend for Huey.

Inspired from a snippet by Thiago Arruda [1]

[1] http://flask.pocoo.org/snippets/88/
"""
import json
import sqlite3
import time
try:
    from thread import get_ident
except ImportError:  # Python 3
    try:
        from threading import get_ident
    except ImportError:
        from _thread import get_ident
    buffer = memoryview

from huey.backends.base import BaseDataStore
from huey.backends.base import BaseEventEmitter
from huey.backends.base import BaseQueue
from huey.backends.base import BaseSchedule
from huey.utils import EmptyData


class _SqliteDatabase(object):
    def __init__(self, location):
        if location == ':memory:':
            raise ValueError("Database location has to be a file path, "
                             "in-memory databases are not supported.")
        self.location = location
        self._conn_cache = {}
        with self.get_connection() as conn:
            # Enable write-ahead logging
            conn.execute("PRAGMA journal_mode=WAL;")
            # Hand over syncing responsibility to OS
            conn.execute("PRAGMA synchronous=OFF;")
            # Store temporary tables and indices in memory
            conn.execute("PRAGMA temp_store=MEMORY;")

    def get_connection(self, immediate=False):
        """ Obtain a sqlite3.Connection instance for the database.

        Connections are cached on a by-thread basis, i.e. every calling thread
        will always get the same Connection object back.
        """
        if immediate:
            return sqlite3.Connection(self.location, timeout=60,
                                      isolation_level="IMMEDIATE")
        id = get_ident()
        if id not in self._conn_cache:
            self._conn_cache[id] = sqlite3.Connection(
                self.location, timeout=60)
        return self._conn_cache[id]


class SqliteQueue(BaseQueue):
    """
    A simple Queue that uses SQLite to store messages
    """
    _create = """
        CREATE TABLE IF NOT EXISTS {0}
        (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          item BLOB
        )
    """
    _count = "SELECT COUNT(*) FROM {0}"
    _append = "INSERT INTO {0} (item) VALUES (?)"
    _get = "SELECT id, item FROM {0} ORDER BY id LIMIT 1"
    _remove_by_value = "DELETE FROM {0} WHERE item = ?"
    _remove_by_id = "DELETE FROM {0} WHERE id = ?"
    _flush = "DELETE FROM {0}"

    def __init__(self, name, location):
        super(SqliteQueue, self).__init__(name, location=location)
        self.queue_name = 'huey_queue_{0}'.format(name)
        self._db = _SqliteDatabase(location)
        with self._db.get_connection() as conn:
            conn.execute(self._create.format(self.queue_name))

    def write(self, data):
        with self._db.get_connection() as conn:
            conn.execute(self._append.format(self.queue_name), (data,))

    def read(self):
        with self._db.get_connection(immediate=True) as conn:
            cursor = conn.execute(self._get.format(self.queue_name))
            try:
                id, data = next(cursor)
            except StopIteration:
                return None
            if id:
                conn.execute(self._remove_by_id.format(self.queue_name), (id,))
                return data

    def remove(self, data):
        with self._db.get_connection() as conn:
            return conn.execute(self._remove_by_value.format(self.queue_name),
                                (data,)).rowcount

    def flush(self):
        with self._db.get_connection() as conn:
            conn.execute(self._flush.format(self.queue_name,))

    def __len__(self):
        with self._db.get_connection() as conn:
            return next(conn.execute(self._count.format(self.queue_name)))[0]


class SqliteSchedule(BaseSchedule):
    _create = """
        CREATE TABLE IF NOT EXISTS {0}
        (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          item BLOB,
          timestamp INTEGER
        )
    """
    _read_items = """
        SELECT item, timestamp FROM {0} WHERE timestamp <= ?
        ORDER BY timestamp
    """
    _delete_items = "DELETE FROM {0} WHERE timestamp <= ?"
    _add_item = "INSERT INTO {0} (item, timestamp) VALUES (?, ?)"
    _flush = "DELETE FROM {0}"

    def __init__(self, name, location):
        super(SqliteSchedule, self).__init__(name, location=location)
        self._db = _SqliteDatabase(location)
        self.name = 'huey_schedule_{0}'.format(name)
        with self._db.get_connection() as conn:
            conn.execute(self._create.format(self.name))

    def convert_ts(self, ts):
        return time.mktime(ts.timetuple())

    def add(self, data, ts):
        with self._db.get_connection() as conn:
            conn.execute(self._add_item.format(self.name),
                         (data, self.convert_ts(ts)))

    def read(self, ts):
        with self._db.get_connection() as conn:
            results = conn.execute(self._read_items.format(self.name),
                                   (self.convert_ts(ts),)).fetchall()
            conn.execute(self._delete_items.format(self.name),
                         (self.convert_ts(ts),))
        return [data for data, _ in results]

    def flush(self):
        with self._db.get_connection() as conn:
            conn.execute(self._flush.format(self.name))


class SqliteDataStore(BaseDataStore):
    _create = """
        CREATE TABLE IF NOT EXISTS {0}
        (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          key TEXT,
          result BLOB
        )
    """
    _put = "INSERT INTO {0} (key, result) VALUES (?, ?)"
    _peek = "SELECT result FROM {0} WHERE key = ?"
    _remove = "DELETE FROM {0} WHERE key = ?"
    _flush = "DELETE FROM {0}"

    def __init__(self, name, location):
        super(SqliteDataStore, self).__init__(name, location=location)
        self._db = _SqliteDatabase(location)
        self.name = 'huey_results_{0}'.format(name)
        with self._db.get_connection() as conn:
            conn.execute(self._create.format(self.name))

    def put(self, key, value):
        with self._db.get_connection() as conn:
            conn.execute(self._remove.format(self.name), (key,))
            conn.execute(self._put.format(self.name), (key, value))

    def peek(self, key):
        with self._db.get_connection() as conn:
            try:
                return next(conn.execute(self._peek.format(self.name),
                                         (key,)))[0]
            except StopIteration:
                return EmptyData

    def get(self, key):
        with self._db.get_connection() as conn:
            try:
                data = next(conn.execute(self._peek.format(self.name),
                                         (key,)))[0]
                conn.execute(self._remove.format(self.name), (key,))
                return data
            except StopIteration:
                return EmptyData

    def flush(self):
        with self._db.get_connection() as conn:
            conn.execute(self._flush.format(self.name))


Components = (SqliteQueue, SqliteDataStore, SqliteSchedule, None)
