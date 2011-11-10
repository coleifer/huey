import logging
from huey.backends.dummy import DummyQueue, DummyDataStore
from huey.bin.config import BaseConfiguration


class Config(BaseConfiguration):
    QUEUE = DummyQueue('test-queue')
    RESULT_STORE = DummyDataStore('test-results')
    LOGFILE = None
    LOGLEVEL = logging.INFO
    PERIODIC = True
    MAX_DELAY = 60
    BACKOFF = 2
