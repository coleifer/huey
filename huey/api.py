import datetime
import json
import pickle
import re
import time
import traceback
import uuid
from collections import OrderedDict
from functools import wraps
from inspect import isclass

from huey.constants import EmptyData
from huey.consumer import Consumer
from huey.exceptions import DataStoreGetException
from huey.exceptions import DataStorePutException
from huey.exceptions import DataStoreTimeout
from huey.exceptions import QueueException
from huey.exceptions import QueueReadException
from huey.exceptions import QueueRemoveException
from huey.exceptions import QueueWriteException
from huey.exceptions import ScheduleAddException
from huey.exceptions import ScheduleReadException
from huey.exceptions import TaskException
from huey.exceptions import TaskLockedException
from huey.registry import registry
from huey.registry import TaskRegistry
from huey.utils import Error
from huey.utils import aware_to_utc
from huey.utils import is_aware
from huey.utils import is_naive
from huey.utils import local_to_utc
from huey.utils import make_naive
from huey.utils import wrap_exception


class Huey(object):
    """
    Huey executes tasks by exposing function decorators that cause the function
    call to be enqueued for execution by the consumer.

    Typically your application will only need one Huey instance, but you can
    have as many as you like -- the only caveat is that one consumer process
    must be executed for each Huey instance.

    :param name: a name for the task queue.
    :param bool result_store: whether to store task results.
    :param bool events: whether to enable consumer-sent events.
    :param store_none: Flag to indicate whether tasks that return ``None``
        should store their results in the result store.
    :param always_eager: Useful for testing, this will execute all tasks
        immediately, without enqueueing them.
    :param store_errors: Flag to indicate whether task errors should be stored.
    :param global_registry: Use a global registry for tasks.

    Example usage::

        from huey import RedisHuey

        # Create a huey instance and disable consumer-sent events.
        huey = RedisHuey('my-app', events=False)

        @huey.task()
        def slow_function(some_arg):
            # ... do something ...
            return some_arg

        @huey.periodic_task(crontab(minute='0', hour='3'))
        def backup():
            # do a backup every day at 3am
            return
    """
    def __init__(self, name='huey', result_store=True, events=True,
                 store_none=False, always_eager=False, store_errors=True,
                 blocking=False, global_registry=True, **storage_kwargs):
        self.name = name
        self.result_store = result_store
        self.events = events
        self.store_none = store_none
        self.always_eager = always_eager
        self.store_errors = store_errors
        self.blocking = blocking
        self.storage = self.get_storage(**storage_kwargs)
        self.pre_execute_hooks = OrderedDict()
        self.post_execute_hooks = OrderedDict()
        self.startup_hooks = OrderedDict()
        self._locks = set()
        if global_registry:
            self.registry = registry
        else:
            self.registry = TaskRegistry()

    def get_storage(self, **kwargs):
        raise NotImplementedError('Storage API not implemented in the base '
                                  'Huey class. Use `RedisHuey` instead.')

    def create_consumer(self, **config):
        return Consumer(self, **config)

    def _normalize_execute_time(self, eta=None, delay=None, convert_utc=True):
        if delay and eta:
            raise ValueError('Both a delay and an eta cannot be '
                             'specified at the same time')
        elif delay:
            method = (convert_utc and datetime.datetime.utcnow or
                      datetime.datetime.now)
            return method() + datetime.timedelta(seconds=delay)
        elif eta:
            if is_naive(eta) and convert_utc:
                eta = local_to_utc(eta)
            elif is_aware(eta) and convert_utc:
                eta = aware_to_utc(eta)
            elif is_aware(eta) and not convert_utc:
                eta = make_naive(eta)
            return eta

    def task(self, retries=0, retry_delay=0, retries_as_argument=False,
             include_task=False, name=None, **task_settings):
        def decorator(func):
            """
            Decorator to execute a function out-of-band via the consumer.
            """
            return TaskWrapper(
                self,
                func.func if isinstance(func, TaskWrapper) else func,
                retries=retries,
                retry_delay=retry_delay,
                retries_as_argument=retries_as_argument,
                include_task=include_task,
                name=name,
                **task_settings)
        return decorator

    # We specify retries and retry_delay as 0 because they become the default
    # values as class attributes on the derived PeriodicQueueTask instance.
    # Since the values the class is instantiated with will always be `None`,
    # we want the fallback behavior to be 0 by default.
    def periodic_task(self, validate_datetime, name=None, retries=0,
                      retry_delay=0, **task_settings):
        """
        Decorator to execute a function on a specific schedule.
        """
        def decorator(func):
            def method_validate(self, dt):
                return validate_datetime(dt)

            return TaskWrapper(
                self,
                func.func if isinstance(func, TaskWrapper) else func,
                name=name,
                task_base=PeriodicQueueTask,
                default_retries=retries,
                default_retry_delay=retry_delay,
                validate_datetime=method_validate,
                **task_settings)

        return decorator

    def register_pre_execute(self, name, fn):
        """
        Register a pre-execute hook. The callback will be executed before the
        execution of all tasks. Execution of the task can be cancelled by
        raising a :py:class:`CancelExecution` exception. Uncaught exceptions
        will be logged but will not cause the task itself to be cancelled.

        The callback function should accept a single task instance, the return
        value is ignored.

        :param name: Name for the hook.
        :param fn: Callback function that accepts task to be executed.
        """
        self.pre_execute_hooks[name] = fn

    def unregister_pre_execute(self, name):
        del self.pre_execute_hooks[name]

    def pre_execute(self, name=None):
        """
        Decorator for registering a pre-execute hook.
        """
        def decorator(fn):
            self.register_pre_execute(name or fn.__name__, fn)
            return fn
        return decorator

    def register_post_execute(self, name, fn):
        """
        Register a post-execute hook. The callback will be executed after the
        execution of all tasks. Uncaught exceptions will be logged but will
        have no other effect on the overall operation of the consumer.

        The callback function should accept:

        * a task instance
        * the return value from the execution of the task (which may be None)
        * any exception that was raised during the execution of the task (which
          will be None for tasks that executed normally).

        The return value of the callback itself is ignored.

        :param name: Name for the hook.
        :param fn: Callback function that accepts task that was executed and
                   the tasks return value (or None).
        """
        self.post_execute_hooks[name] = fn

    def unregister_post_execute(self, name):
        del self.post_execute_hooks[name]

    def post_execute(self, name=None):
        """
        Decorator for registering a post-execute hook.
        """
        def decorator(fn):
            self.register_post_execute(name or fn.__name__, fn)
            return fn
        return decorator

    def register_startup(self, name, fn):
        """
        Register a startup hook. The callback will be executed whenever a
        worker comes online. Uncaught exceptions will be logged but will
        have no other effect on the overall operation of the worker.

        The callback function must not accept any parameters.

        This API is provided to simplify setting up global resources that, for
        whatever reason, should not be created as import-time side-effects. For
        example, your tasks need to write data into a Postgres database. If you
        create the connection at import-time, before the worker processes are
        spawned, you'll likely run into errors when attempting to use the
        connection from the child (worker) processes. To avoid this problem,
        you can register a startup hook which is executed by the worker process
        as part of its initialization.

        :param name: Name for the hook.
        :param fn: Callback function.
        """
        self.startup_hooks[name] = fn

    def unregister_startup(self, name):
        del self.startup_hooks[name]

    def on_startup(self, name=None):
        """
        Decorator for registering a startup hook.
        """
        def decorator(fn):
            self.register_startup(name or fn.__name__, fn)
            return fn
        return decorator

    def _wrapped_operation(exc_class):
        def decorator(fn):
            def inner(*args, **kwargs):
                try:
                    return fn(*args, **kwargs)
                except (KeyboardInterrupt, RuntimeError):
                    raise
                except:
                    wrap_exception(exc_class)
            return inner
        return decorator

    @_wrapped_operation(QueueWriteException)
    def _enqueue(self, msg):
        self.storage.enqueue(msg)

    @_wrapped_operation(QueueReadException)
    def _dequeue(self):
        return self.storage.dequeue()

    @_wrapped_operation(QueueRemoveException)
    def _unqueue(self, msg):
        return self.queue.unqueue(msg)

    @_wrapped_operation(DataStoreGetException)
    def _get_data(self, key, peek=False):
        if peek:
            return self.storage.peek_data(key)
        else:
            return self.storage.pop_data(key)

    @_wrapped_operation(DataStorePutException)
    def _put_data(self, key, value):
        return self.storage.put_data(key, value)

    @_wrapped_operation(DataStorePutException)
    def _put_if_empty(self, key, value):
        return self.storage.put_if_empty(key, value)

    @_wrapped_operation(DataStorePutException)
    def _put_error(self, metadata):
        self.storage.put_error(metadata)

    @_wrapped_operation(DataStoreGetException)
    def _get_errors(self, limit=None, offset=0):
        return self.storage.get_errors(limit=limit, offset=offset)

    @_wrapped_operation(ScheduleAddException)
    def _add_to_schedule(self, data, ts):
        self.storage.add_to_schedule(data, ts)

    @_wrapped_operation(ScheduleReadException)
    def _read_schedule(self, ts):
        return self.storage.read_schedule(ts)

    def emit(self, message):
        try:
            self.storage.emit(message)
        except:
            # Events always fail silently since they are treated as a non-
            # critical component.
            pass

    def _execute_always_eager(self, task):
        accum = []
        failure_exc = None
        while task is not None:
            for name, callback in self.pre_execute_hooks.items():
                callback(task)
            try:
                result = task.execute()
            except Exception as exc:
                result = None
                failure_exc = task_exc = exc
            else:
                task_exc = None
            accum.append(result)
            for name, callback in self.post_execute_hooks.items():
                callback(task, result, task_exc)
            if task.on_complete:
                task = task.on_complete
                task.extend_data(result)
            else:
                task = None

        if failure_exc is not None:
            raise failure_exc

        return accum[0] if len(accum) == 1 else accum

    def enqueue(self, task):
        if self.always_eager:
            return self._execute_always_eager(task)

        self._enqueue(self.registry.get_message_for_task(task))
        if not self.result_store:
            return

        if task.on_complete:
            q = [task]
            result_wrappers = []
            while q:
                current = q.pop()
                result_wrappers.append(TaskResultWrapper(self, current))
                if current.on_complete:
                    q.append(current.on_complete)
            return result_wrappers
        else:
            return TaskResultWrapper(self, task)

    def dequeue(self):
        message = self._dequeue()
        if message:
            return self.registry.get_task_for_message(message)

    def put(self, key, value):
        return self._put_data(key,
                              pickle.dumps(value, pickle.HIGHEST_PROTOCOL))

    def get(self, key, peek=False):
        data = self._get_data(key, peek=peek)
        if data is EmptyData:
            return
        else:
            return pickle.loads(data)

    def put_error(self, metadata):
        return self._put_error(pickle.dumps(metadata))

    def _format_time(self, dt):
        if dt is None:
            return None
        return time.mktime(dt.timetuple())

    def _get_task_metadata(self, task, error=False, include_data=False):
        metadata = {
            'id': task.task_id,
            'task': type(task).__name__,
            'retries': task.retries,
            'retry_delay': task.retry_delay,
            'execute_time': self._format_time(task.execute_time)}
        if include_data and not isinstance(task, PeriodicQueueTask):
            targs, tkwargs = task.get_data()
            if tkwargs.get("task") and isinstance(tkwargs["task"], QueueTask):
                del(tkwargs['task'])
            metadata['data'] = (targs, tkwargs)

        return metadata

    def emit_status(self, status, error=False, **data):
        if self.events:
            metadata = {'status': status, 'error': error}
            if error:
                metadata['traceback'] = traceback.format_exc()
            metadata.update(data)
            self.emit(json.dumps(metadata))

    def emit_task(self, status, task, error=False, **data):
        if self.events:
            metadata = self._get_task_metadata(task)
            metadata.update(data)
            self.emit_status(status, error=error, **metadata)

    def execute(self, task):
        if not isinstance(task, QueueTask):
            raise TypeError('Unknown object: %s' % task)

        try:
            result = task.execute()
        except Exception as exc:
            if self.store_errors:
                metadata = self._get_task_metadata(task, True)
                metadata['error'] = repr(exc)
                metadata['traceback'] = traceback.format_exc()
                self.put(task.task_id, Error(metadata))
                self.put_error(metadata)
            raise

        if self.result_store and not isinstance(task, PeriodicQueueTask):
            if result is not None or self.store_none:
                self.put(task.task_id, result)

        if task.on_complete:
            next_task = task.on_complete
            next_task.extend_data(result)
            self.enqueue(next_task)

        return result

    def revoke_all(self, task_class, revoke_until=None, revoke_once=False):
        self.put('rt:%s' % task_class.__name__, (revoke_until, revoke_once))

    def restore_all(self, task_class):
        return self._get_data('rt:%s' % task_class.__name__) is not EmptyData

    def revoke(self, task, revoke_until=None, revoke_once=False):
        self.put(task.revoke_id, (revoke_until, revoke_once))

    def restore(self, task):
        # Return value indicates whether the task was in fact revoked.
        return self._get_data(task.revoke_id) is not EmptyData

    def revoke_by_id(self, task_id, revoke_until=None, revoke_once=False):
        return self.revoke(QueueTask(task_id=task_id), revoke_until,
                           revoke_once)

    def restore_by_id(self, task_id):
        return self.restore(QueueTask(task_id=task_id))

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
        if isclass(task) and issubclass(task, QueueTask):
            revoke_id = 'rt:%s' % task.__name__
            is_revoked, can_restore = self._check_revoked(revoke_id, dt, peek)
            if can_restore:
                self.restore_all(task)
            return is_revoked

        if not isinstance(task, QueueTask):
            task = QueueTask(task_id=task)

        is_revoked, can_restore = self._check_revoked(task.revoke_id, dt, peek)
        if can_restore:
            self.restore(task)
        if not is_revoked:
            is_revoked = self.is_revoked(type(task), dt, peek)

        return is_revoked

    def add_schedule(self, task):
        msg = self.registry.get_message_for_task(task)
        ex_time = task.execute_time or datetime.datetime.fromtimestamp(0)
        self._add_to_schedule(msg, ex_time)

    def read_schedule(self, ts):
        return [self.registry.get_task_for_message(m)
                for m in self._read_schedule(ts)]

    def read_periodic(self, ts):
        periodic = self.registry.get_periodic_tasks()
        return [task for task in periodic
                if task.validate_datetime(ts)]

    def ready_to_run(self, cmd, dt=None):
        dt = dt or datetime.datetime.utcnow()
        return cmd.execute_time is None or cmd.execute_time <= dt

    def pending(self, limit=None):
        return [self.registry.get_task_for_message(m)
                for m in self.storage.enqueued_items(limit)]

    def pending_count(self):
        return self.storage.queue_size()

    def scheduled(self, limit=None):
        return [self.registry.get_task_for_message(m)
                for m in self.storage.scheduled_items(limit)]

    def scheduled_count(self):
        return self.storage.schedule_size()

    def all_results(self):
        return self.storage.result_items()

    def result_count(self):
        return self.storage.result_store_size()

    def errors(self, limit=None, offset=0):
        return [
            pickle.loads(error)
            for error in self.storage.get_errors(limit, offset)]

    def __len__(self):
        return self.pending_count()

    def flush(self):
        self.storage.flush_all()

    def get_tasks(self):
        return sorted(self.registry._registry.keys())

    def get_periodic_tasks(self):
        return [name for name, task in self.registry._registry.items()
                if hasattr(task, 'validate_datetime')]

    def get_regular_tasks(self):
        periodic = set(self.get_periodic_tasks())
        return [task for task in self.get_tasks() if task not in periodic]

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
            if self._get_data(lock_key) is not EmptyData:
                flushed.add(lock_key.split('.lock.', 1)[-1])
        return flushed

    def result(self, task_id, blocking=False, timeout=None, backoff=1.15,
               max_delay=1.0, revoke_on_timeout=False, preserve=False):
        """
        Retrieve the results of a task, given the task's ID. This
        method accepts the same parameters and has the same behavior
        as the :py:class:`TaskResultWrapper` object.
        """
        task_result = TaskResultWrapper(self, QueueTask(task_id=task_id))
        return task_result.get(
            blocking=blocking,
            timeout=timeout,
            backoff=backoff,
            max_delay=max_delay,
            revoke_on_timeout=revoke_on_timeout,
            preserve=preserve)


