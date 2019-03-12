import datetime
import logging
import re
import time
import traceback
import uuid

from collections import OrderedDict

from .constants import EmptyData
from .registry import Registry
from .serializer import Serializer
from .utils import Error
from .utils import normalize_time
from .utils import wrap_exception


class Huey(object):
    def __init__(self, name='huey', results=True, store_none=False, utc=True,
                 serializer=None, compression=False, **storage_kwargs):
        self.name = name
        self.results = results
        self.store_none = store_none
        self.utc = utc
        self.serializer = serializer or Serializer()
        if compression:
            self.serializer.compression = True

        self.storage = self.get_storage(**storage_kwargs)
        self._pre_execute = OrderedDict()
        self._post_execute = OrderedDict()
        self._startup = OrderedDict()
        self._registry = Registry()

    def get_storage(self, **kwargs):
        raise NotImplementedError('Storage API not implemented in the base '
                                  'Huey class. Use `RedisHuey` instead.')

    def task(self, retries=0, retry_delay=0, context=False, name=None, **kw):
        def decorator(func):
            return TaskWrapper(
                self,
                func.func if isinstance(func, TaskWrapper) else func,
                retries=retries,
                retry_delay=retry_delay,
                context=context,
                name=name,
                **kw)
        return decorator

    def periodic_task(self, validate_datetime, retries=0, retry_delay=0,
                      context=False, name=None, **kw):
        def decorator(func):
            def method_validate(self, timestamp):
                return validate_datetime(timestamp)

            return TaskWrapper(
                self,
                func.func if isinstance(func, TaskWrapper) else func,
                context=context,
                name=name,
                default_retries=retries,
                default_retry_delay=retry_delay,
                validate_datetime=method_validate,
                task_base=PeriodicTask,
                **kw)

        return decorator

    def serialize_task(self, task):
        message = self._registry.create_message(task)
        return self._serializer.serialize(message)

    def deserialize_task(self, data):
        message = self._serializer.deserialize(data)
        return self._registry.create_task(message)

    def enqueue(self, task):
        self.storage.enqueue(self.serialize_task(task))
        if not self.results:
            return

        if task.on_complete:
            current = task
            results = []
            while current is not None:
                results.append(Result(self, current))
                current = current.on_complete
            return results
        else:
            return Result(self, task)

    def dequeue(self):
        data = self.storage.dequeue()
        if data is not None:
            return self.deserialize_task(data)

    def put(self, key, data):
        return self.storage.put_data(key, self._serializer.serialize(data))

    def put_if_empty(self, key, data):
        return self.storage.put_if_empty(key, self._serializer.serialize(data))

    def get_raw(self, key, peek=False):
        if peek:
            return self.storage.peek_data(key)
        else:
            return self.storage.pop_data(key)

    def get(self, key, peek=False):
        data = self.get_raw(key, peek)
        if data is not EmptyData:
            return self._serializer.deserialize(data)

    def execute(self, task):
        try:
            result = task.execute()
        except Exception as exc:
            if self.results:
                metadata = {
                    'error': repr(exc),
                    'traceback': traceback.format_exc()}
                self.put(task.id, Error(metadata))

            if task.on_error:
                next_task = task.on_error
                next_task.extend_data(exc)
                self.enqueue(next_task)

            raise

        if self.results and not isinstance(task, PeriodicTask):
            if result is not None or self.store_none:
                self.put(task.id, result)

        if task.on_complete:
            next_task = task.on_complete
            next_task.extend_data(result)
            self.enqueue(next_task)

        return result

    def _task_key(self, task_class, key):
        return ':'.join((key, self._registry.task_to_string(task_class)))

    def revoke_all(self, task_class, revoke_until=None, revoke_once=False):
        self.put(self._task_key(task_class, 'rt'), (revoke_until, revoke_once))

    def restore_all(self, task_class):
        return self.get_raw(self._task_key(task_class, 'rt')) is not EmptyData

    def revoke(self, task, revoke_until=None, revoke_once=False):
        self.put(task.revoke_id, (revoke_until, revoke_once))

    def restore(self, task):
        # Return value indicates whether the task was in fact revoked.
        return self.get_raw(task.revoke_id) is not EmptyData

    def revoke_by_id(self, id, revoke_until=None, revoke_once=False):
        return self.revoke(Task(id=id), revoke_until, revoke_once)

    def restore_by_id(self, id):
        return self.restore(Task(id=id))

    def _check_revoked(self, revoke_id, dt=None, peek=True):
        """
        Checks if a task is revoked, returns a 2-tuple indicating:

        1. Is task revoked?
        2. Should task be restored?
        """
        res = self.get(revoke_id, peek=True)
        if res is None:
            return False, False

        revoke_until, revoke_once = res
        if revoke_once:
            # This task *was* revoked for one run, but now it should be
            # restored to normal execution (unless we are just peeking).
            return True, not peek
        elif revoke_until is not None and revoke_until <= dt:
            # Task is no longer revoked and can be restored.
            return False, True
        else:
            # Task is still revoked. Do not restore.
            return True, False

    def is_revoked(self, task, dt=None, peek=True):
        if isclass(task) and issubclass(task, Task):
            revoke_id = self._task_key(task, 'rt')
            is_revoked, can_restore = self._check_revoked(revoke_id, dt, peek)
            if can_restore:
                self.restore_all(task)
            return is_revoked

        if not isinstance(task, Task):
            # Assume we've been given a task ID.
            task = Task(id=task)

        is_revoked, can_restore = self._check_revoked(task.revoke_id, dt, peek)
        if can_restore:
            self.restore(task)
        if not is_revoked:
            is_revoked = self.is_revoked(type(task), dt, peek)

        return is_revoked

    def add_schedule(self, task):
        data = self.serialize_task(task)
        eta = task.eta or datetime.datetime.fromtimestamp(0)
        self.storage.add_to_schedule(data, eta)

    def read_schedule(self, ts):
        return [self.deserialize_task(task)
                for task in self.storage.read_schedule(ts)]

    def read_periodic(self, ts):
        return [task for task in self._registry.periodic_tasks
                if task.validate_datetime(ts)]

    def ready_to_run(self, task, dt=None):
        if dt is None:
            dt = (datetime.datetime.utcnow() if self.utc
                  else datetime.datetime.now())
        return task.eta is None or cmd.eta <= dt

    def pending(self, limit=None):
        return [self.deserialize_task(task)
                for task in self.storage.enqueued_items(limit)]

    def pending_count(self):
        return self.storage.queue_size()

    def scheduled(self, limit=None):
        return [self.deserialize_task(task)
                for task in self.storage.scheduled_items(limit)]

    def scheduled_count(self):
        return self.storage.schedule_size()

    def all_results(self):
        return self.storage.result_items()

    def result_count(self):
        return self.storage.result_store_size()

    def __len__(self):
        return self.pending_count()

    def flush(self):
        self.storage.flush_all()

    def lock_task(self, lock_name):
        """
        Utilize the Storage key/value APIs to implement simple locking.

        This lock is designed to be used to prevent multiple invocations of a
        task from running concurrently. Can be used as either a context-manager
        or as a task decorator. If using as a decorator, place it directly
        above the function declaration.

        If a second invocation occurs and the lock cannot be acquired, then a
        special exception is raised, which is handled by the consumer. The task
        will not be executed and an ``EVENT_LOCKED`` will be emitted. If the
        task is configured to be retried, then it will be retried normally, but
        the failure to acquire the lock is not considered an error.

        Examples:

            @huey.periodic_task(crontab(minute='*/5'))
            @huey.lock_task('reports-lock')
            def generate_report():
                # If a report takes longer than 5 minutes to generate, we do
                # not want to kick off another until the previous invocation
                # has finished.
                run_report()

            @huey.periodic_task(crontab(minute='0'))
            def backup():
                # Generate backup of code
                do_code_backup()

                # Generate database backup. Since this may take longer than an
                # hour, we want to ensure that it is not run concurrently.
                with huey.lock_task('db-backup'):
                    do_db_backup()
        """
        return TaskLock(self, lock_name)

    def flush_locks(self):
        """
        Flush any stale locks (for example, when restarting the consumer).

        :return: List of any stale locks that were cleared.
        """
        flushed = set()
        for lock_key in self._locks:
            if self.get_raw(lock_key) is not EmptyData:
                flushed.add(lock_key.split('.lock.', 1)[-1])
        return flushed

    def result(self, id, blocking=False, timeout=None, backoff=1.15,
               max_delay=1.0, revoke_on_timeout=False, preserve=False):
        """
        Retrieve the results of a task, given the task's ID. This
        method accepts the same parameters and has the same behavior
        as the :py:class:`Result` object.
        """
        task_result = Result(self, Task(id=id))
        return task_result.get(
            blocking=blocking,
            timeout=timeout,
            backoff=backoff,
            max_delay=max_delay,
            revoke_on_timeout=revoke_on_timeout,
            preserve=preserve)


