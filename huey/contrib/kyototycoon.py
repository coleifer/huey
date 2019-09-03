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
                 timeout=None, max_age=3600, queue_db=0, client=None,
                 blocking=False):
        super(KyotoTycoonStorage, self).__init__(name)
        if client is None:
            client = KyotoTycoon(host, port, timeout, db, serializer=KT_NONE,
                                 max_age=max_age)

        self.blocking = blocking
        self.kt = client
        if db is not None:
            self.kt.set_database(db)

        self.qname = self.name + '.q'
        self.sname = self.name + '.s'

        self.q = self.kt.Queue(self.qname, queue_db)
        self.s = self.kt.Schedule(self.sname, queue_db)

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

    def add_to_schedule(self, data, ts, utc):
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
        self.kt.set(self.prefix_key(key), value)

    def peek_data(self, key):
        result = self.kt.get_bytes(self.prefix_key(key))
        return EmptyData if result is None else result

    def pop_data(self, key):
        result = self.kt.seize(self.prefix_key(key))
        return EmptyData if result is None else result

    def delete_data(self, key):
        return self.kt.seize(self.prefix_key(key)) is not None

    def has_data_for_key(self, key):
        return self.kt.exists(self.prefix_key(key))

    def put_if_empty(self, key, value):
        return self.kt.add(self.prefix_key(key), value)

    def result_store_size(self):
        return len(self.kt.match_prefix(self.prefix_key('')))

    def result_items(self):
        prefix = self.prefix_key('')
        keys = self.kt.match_prefix(prefix)
        result = self.kt.get_bulk(keys)

        plen = len(prefix)
        return {key[plen:]: value for key, value in result.items()}

    def flush_results(self):
        prefix = self.prefix_key('')
        return self.kt.remove_bulk(self.kt.match_prefix(prefix))

    def flush_all(self):
        self.flush_queue()
        self.flush_schedule()
        self.flush_results()


KyotoTycoonHuey = partial(Huey, storage_class=KyotoTycoonStorage)
