#
# Minimal huey-like API using gevent and running within the parent process.
#
import datetime
import heapq
import itertools
import logging
import time
from functools import wraps

import gevent
from gevent.event import AsyncResult
from gevent.event import Event
from gevent.pool import Pool

from huey.api import crontab
from huey.utils import normalize_time


logger = logging.getLogger('huey.mini')


class MiniHueyResult(AsyncResult):
    __call__ = AsyncResult.get


class MiniHuey(object):
    def __init__(self, name='huey', interval=1, pool_size=None):
        self.name = name
        self._interval = interval
        now = datetime.datetime.now()
        self._last_check = now.replace(second=0, microsecond=0)
        self._periodic_tasks = []
        self._scheduled_tasks = []
        self._counter = itertools.count()
        self._shutdown = Event()
        self._pool = Pool(pool_size)
        self._run_t = None

    def task(self, validate_func=None):
        if validate_func is not None:
            def periodic_task_wrapper(fn):
                self._periodic_tasks.append((validate_func, fn))
                return fn
            return periodic_task_wrapper

        def decorator(fn):
            @wraps(fn)
            def _inner(*args, **kwargs):
                async_result = MiniHueyResult()
                self._enqueue(fn, args, kwargs, async_result)
                return async_result

            def _schedule(args=None, kwargs=None, delay=None, eta=None):
                eta = normalize_time(eta, delay, utc=False)
                async_result = MiniHueyResult()
                heapq.heappush(self._scheduled_tasks,
                               (eta, next(self._counter), fn, args, kwargs,
                                async_result))
                return async_result

            _inner.schedule = _schedule
            return _inner

        return decorator

    def periodic_task(self, validate_func):
        def decorator(fn):
            return self.task(validate_func)(fn)
        return decorator

    def start(self):
        if self._run_t is not None:
            raise Exception('Task runner is already running.')
        self._shutdown.clear()
        self._run_t = gevent.spawn(self._run)

    def stop(self):
        if self._run_t is None:
            raise Exception('Task runner does not appear to have started.')
        self._shutdown.set()
        logger.info('shutdown requested.')
        self._run_t.join()
        self._run_t = None

    def _enqueue(self, fn, args=None, kwargs=None, async_result=None):
        logger.info('enqueueing %s', fn.__name__)
        self._pool.spawn(self._execute, fn, args, kwargs, async_result)

    def _execute(self, fn, args, kwargs, async_result):
        args = args or ()
        kwargs = kwargs or {}
        start = time.monotonic()
        try:
            ret = fn(*args, **kwargs)
        except Exception as exc:
            logger.exception('task %s failed', fn.__name__)
            if async_result is not None:
                async_result.set_exception(exc)
            return

        duration = time.monotonic() - start
        if async_result is not None:
            async_result.set(ret)
        logger.info('executed %s in %0.3fs', fn.__name__, duration)

    def _run(self):
        logger.info('task runner started.')
        while not self._shutdown.is_set():
            start = time.monotonic()
            try:
                now = datetime.datetime.now()
                minute = now.replace(second=0, microsecond=0)
                if minute > self._last_check:
                    logger.debug('checking periodic task schedule')
                    self._last_check = minute
                    for validate_func, fn in self._periodic_tasks:
                        if validate_func(now):
                            self._enqueue(fn)

                if self._scheduled_tasks:
                    logger.debug('checking scheduled tasks')
                    # The 0-th item of a heap is always the smallest.
                    while self._scheduled_tasks and \
                          self._scheduled_tasks[0][0] <= now:

                        eta, _, fn, args, kwargs, async_result = (
                            heapq.heappop(self._scheduled_tasks))
                        self._enqueue(fn, args, kwargs, async_result)
            except Exception:
                logger.exception('error in task scheduler.')

            remaining = self._interval - (time.monotonic() - start)
            if remaining > 0:
                self._shutdown.wait(remaining)
        logger.info('exiting task runner')