class Task(object):
    default_retries = 0
    default_retry_delay = 0

    def __init__(self, args=None, kwargs=None, id=None, eta=None, retries=None,
                 retry_delay=None, on_complete=None, on_error=None):
        self.name = type(self).__name__
        self.args = () if args is None else args
        self.kwargs = {} if kwargs is None else kwargs
        self.id = id or self.create_id()
        self.revoke_id = 'r:%s' % self.id
        self.eta = eta
        self.retries = retries if retries is not None else self.default_retries
        self.retry_delay = retry_delay if retry_delay is not None else \
                self.default_retry_delay

        self.on_complete = on_complete
        self.on_error = on_error

    @property
    def data(self):
        return (self.args, self.kwargs)

    def __repr__(self):
        rep = '%s.%s: %s' % (self.__module__, self.name, self.id)
        if self.eta:
            rep += ' @%s' % self.eta
        if self.retries:
            rep += ' %s retries' % self.retries
        if self.on_complete:
            rep += ' -> %s' % self.on_complete
        if self.on_error:
            rep += ', on error %s' % self.on_complete
        return rep

    def create_id(self):
        return str(uuid.uuid4())

    def extend_data(self, data):
        if data is None or data == ():
            return

        if isinstance(data, tuple):
            self.args += data
        elif isinstance(data, dict):
            self.kwargs.update(data)
        else:
            self.args = self.args + (data,)

    def then(self, task, *args, **kwargs):
        if self.on_complete:
            self.on_complete.then(task, *args, **kwargs)
        else:
            self.on_complete = task.s(*args, **kwargs)
        return self

    def error(self, task, *args, **kwargs):
        if self.on_error:
            self.on_error.err(task, *args, **kwargs)
        else:
            self.on_error = task.s(*args, **kwargs)
        return self

    def execute(self):
        # Implementation provided by subclass, see: TaskWrapper.create_task().
        raise NotImplementedError

    def __eq__(self, rhs):
        if not isinstance(rhs, Task):
            return False

        return (
            self.id == rhs.id and
            self.eta == rhs.eta and
            type(self) == type(rhs))