class TaskWrapper(object):
    def __init__(self, huey, func, retries=0, retry_delay=0,
                 retries_as_argument=False, include_task=False, name=None,
                 task_base=None, **task_settings):
        self.huey = huey
        self.func = func
        self.retries = retries
        self.retry_delay = retry_delay
        self.retries_as_argument = retries_as_argument
        self.include_task = include_task
        self.name = name
        self.task_settings = task_settings
        self.task_class = create_task(
            QueueTask if task_base is None else task_base,
            func,
            retries_as_argument,
            name,
            include_task,
            **task_settings)
        self.huey.registry.register(self.task_class)

    def is_revoked(self, dt=None, peek=True):
        return self.huey.is_revoked(self.task_class, dt, peek)

    def revoke(self, revoke_until=None, revoke_once=False):
        self.huey.revoke_all(self.task_class, revoke_until, revoke_once)

    def restore(self):
        return self.huey.restore_all(self.task_class)

    def schedule(self, args=None, kwargs=None, eta=None, delay=None,
                 convert_utc=True, task_id=None):
        execute_time = self.huey._normalize_execute_time(
            eta=eta, delay=delay, convert_utc=convert_utc)
        cmd = self.task_class(
            (args or (), kwargs or {}),
            execute_time=execute_time,
            retries=self.retries,
            retry_delay=self.retry_delay,
            task_id=task_id)
        return self.huey.enqueue(cmd)

    def __call__(self, *args, **kwargs):
        return self.huey.enqueue(self.s(*args, **kwargs))

    def call_local(self, *args, **kwargs):
        return self.func(*args, **kwargs)

    def s(self, *args, **kwargs):
        return self.task_class((args, kwargs), retries=self.retries,
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
        if not self._huey._put_if_empty(self._key, '1'):
            raise TaskLockedException('unable to set lock: %s' % self._name)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._huey._get_data(self._key)


class TaskResultWrapper(object):
    """
    Wrapper around task result data. When a task is executed, an instance of
    ``TaskResultWrapper`` is returned to provide access to the return value.

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

    def __call__(self, *args, **kwargs):
        return self.get(*args, **kwargs)

    def _get(self, preserve=False):
        task_id = self.task.task_id
        if self._result is EmptyData:
            res = self.huey._get_data(task_id, peek=preserve)

            if res is not EmptyData:
                self._result = pickle.loads(res)
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

    def reschedule(self, eta=None, delay=None, convert_utc=True):
        # Rescheduling works by revoking the currently-scheduled task (nothing
        # is done to check if the task has already run, however). Then the
        # original task's data is used to enqueue a new task with a new task ID
        # and execution_time.
        self.revoke()
        execute_time = self.huey._normalize_execute_time(
            eta=eta, delay=delay, convert_utc=convert_utc)
        cmd = self.task.__class__(
            self.task.data,
            execute_time=execute_time,
            retries=self.task.retries,
            retry_delay=self.task.retry_delay,
            task_id=None)
        return self.huey.enqueue(cmd)

    def reset(self):
        self._result = EmptyData


def with_metaclass(meta, base=object):
    return meta("NewBase", (base,), {})


class QueueTask(object):
    """
    A class that encapsulates the logic necessary to 'do something' given some
    arbitrary data.  When enqueued with the :class:`Huey`, it will be
    stored in a queue for out-of-band execution via the consumer.  See also
    the :meth:`task` decorator, which can be used to automatically
    execute any function out-of-band.

    Example::

    class SendEmailTask(QueueTask):
        def execute(self):
            data = self.get_data()
            send_email(data['recipient'], data['subject'], data['body'])

    huey.enqueue(
        SendEmailTask({
            'recipient': 'somebody@spam.com',
            'subject': 'look at this awesome website',
            'body': 'http://youtube.com'
        })
    )
    """
    default_retries = 0
    default_retry_delay = 0

    def __init__(self, data=None, task_id=None, execute_time=None,
                 retries=None, retry_delay=None, on_complete=None):
        self.name = type(self).__name__
        self.set_data(data)
        self.task_id = task_id or self.create_id()
        self.revoke_id = 'r:%s' % self.task_id
        self.execute_time = execute_time
        self.retries = retries if retries is not None else self.default_retries
        self.retry_delay = retry_delay if retry_delay is not None else \
                self.default_retry_delay
        self.on_complete = on_complete

    def __repr__(self):
        rep = '%s.%s: %s' % (self.__module__, self.name, self.task_id)
        if self.execute_time:
            rep += ' @%s' % self.execute_time
        if self.retries:
            rep += ' %s retries' % self.retries
        if self.on_complete:
            rep += ' -> %s' % self.on_complete
        return rep

    def create_id(self):
        return str(uuid.uuid4())

    def get_data(self):
        return self.data

    def set_data(self, data):
        self.data = data

    def extend_data(self, data):
        if data is None or data == ():
            return
        args, kwargs = self.get_data()
        if isinstance(data, tuple):
            args += data
        elif isinstance(data, dict):
            kwargs.update(data)
        else:
            args = args + (data,)
        self.set_data((args, kwargs))

    def then(self, task, *args, **kwargs):
        if self.on_complete:
            self.on_complete.then(task, *args, **kwargs)
        else:
            self.on_complete = task.s(*args, **kwargs)
        return self

    def execute(self):
        """Execute any arbitary code here"""
        raise NotImplementedError

    def __eq__(self, rhs):
        return (
            self.task_id == rhs.task_id and
            self.execute_time == rhs.execute_time and
            type(self) == type(rhs))


class PeriodicQueueTask(QueueTask):
    def validate_datetime(self, dt):
        """Validate that the task should execute at the given datetime"""
        return False


def create_task(task_class, func, retries_as_argument=False, task_name=None,
                include_task=False, **kwargs):
    def execute(self):
        args, kwargs = self.data or ((), {})
        if retries_as_argument:
            kwargs['retries'] = self.retries
        if include_task:
            kwargs['task'] = self
        return func(*args, **kwargs)

    attrs = {
        'execute': execute,
        '__module__': func.__module__,
        '__doc__': func.__doc__}
    attrs.update(kwargs)

    if not task_name:
        task_name = 'queue_task_%s' % (func.__name__)

    return type(task_name, (task_class,), attrs)


dash_re = re.compile('(\d+)-(\d+)')
every_re = re.compile('\*\/(\d+)')


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
