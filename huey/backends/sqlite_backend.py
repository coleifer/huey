""" SQLite backend for Huey.

Inspired from a snippet by Thiago Arruda [1]

[1] http://flask.pocoo.org/snippets/88/
"""
import sqlite3
import time
from cPickle import dumps, loads
from thread import get_ident

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

    def get_connection(self):
        """ Obtain a sqlite3.Connection instance for the database.

        Connections are cached on a by-thread basis, i.e. every calling thread
        will always get the same Connection object back.
        """
        id = get_ident()
        if id not in self._conn_cache:
            self._conn_cache[id] = sqlite3.Connection(
                self.location, timeout=60)
        return self._conn_cache[id]


class SqliteQueue(BaseQueue):
    """
    A simple Queue that uses SQLite to store messages
    """
    _create = (
        "CREATE TABLE IF NOT EXISTS {0} "
        "("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  item BLOB"
        ")"
    )
    _count = "SELECT COUNT(*) FROM {0}"
    _append = "INSERT INTO {0} (item) VALUES (?)"
    _get = (
        "SELECT id, item FROM {0} "
        "ORDER BY id LIMIT 1"
    )
    _write_lock = "BEGIN IMMEDIATE"
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
        obj_buffer = buffer(dumps(data, 2))
        with self._db.get_connection() as conn:
            conn.execute(self._append.format(self.queue_name), (obj_buffer,))

    def read(self):
        with self._db.get_connection() as conn:
            # NOTE: We issue a write lock so we can make sure that the
            #       database stays consistent for the duration of  our
            #       transaction
            conn.execute(self._write_lock)
            cursor = conn.execute(self._get.format(self.queue_name))
            try:
                id, obj_buffer = cursor.next()
            except StopIteration:
                return None
            if id:
                conn.execute(self._remove_by_id.format(self.queue_name), (id,))
                return loads(str(obj_buffer))

    def remove(self, data):
        obj_buffer = buffer(dumps(data, 2))
        with self._db.get_connection() as conn:
            return conn.execute(self._remove_by_value.format(self.queue_name),
                                (obj_buffer,)).rowcount

    def flush(self):
        with self._db.get_connection() as conn:
            conn.execute(self._flush.format(self.queue_name,))

    def __len__(self):
        with self._db.get_connection() as conn:
            return conn.execute(self._count.format(self.queue_name)).next()[0]


class SqliteBlockingQueue(SqliteQueue):
    """
    Use a simulated blocking right pop, should behave similarly to
    RedisBlockingQueue.
    """
    blocking = True

    def read(self):
        wait = 0.1  # Initial wait period
        max_wait = 2  # Maximum wait duration
        tries = 0
        with self._db.get_connection() as conn:
            id = None
            while True:
                conn.execute(self._write_lock)
                cursor = conn.execute(self._get
                                      .format(self.queue_name))
                try:
                    id, obj_buffer = cursor.next()
                    break
                except StopIteration:
                    conn.commit()  # unlock the database
                    tries += 1
                    time.sleep(wait)
                    # Increase the wait period
                    wait = min(max_wait, tries/10 + wait)
            if id:
                conn.execute(self._remove_by_id.format(self.queue_name), (id,))
                return loads(str(obj_buffer))
        return None


class SqliteSchedule(BaseSchedule):
    _create = (
        "CREATE TABLE IF NOT EXISTS {0} "
        "("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  item BLOB,"
        "  timestamp INTEGER"
        ")"
    )
    _read_items = (
        "SELECT item, timestamp FROM {0} WHERE timestamp <= ? "
        "ORDER BY timestamp"
    )
    _delete_items = (
        "DELETE FROM {0} WHERE timestamp <= ?"
    )
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
        obj_buffer = buffer(dumps(data, 2))
        with self._db.get_connection() as conn:
            conn.execute(self._add_item.format(self.name),
                         (obj_buffer, self.convert_ts(ts)))

    def read(self, ts):
        with self._db.get_connection() as conn:
            results = conn.execute(self._read_items.format(self.name),
                                   (self.convert_ts(ts),)).fetchall()
            conn.execute(self._delete_items.format(self.name),
                         (self.convert_ts(ts),))
        return [loads(str(obj_buffer)) for obj_buffer, _ in results]

    def flush(self):
        with self._db.get_connection() as conn:
            conn.execute(self._flush.format(self.name))


class SqliteDataStore(BaseDataStore):
    _create = (
        "CREATE TABLE IF NOT EXISTS {0} "
        "("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  key TEXT,"
        "  result BLOB"
        ")"
    )
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
        obj_buffer = buffer(dumps(value, 2))
        with self._db.get_connection() as conn:
            conn.execute(self._remove.format(self.name), (key,))
            conn.execute(self._put.format(self.name), (key, obj_buffer))

    def peek(self, key):
        with self._db.get_connection() as conn:
            try:
                obj_buffer = conn.execute(self._peek.format(self.name),
                                          (key,)).next()[0]
            except StopIteration:
                return EmptyData
        return loads(str(obj_buffer))

    def get(self, key):
        with self._db.get_connection() as conn:
            try:
                obj_buffer = conn.execute(self._peek.format(self.name),
                                          (key,)).next()[0]
            except StopIteration:
                return EmptyData
            conn.execute(self._remove.format(self.name), (key,))
        return loads(str(obj_buffer))

    def flush(self):
        with self._db.get_connection() as conn:
            conn.execute(self._flush.format(self.name))


class SqliteEventEmitter(BaseEventEmitter):
    _create = (
        "CREATE TABLE IF NOT EXISTS {0} "
        "("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  message TEXT"
        ")"
    )
    _purge_old = (
        "DELETE FROM {0} WHERE id IN "
        "(SELECT id FROM {0} ORDER BY id ASC LIMIT ?)"
    )
    _emit = "INSERT INTO {0} (message) VALUES (?)"
    _get = (
        "SELECT id, message FROM {0} "
        "ORDER BY id DESC LIMIT ?"
    )
    _count = "SELECT COUNT(*) FROM {0}"

    def __init__(self, channel, location, size=500):
        super(SqliteEventEmitter, self).__init__(channel, location=location)
        self._size = size
        self._db = _SqliteDatabase(location)
        self.name = 'huey_events_{0}'.format(channel)
        with self._db.get_connection() as conn:
            conn.execute(self._create.format(self.name))

    def emit(self, message):
        with self._db.get_connection() as conn:
            conn.execute(self._emit.format(self.name), (message,))
            size = conn.execute(self._count.format(self.name)).next()[0]
            if size > self._size:
                conn.execute(self._purge_old.format(self.name),
                             (self._size-200,))

    def read(self):
        wait = 0.1  # Initial wait period
        max_wait = 2  # Maximum wait duration
        tries = 0
        with self._db.get_connection() as conn:
            rv = next(conn.execute(self._get.format(self.name), (1,)))
            last_id = rv[0]
            print last_id
            while True:
                recent_id = next(conn.execute(self._get
                                              .format(self.name), (1,)))[0]
                print recent_id
                if recent_id != last_id:
                    cursor = conn.execute(
                        self._get.format(self.name), (recent_id-last_id,))
                    return (msg for id, msg in cursor)
                else:
                    tries += 1
                    time.sleep(wait)
                    # Increase the wait period
                    wait = min(max_wait, tries/10 + wait)


Components = (SqliteBlockingQueue, SqliteDataStore, SqliteSchedule,
              SqliteEventEmitter)