class PeriodicTask(Task):
    def validate_datetime(self, timestamp):
        return False


class TaskWrapper(object):
    task_base = Task

    def __init__(self, huey, func, retries=0, retry_delay=0, context=False,
                 name=None, task_base=None, **settings):
        self.huey = huey
        self.func = func
        self.retries = retries
        self.retry_delay = retry_delay
        self.context = context
        self.name = name
        self.settings = settings
        if task_base is not None:
            self.task_base = task_base

        # Dynamically create task class and register with Huey instance.
        self.task_class = self.create_task(func, context, name, **settings)
        self.huey._registry.register(self.task_class)

    def create_task(self, func, context=False, name=None, **settings):
        def execute(self):
            args, kwargs = self.data
            if self.context:
                kwargs['task'] = self
            return func(*args, **kwargs)

        attrs = {
            'context': context,
            'execute': execute,
            '__module__': func.__module__,
            '__doc__': func.__doc__}
        attrs.update(settings)

        if not name:
            name = func.__name__

        return type(name, (self.task_base,), attrs)

    def is_revoked(self, timestamp=None, peek=True):
        return self.huey.is_revoked(self.task_class, timestamp, peek)

    def revoke(self, revoke_until=None, revoke_once=False):
        self.huey.revoke_all(self.task_class, revoke_until, revoke_once)

    def restore(self):
        return self.huey.restore_all(self.task_class)

    def schedule(self, args=None, kwargs=None, eta=None, delay=None, id=None):
        if eta is None and delay is None:
            if isinstance(args, (int, float)):
                delay = args
            elif isinstance(args, datetime.timedelta):
                delay = args.total_seconds()
            elif isinstance(args, datetime.datetime):
                eta = args
            else:
                raise ValueError('schedule() missing required eta= or delay=')
            args = None

        if kwargs is not None and not isinstance(kwargs, dict):
            raise ValueError('schedule() kwargs argument must be a dict.')

        eta = normalize_time(eta, delay, self.utc)
        task = self.task_class(
            (args or (), kwargs or {}),
            id=id,
            eta=eta,
            retries=self.retries,
            retry_delay=self.retry_delay)
        return self.huey.enqueue(task)

    def __call__(self, *args, **kwargs):
        return self.huey.enqueue(self.s(*args, **kwargs))

    def call_local(self, *args, **kwargs):
        return self.func(*args, **kwargs)

    def s(self, *args, **kwargs):
        return self.task_class(args, kwargs, retries=self.retries,
                               retry_delay=self.retry_delay)


