from functools import partial
import time

from ukt import KT_NONE
from ukt import KyotoTycoon

from huey.api import Huey
from huey.constants import EmptyData
from huey.storage import BaseStorage
from huey.utils import decode


class KyotoTycoonStorage(BaseStorage):
    priority = True

    def __init__(self, name='huey', host='127.0.0.1', port=1978, db=None,
                 timeout=None, max_age=3600, queue_db=None, client=None,
                 blocking=False, result_expire_time=None):
        super(KyotoTycoonStorage, self).__init__(name)
        if client is None:
            client = KyotoTycoon(host, port, timeout, db, serializer=KT_NONE,
                                 max_age=max_age)

        self.blocking = blocking
        self.expire_time = result_expire_time

        self.kt = client
        self._db = db
        self._queue_db = queue_db if queue_db is not None else db

        self.qname = self.name + '.q'
        self.sname = self.name + '.s'

        self.q = self.kt.Queue(self.qname, self._queue_db)
        self.s = self.kt.Schedule(self.sname, self._queue_db)

    def enqueue(self, data, priority=None):
        self.q.add(data, priority)

    def dequeue(self):
        if self.blocking:
            return self.q.bpop(timeout=30)
        else:
            return self.q.pop()

    def queue_size(self):
        return len(self.q)

    def enqueued_items(self, limit=None):
        return self.q.peek(n=limit or -1)

    def flush_queue(self):
        return self.q.clear()

    def convert_ts(self, ts):
        return int(time.mktime(ts.timetuple()))

    def add_to_schedule(self, data, ts):
        self.s.add(data, self.convert_ts(ts))

    def read_schedule(self, ts):
        return self.s.read(self.convert_ts(ts))

    def schedule_size(self):
        return len(self.s)

    def scheduled_items(self, limit=None):
        return self.s.items(limit)

    def flush_schedule(self):
        return self.s.clear()

    def prefix_key(self, key):
        return '%s.%s' % (self.qname, decode(key))

    def put_data(self, key, value, is_result=False):
        xt = self.expire_time if is_result else None
        self.kt.set(self.prefix_key(key), value, self._db, expire_time=xt)

    def peek_data(self, key):
        result = self.kt.get_bytes(self.prefix_key(key), self._db)
        return EmptyData if result is None else result

    def pop_data(self, key):
        if self.expire_time is not None:
            return self.peek_data(key)

        result = self.kt.seize(self.prefix_key(key), self._db)
        return EmptyData if result is None else result

    def delete_data(self, key):
        return self.kt.seize(self.prefix_key(key), self._db) is not None

    def has_data_for_key(self, key):
        return self.kt.exists(self.prefix_key(key), self._db)

    def put_if_empty(self, key, value):
        return self.kt.add(self.prefix_key(key), value, self._db)

    def result_store_size(self):
        return len(self.kt.match_prefix(self.prefix_key(''), db=self._db))

    def result_items(self):
        prefix = self.prefix_key('')
        keys = self.kt.match_prefix(prefix, db=self._db)
        result = self.kt.get_bulk(keys, self._db)

        plen = len(prefix)
        return {key[plen:]: value for key, value in result.items()}

    def flush_results(self):
        prefix = self.prefix_key('')
        keys = self.kt.match_prefix(prefix, db=self._db)
        return self.kt.remove_bulk(keys, self._db)

    def flush_all(self):
        self.flush_queue()
        self.flush_schedule()
        self.flush_results()


class KyotoTycoonHuey(Huey):
    storage_class = KyotoTycoonStorage
