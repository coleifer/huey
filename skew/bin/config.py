import logging

from skew.backends.dummy import DummyQueue


class BaseConfiguration(object):
    QUEUE = None
    RESULT_STORE = None
    PERIODIC = False
    THREADS = 1

    LOGFILE = '/tmp/skew.log'
    LOGLEVEL = logging.INFO

    BACKOFF = 1.15
    INITIAL_DELAY = .1
    MAX_DELAY = 10