class TaskLock(object):
    """
    Utilize the Storage key/value APIs to implement simple locking. For more
    details see :py:meth:`Huey.lock_task`.
    """
    def __init__(self, huey, name):
        self._huey = huey
        self._name = name
        self._key = '%s.lock.%s' % (self._huey.name, self._name)
        self._huey._locks.add(self._key)

    def __call__(self, fn):
        @wraps(fn)
        def inner(*args, **kwargs):
            with self:
                return fn(*args, **kwargs)
        return inner

    def __enter__(self):
        if not self._huey.put_if_empty(self._key, '1'):
            raise TaskLockedException('unable to set lock: %s' % self._name)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._huey.get_raw(self._key)


class Result(object):
    """
    Wrapper around task result data. When a task is executed, an instance of
    ``Result`` is returned to provide access to the return value.

    To retrieve the task's result value, you can simply call the wrapper::

        @huey.task()
        def my_task(a, b):
            return a + b

        result = my_task(1, 2)

        # After a moment, when the consumer has executed the task and put
        # the result in the result storage, we can retrieve the value.
        print result()  # Prints 3

        # If you want to block until the result is ready, you can pass
        # blocking=True. We'll also specify a 4 second timeout so we don't
        # block forever if the consumer goes down:
        result2 = my_task(2, 3)
        print result(blocking=True, timeout=4)
    """
    def __init__(self, huey, task):
        self.huey = huey
        self.task = task
        self._result = EmptyData

    @property
    def id(self):
        return self.task.id

    def __call__(self, *args, **kwargs):
        return self.get(*args, **kwargs)

    def _get(self, preserve=False):
        task_id = self.id
        if self._result is EmptyData:
            res = self.huey.get_raw(task_id, peek=preserve)

            if res is not EmptyData:
                self._result = self.huey._serializer.deserialize(res)
                return self._result
            else:
                return res
        else:
            return self._result

    def get_raw_result(self, blocking=False, timeout=None, backoff=1.15,
                       max_delay=1.0, revoke_on_timeout=False, preserve=False):
        if not blocking:
            res = self._get(preserve)
            if res is not EmptyData:
                return res
        else:
            start = time.time()
            delay = .1
            while self._result is EmptyData:
                if timeout and time.time() - start >= timeout:
                    if revoke_on_timeout:
                        self.revoke()
                    raise DataStoreTimeout
                if delay > max_delay:
                    delay = max_delay
                if self._get(preserve) is EmptyData:
                    time.sleep(delay)
                    delay *= backoff

            return self._result

    def get(self, blocking=False, timeout=None, backoff=1.15, max_delay=1.0,
            revoke_on_timeout=False, preserve=False):
        result = self.get_raw_result(blocking, timeout, backoff, max_delay,
                                     revoke_on_timeout, preserve)
        if result is not None and isinstance(result, Error):
            raise TaskException(result.metadata)
        return result

    def is_revoked(self):
        return self.huey.is_revoked(self.task, peek=True)

    def revoke(self):
        self.huey.revoke(self.task)

    def restore(self):
        return self.huey.restore(self.task)

    def reschedule(self, eta=None, delay=None):
        # Rescheduling works by revoking the currently-scheduled task (nothing
        # is done to check if the task has already run, however). Then the
        # original task's data is used to enqueue a new task with a new task ID
        # and execution_time.
        self.revoke()
        eta = normalize_time(eta, delay, self.huey.utc)
        task = type(self.task)(
            self.task.args,
            self.task.kwargs,
            eta=eta,
            retries=self.task.retries,
            retry_delay=self.task.retry_delay)
        return self.huey.enqueue(task)

    def reset(self):
        self._result = EmptyData


