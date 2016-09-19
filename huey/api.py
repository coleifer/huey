import datetime
import json
import pickle
import re
import time
import traceback
import uuid
from functools import wraps

from huey.constants import EmptyData
from huey.exceptions import DataStoreGetException
from huey.exceptions import DataStorePutException
from huey.exceptions import DataStoreTimeout
from huey.exceptions import QueueException
from huey.exceptions import QueueReadException
from huey.exceptions import QueueRemoveException
from huey.exceptions import QueueWriteException
from huey.exceptions import ScheduleAddException
from huey.exceptions import ScheduleReadException
from huey.registry import registry
from huey.utils import local_to_utc
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
                 blocking=False, **storage_kwargs):
        self.name = name
        self.result_store = result_store
        self.events = events
        self.store_none = store_none
        self.always_eager = always_eager
        self.store_errors = store_errors
        self.blocking = blocking
        self.storage = self.get_storage(**storage_kwargs)

    def get_storage(self, **kwargs):
        raise NotImplementedError('Storage API not implemented in the base '
                                  'Huey class. Use `RedisHuey` instead.')

    def task(self, retries=0, retry_delay=0, retries_as_argument=False,
             include_task=False, name=None):
        def decorator(func):
            """
            Decorator to execute a function out-of-band via the consumer.
            """
            klass = create_task(
                QueueTask,
                func,
                retries_as_argument,
                name,
                include_task)

            def schedule(args=None, kwargs=None, eta=None, delay=None,
                         convert_utc=True, task_id=None):
                if delay and eta:
                    raise ValueError('Both a delay and an eta cannot be '
                                     'specified at the same time')
                if delay:
                    eta = (datetime.datetime.now() +
                           datetime.timedelta(seconds=delay))
                if convert_utc and eta:
                    eta = local_to_utc(eta)
                cmd = klass(
                    (args or (), kwargs or {}),
                    execute_time=eta,
                    retries=retries,
                    retry_delay=retry_delay,
                    task_id=task_id)
                return self.enqueue(cmd)

            func.schedule = schedule
            func.task_class = klass

            @wraps(func)
            def inner_run(*args, **kwargs):
                cmd = klass(
                    (args, kwargs),
                    retries=retries,
                    retry_delay=retry_delay)
                return self.enqueue(cmd)

            inner_run.call_local = func
            return inner_run
        return decorator

    def periodic_task(self, validate_datetime, name=None):
        """
        Decorator to execute a function on a specific schedule.
        """
        def decorator(func):
            def method_validate(self, dt):
                return validate_datetime(dt)

            klass = create_task(
                PeriodicQueueTask,
                func,
                task_name=name,
                validate_datetime=method_validate,
            )

            func.task_class = klass

            def _revoke(revoke_until=None, revoke_once=False):
                self.revoke(klass(), revoke_until, revoke_once)
            func.revoke = _revoke

            def _is_revoked(dt=None, peek=True):
                return self.is_revoked(klass(), dt, peek)
            func.is_revoked = _is_revoked

            def _restore():
                return self.restore(klass())
            func.restore = _restore

            return func
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

    def enqueue(self, task):
        if self.always_eager:
            return task.execute()

        self._enqueue(registry.get_message_for_task(task))

        if self.result_store:
            return TaskResultWrapper(self, task)

    def dequeue(self):
        message = self._dequeue()
        if message:
            return registry.get_task_for_message(message)

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
            if self.result_store and self.store_errors:
                metadata = self._get_task_metadata(task, True)
                metadata['error'] = exc
                metadata['traceback'] = traceback.format_exc()
                self._put_error(pickle.dumps(metadata))
            raise

        if result is None and not self.store_none:
            return

        if self.result_store and not isinstance(task, PeriodicQueueTask):
            self._put_data(task.task_id, pickle.dumps(result))

        return result

    def revoke(self, task, revoke_until=None, revoke_once=False):
        serialized = pickle.dumps((revoke_until, revoke_once))
        self._put_data(task.revoke_id, serialized)

    def restore(self, task):
        # Return value indicates whether the task was in fact revoked.
        return self._get_data(task.revoke_id) is not EmptyData

    def revoke_by_id(self, task_id, revoke_until=None, revoke_once=False):
        return self.revoke(QueueTask(task_id=task_id), revoke_until,
                           revoke_once)

    def restore_by_id(self, task_id):
        return self.restore(QueueTask(task_id=task_id))

    def is_revoked(self, task, dt=None, peek=True):
        if not isinstance(task, QueueTask):
            task = QueueTask(task_id=task)
        res = self._get_data(task.revoke_id, peek=True)
        if res is EmptyData:
            return False
        revoke_until, revoke_once = pickle.loads(res)
        if revoke_once:
            # This task *was* revoked for one run, but now it should be
            # restored to normal execution.
            if not peek:
                self.restore(task)
            return True
        return revoke_until is None or revoke_until > dt

    def add_schedule(self, task):
        msg = registry.get_message_for_task(task)
        ex_time = task.execute_time or datetime.datetime.fromtimestamp(0)
        self._add_to_schedule(msg, ex_time)

    def read_schedule(self, ts):
        return [registry.get_task_for_message(m)
                for m in self._read_schedule(ts)]

    def read_periodic(self, ts):
        periodic = registry.get_periodic_tasks()
        return [task for task in periodic
                if task.validate_datetime(ts)]

    def ready_to_run(self, cmd, dt=None):
        dt = dt or datetime.datetime.utcnow()
        return cmd.execute_time is None or cmd.execute_time <= dt

    def pending(self, limit=None):
        return [registry.get_task_for_message(m)
                for m in self.storage.enqueued_items(limit)]

    def pending_count(self):
        return self.storage.queue_size()

    def scheduled(self, limit=None):
        return [registry.get_task_for_message(m)
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
        return sorted(registry._registry.keys())

    def get_periodic_tasks(self):
        return [task_name for task_name, task in registry._registry.items()
                if hasattr(task, 'validate_datetime')]

    def get_regular_tasks(self):
        periodic = set(self.get_periodic_tasks())
        return [task for task in self.get_tasks() if task not in periodic]

    def result(self, task_id, blocking=False, timeout=None, backoff=1.15,
               max_delay=1.0, revoke_on_timeout=False, preserve=False):
        """
        Retrieve the results of a task, given the task's ID. This
        method accepts the same parameters and has the same behavior
        as the :py:class:`TaskResultWrapper` object.
        """
        if not blocking:
            result = self._get_data(task_id, peek=preserve)
            if result is not EmptyData:
                return pickle.loads(result)
        else:
            task_result = TaskResultWrapper(self, QueueTask(task_id=task_id))
            return task_result.get(
                blocking=blocking,
                timeout=timeout,
                backoff=backoff,
                max_delay=max_delay,
                revoke_on_timeout=revoke_on_timeout,
                preserve=preserve)


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
        # block=True. We'll also specify a 4 second timeout so we don't
        # block forever if the consumer goes down:
        result2 = my_task(2, 3)
        print result(block=True, timeout=4)
    """
    def __init__(self, huey, task):
        self.huey = huey
        self.task = task

        self._result = EmptyData

    def __call__(self, *args, **kwargs):
        return self.get(*args, **kwargs)

    def _get(self):
        task_id = self.task.task_id
        if self._result is EmptyData:
            res = self.huey._get_data(task_id)

            if res is not EmptyData:
                self._result = pickle.loads(res)
                return self._result
            else:
                return res
        else:
            return self._result

    def get(self, blocking=False, timeout=None, backoff=1.15, max_delay=1.0,
            revoke_on_timeout=False, preserve=False):
        if not blocking:
            res = self._get()
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
                if self._get() is EmptyData:
                    time.sleep(delay)
                    delay *= backoff

            return self._result

    def revoke(self):
        self.huey.revoke(self.task)

    def restore(self):
        self.huey.restore(self.task)


def with_metaclass(meta, base=object):
    return meta("NewBase", (base,), {})


class QueueTaskMetaClass(type):
    def __init__(cls, name, bases, attrs):
        """
        Metaclass to ensure that all task classes are registered
        """
        registry.register(cls)


class QueueTask(with_metaclass(QueueTaskMetaClass)):
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

    def __init__(self, data=None, task_id=None, execute_time=None, retries=0,
                 retry_delay=0):
        self.set_data(data)
        self.task_id = task_id or self.create_id()
        self.revoke_id = 'r:%s' % self.task_id
        self.execute_time = execute_time
        self.retries = retries
        self.retry_delay = retry_delay
        self.name = type(self).__name__

    def __repr__(self):
        rep = '%s: %s' % (self.name, self.task_id)
        if self.execute_time:
            rep += ' @%s' % self.execute_time
        if self.retries:
            rep += ' %s retries' % self.retries
        return rep

    def create_id(self):
        return str(uuid.uuid4())

    def get_data(self):
        return self.data

    def set_data(self, data):
        self.data = data

    def execute(self):
        """Execute any arbitary code here"""
        raise NotImplementedError

    def __eq__(self, rhs):
        return (
            self.task_id == rhs.task_id and
            self.execute_time == rhs.execute_time and
            type(self) == type(rhs))


class PeriodicQueueTask(QueueTask):
    def create_id(self):
        return registry.task_to_string(type(self))

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
        '__doc__': func.__doc__
    }
    attrs.update(kwargs)

    klass = type(
        task_name or 'queuecmd_%s' % (func.__name__),
        (task_class,),
        attrs
    )

    return klass

dash_re = re.compile('(\d+)-(\d+)')
every_re = re.compile('\*\/(\d+)')

def crontab(month='*', day='*', day_of_week='*', hour='*', minute='*'):
    """
    Convert a "crontab"-style set of parameters into a test function that will
    return True when the given datetime matches the parameters set forth in
    the crontab.

    Acceptable inputs:
    * = every distinct value
    */n = run every "n" times, i.e. hours='*/4' == 0, 4, 8, 12, 16, 20
    m-n = run every time m..n
    m,n = run on m and n
    """
    validation = (
        ('m', month, range(1, 13)),
        ('d', day, range(1, 32)),
        ('w', day_of_week, range(7)),
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
                settings.add(piece)

            else:
                dash_match = dash_re.match(piece)
                if dash_match:
                    lhs, rhs = map(int, dash_match.groups())
                    if lhs not in acceptable or rhs not in acceptable:
                        raise ValueError('%s is not a valid input' % piece)
                    settings.update(range(lhs, rhs+1))
                    continue

                every_match = every_re.match(piece)
                if every_match:
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
