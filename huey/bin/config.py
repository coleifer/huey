import logging

from huey.backends.dummy import DummyQueue


class BaseConfiguration(object):
    QUEUE = None
    RESULT_STORE = None
    TASK_STORE = None
    PERIODIC = False
    THREADS = 1

    LOGFILE = None
    LOGLEVEL = logging.INFO

    BACKOFF = 1.15
    INITIAL_DELAY = .1
    MAX_DELAY = 10
    
    UTC = True
