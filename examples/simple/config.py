from huey.backends.redis_backend import RedisBlockingQueue, RedisDataStore
from huey.bin.config import BaseConfiguration
from huey.queue import Invoker


queue = RedisBlockingQueue('test-queue', host='localhost', port=6379)
result_store = RedisDataStore('results', host='localhost', port=6379)

invoker = Invoker(queue, result_store=result_store)


class Configuration(BaseConfiguration):
    QUEUE = queue
    RESULT_STORE = result_store
    PERIODIC = True
