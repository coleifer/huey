WORKER_GEVENT = 'gevent'
WORKER_PROCESS = 'process'
WORKER_THREAD = 'thread'

WORKER_ALIAS = {
    'greenlet': WORKER_GEVENT,
    'greenlets': WORKER_GEVENT,
    'processes': WORKER_PROCESS,
    'threads': WORKER_THREAD,
}

VALID_WORKER_TYPES = set((
    WORKER_GEVENT,
    WORKER_PROCESS,
    WORKER_THREAD,
))
