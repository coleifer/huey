import base64

from glide_sync import GlideClient
from glide_sync import GlideClientConfiguration
from glide_sync import NodeAddress
from glide_sync import RangeByIndex
from glide_sync import Script
from glide_sync import Transaction

from huey.api import RedisHuey
from huey.constants import EmptyData
from huey.exceptions import ConfigurationError
from huey.storage import RedisStorage
from huey.storage import SCHEDULE_POP_LUA


class ValkeyGlideStorage(RedisStorage):
    def __init__(self, name='huey', blocking=False, read_timeout=1,
                 client=None, client_config=None, host=None, port=None,
                 client_name=None, **client_config_params):
        if sum(1 for p in (client, client_config, host) if p) > 1:
            raise ConfigurationError('Specify only one of the following: '
                                     '"client", "client_config" or "host"')

        if client is not None:
            self.conn = client
        elif client_config is not None:
            self.conn = GlideClient.create(client_config)
        else:
            host = host or '127.0.0.1'
            port = port or 6379
            config = GlideClientConfiguration(
                [NodeAddress(host, port)],
                **client_config_params)
            self.conn = GlideClient.create(config)

        self._pop = Script(SCHEDULE_POP_LUA)

        self.name = self.clean_name(name)
        self.queue_key = 'huey.redis.%s' % self.name
        self.schedule_key = 'huey.schedule.%s' % self.name
        self.result_key = 'huey.results.%s' % self.name
        self.error_key = 'huey.errors.%s' % self.name

        if client_name is not None:
            self.conn.client_setname(client_name)

        if blocking:
            raise ConfigurationError('Valkey glide does not seem to work '
                                     'properly with blocking operations.')
        self.read_timeout = read_timeout

    def enqueue(self, data, priority=None):
        if priority:
            raise NotImplementedError('Task priorities are not supported by '
                                      'this storage.')
        self.conn.lpush(self.queue_key, [data])

    def dequeue(self):
        return self.conn.rpop(self.queue_key)

    def add_to_schedule(self, data, ts):
        data = base64.b64encode(data).decode('utf8')
        self.conn.zadd(self.schedule_key, {data: self.convert_ts(ts)})

    def read_schedule(self, ts):
        unix_ts = self.convert_ts(ts)
        # invoke the redis lua script that will atomically pop off
        # all the tasks older than the given timestamp
        tasks = self.conn.invoke_script(self._pop, keys=[self.schedule_key],
                                        args=[str(unix_ts)])
        return [] if tasks is None else [base64.b64decode(t) for t in tasks]

    def scheduled_items(self, limit=None):
        limit = limit or -1
        tasks = self.conn.zrange(self.schedule_key, RangeByIndex(0, limit))
        return [base64.b64decode(t) for t in tasks]

    def put_data(self, key, value, is_result=False):
        self.conn.hset(self.result_key, {key: value})

    def peek_data(self, key):
        tx = Transaction()
        tx.hexists(self.result_key, key)
        tx.hget(self.result_key, key)
        exists, val = self.conn.exec(tx, False)
        return EmptyData if not exists else val

    def pop_data(self, key):
        tx = Transaction()
        tx.hexists(self.result_key, key)
        tx.hget(self.result_key, key)
        tx.hdel(self.result_key, [key])
        exists, val, n = self.conn.exec(tx, False)
        return EmptyData if not exists else val

    def flush_queue(self):
        self.conn.delete([self.queue_key])

    def flush_schedule(self):
        self.conn.delete([self.schedule_key])

    def flush_results(self):
        self.conn.delete([self.result_key])


class ValkeyGlideHuey(RedisHuey):
    storage_class = ValkeyGlideStorage
