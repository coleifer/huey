import logging
from skew.backends.dummy import DummyQueue, DummyResultStore
from skew.bin.config import BaseConfiguration


class Config(BaseConfiguration):
    QUEUE = DummyQueue('test-queue', None)
    RESULT_STORE = DummyResultStore('test-results', None)
    LOGFILE = None
    LOGLEVEL = logging.INFO
    PERIODIC = True
    MAX_DELAY = 60
    BACKOFF = 2
