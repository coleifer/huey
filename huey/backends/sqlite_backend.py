import sqlite3
from huey.backends.base import BaseQueue, BaseDataStore
from huey.utils import EmptyData


class SqliteQueue(BaseQueue):
    """
    A simple Queue that uses the sqlite in memory to store messages
    """
    def __init__(self, name, **connection):
        """
        QUEUE_CONNECTION is not needed for this backend
        """
        super(SqliteQueue, self).__init__(name, **connection)

        self.queue_name = 'huey.sqlite.{0}'.format(name)
        self.conn = sqlite3.connect(':memory:')
        c = self.conn.cursor()
        # create the needed table
        command = """
create TABLE '{0}' (id INTEGER PRIMARY KEY, data text) """.format(
            self.queue_name)
        c.execute(command)
        self.conn.commit()

    def write(self, data):
        c = self.conn.cursor()
        c.execute(
            "INSERT INTO '{0}' (data) VALUES ('{1}')".format(
                self.queue_name, data)
            )

    def read(self):
        c = self.conn.cursor()
        c.execute(
            "SELECT * FROM '{0}' WHERE 1=1".format(self.queue_name))
        row = c.fetchone()
        try:
            c.execute(
                "DELETE FROM '{0}' WHERE id='{1}'".format(
                    self.queue_name, row[0]))
        except TypeError, e:
            #if the table is empty, there is nothing to delete
            print e
            pass
        if row is None:
            return None
        return row[1]

    def remove(self, data):
        c = self.conn.cursor()
        c.execute(
            "SELECT * FROM '{0}' WHERE data='{1}'".format(
                self.queue_name, data)
            )
        rows = c.fetchall()
        for row in rows:
            c.execute(
                "DELETE FROM '{0}' WHERE id='{1}'".format(
                    self.queue_name, row[0]))
        return len(rows)

    def __len__(self):
        c = self.conn.cursor()
        c.execute("SELECT COUNT(*) FROM '{0}' ".format(self.queue_name))
        return c.fetchone()[0]


class SqliteDataStore(BaseDataStore):
    def __init__(self, name, **connection):
        """
        RESULT_STORE_CONNECTION = {
            'host': 'localhost',
            'port': 6379,
            'db': 0,
        }
        """
        super(SqliteDataStore, self).__init__(name, **connection)

        self.storage_name = 'huey.sqlite.results.{0}'.format(name)
        self.conn = sqlite3.connect(':memory:')
        c = self.conn.cursor()
        # create the needed table
        command = """
create TABLE '{0}' (key text PRIMARY KEY, value text) """.format(
            self.storage_name)
        c.execute(command)
        self.conn.commit()

    def put(self, key, value):
        c = self.conn.cursor()
        c.execute(
            "INSERT OR REPLACE INTO '{0}' (key, value) VALUES ('{1}', '{2}')".format(
                self.storage_name, key, value)
            )

    def peek(self, key):
        c = self.conn.cursor()
        c.execute(
            "SELECT * FROM '{0}' WHERE key='{1}'".format(
                self.storage_name, key))
        row = c.fetchone()
        if row is not None:
            return row[-1]
        else:
            return EmptyData
        if self.conn.hexists(self.storage_name, key):
            return self.conn.hget(self.storage_name, key)
        return EmptyData

    def get(self, key):
        c = self.conn.cursor()
        val = self.peek(key)
        if val is not EmptyData:
            c.execute(
                "DELETE FROM '{0}' WHERE key='{1}'".format(
                    self.storage_name, key))
        return val

    def flush(self):
        c = self.conn.cursor()
        c.execute(
            "DELETE FROM '{0}' WHERE 1=1".format(
                self.storage_name))
        self.conn.delete(self.storage_name)