dash_re = re.compile(r'(\d+)-(\d+)')
every_re = re.compile(r'\*\/(\d+)')


def crontab(month='*', day='*', day_of_week='*', hour='*', minute='*'):
    """
    Convert a "crontab"-style set of parameters into a test function that will
    return True when the given datetime matches the parameters set forth in
    the crontab.

    For day-of-week, 0=Sunday and 6=Saturday.

    Acceptable inputs:
    * = every distinct value
    */n = run every "n" times, i.e. hours='*/4' == 0, 4, 8, 12, 16, 20
    m-n = run every time m..n
    m,n = run on m and n
    """
    validation = (
        ('m', month, range(1, 13)),
        ('d', day, range(1, 32)),
        ('w', day_of_week, range(8)), # 0-6, but also 7 for Sunday.
        ('H', hour, range(24)),
        ('M', minute, range(60))
    )
    cron_settings = []

    for (date_str, value, acceptable) in validation:
        settings = set([])

        if isinstance(value, int):
            value = str(value)

        for piece in value.split(','):
            if piece == '*':
                settings.update(acceptable)
                continue

            if piece.isdigit():
                piece = int(piece)
                if piece not in acceptable:
                    raise ValueError('%d is not a valid input' % piece)
                elif date_str == 'w':
                    piece %= 7
                settings.add(piece)

            else:
                dash_match = dash_re.match(piece)
                if dash_match:
                    lhs, rhs = map(int, dash_match.groups())
                    if lhs not in acceptable or rhs not in acceptable:
                        raise ValueError('%s is not a valid input' % piece)
                    elif date_str == 'w':
                        lhs %= 7
                        rhs %= 7
                    settings.update(range(lhs, rhs + 1))
                    continue

                every_match = every_re.match(piece)
                if every_match:
                    if date_str == 'w':
                        raise ValueError('Cannot perform this kind of matching'
                                         ' on day-of-week.')
                    interval = int(every_match.groups()[0])
                    settings.update(acceptable[::interval])

        cron_settings.append(sorted(list(settings)))

    def validate_date(dt):
        _, m, d, H, M, _, w, _, _ = dt.timetuple()

        # fix the weekday to be sunday=0
        w = (w + 1) % 7

        for (date_piece, selection) in zip([m, d, w, H, M], cron_settings):
            if date_piece not in selection:
                return False

        return True

    return validate_date
