import datetime
import os
import pickle
import re
import sys
import time
import uuid

from huey.exceptions import DataStoreGetException
from huey.exceptions import DataStorePutException
from huey.exceptions import DataStoreTimeout
from huey.exceptions import QueueException
from huey.exceptions import QueueReadException
from huey.exceptions import QueueWriteException
from huey.registry import registry
from huey.utils import EmptyData
from huey.utils import local_to_utc
from huey.utils import wrap_exception


class Huey(object):
    """
    Huey executes tasks by exposing function decorators that cause the function
    call to be enqueued for execution by the consumer.

    Typically your application will only need one Huey instance, but you can
    have as many as you like -- the only caveat is that one consumer process
    must be executed for each Huey instance.

    :param queue: a queue instance, e.g. ``RedisQueue()``
    :param result_store: a place to store results and the command schedule,
        e.g. ``RedisResultStore()``
    :param store_none: Flag to indicate whether tasks that return ``None``
        should store their results in the result store.
    :param always_eager: Useful for testing, this will execute all tasks
        immediately, without enqueueing them.

    Example usage::

        from huey.api import Huey, crontab
        from huey.backends.redis_backend import RedisQueue, RedisDataStore

        queue = RedisQueue()
        result_store = RedisDataStore()
        huey = Huey(queue, result_store)

        @huey.task()
        def slow_function(some_arg):
            # ... do something ...
            return some_arg

        @huey.periodic_task(crontab(minute='0', hour='3'))
        def backup():
            # do a backup every day at 3am
            return
    """
    def __init__(self, queue, result_store=None, store_none=False
                 always_eager=False):
        self.queue = queue
        self.result_store = result_store
        self.blocking = self.queue.blocking
        self.store_none = store_none
        self.always_eager = always_eager

    def task(self, retries=0, retry_delay=0, retries_as_argument=False):
        def decorator(func):
            """
            Decorator to execute a function out-of-band via the consumer.
            """
            klass = create_command(QueueCommand, func, retries_as_argument)

            def schedule(args=None, kwargs=None, eta=None, delay=None,
                         convert_utc=True):
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
                    retries=retries)
                return self.enqueue(cmd)

            func.schedule = schedule
            func.command_class = klass

            @wraps(func)
            def inner_run(*args, **kwargs):
                cmd = klass(
                    (args, kwargs),
                    retries=retries,
                    retry_delay=retry_delay)
                return self.enqueue(cmd)
            return inner_run
        return decorator

    def periodic_task(self, validate_datetime):
        """
        Decorator to execute a function on a specific schedule.
        """
        def decorator(func):
            def method_validate(self, dt):
                return validate_datetime(dt)

            klass = create_command(
                PeriodicQueueCommand,
                func,
                validate_datetime=method_validate
            )

            func.command_class = klass

            def _revoke(revoke_until=None, revoke_once=False):
                self.revoke(klass(), revoke_until, revoke_once)
            func.revoke = _revoke

            def _is_revoked(dt=None, preserve=True):
                return self.is_revoked(klass(), dt, preserve)
            func.is_revoked = _is_revoked

            def _restore():
                return self.restore(klass())
            func.restore = _restore

            return func
        return decorator

    def _write(self, msg):
        try:
            self.queue.write(msg)
        except:
            wrap_exception(QueueWriteException)

    def _read(self):
        try:
            return self.queue.read()
        except:
            wrap_exception(QueueReadException)

    def _remove(self, msg):
        try:
            return self.queue.remove(msg)
        except:
            wrap_exception(QueueRemoveException)

    def _get(self, key, peek=False):
        try:
            if peek:
                return self.result_store.peek(key)
            else:
                return self.result_store.get(key)
        except:
            return wrap_exception(DataStoreGetException)

    def _put(self, key, value):
        try:
            return self.result_store.put(key, value)
        except:
            return wrap_exception(DataStorePutException)

    def enqueue(self, command):
        if self.always_eager:
            return command.execute()

        self._write(registry.get_message_for_command(command))

        if self.result_store:
            return AsyncData(self, command)

    def dequeue(self):
        message = self._read()
        if message:
            return registry.get_command_for_message(message)

    def execute(self, command):
        if not isinstance(command, QueueCommand):
            raise TypeError('Unknown object: %s' % command)

        result = command.execute()

        if result is None and not self.store_none:
            return

        if self.result_store and not isinstance(command, PeriodicQueueCommand):
            self._put(command.task_id, pickle.dumps(result))

        return result

    def revoke(self, command, revoke_until=None, revoke_once=False):
        if not self.result_store:
            raise QueueException('A DataStore is required to revoke commands')

        serialized = pickle.dumps((revoke_until, revoke_once))
        self._put(command.revoke_id, serialized)
        #self._remove(registry.get_message_for_command(command))

    def restore(self, command):
        self._get(command.revoke_id)  # simply get and delete if there

    def is_revoked(self, command, dt=None, preserve=True):
        if not self.result_store:
            return False
        res = self._get(command.revoke_id, peek=True)
        if res is EmptyData:
            return False
        revoke_until, revoke_once = pickle.loads(res)
        if revoke_once:
            if not preserve:
                self.restore(command)
            return True
        return revoke_until is None or revoke_until > dt

    def flush(self):
        self.queue.flush()


class AsyncData(object):
    def __init__(self, huey, command):
        self.huey = huey
        self.command = command

        self._result = EmptyData

    def _get(self):
        task_id = self.command.task_id
        if self._result is EmptyData:
            res = self.huey._get(task_id)

            if res is not EmptyData:
                self._result = pickle.loads(res)
                return self._result
            else:
                return res
        else:
            return self._result

    def get(self, blocking=False, timeout=None, backoff=1.15, max_delay=1.0,
            revoke_on_timeout=False):
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
        self.huey.revoke(self.command)

    def restore(self):
        self.huey.restore(self.command)


class CommandSchedule(object):
    def __init__(self, huey, key_name='schedule'):
        self.huey = huey
        self.key_name = key_name

        self.result_store = self.huey.result_store
        self._schedule = {}

    def __contains__(self, task_id):
        return task_id in self._schedule

    def load(self):
        if self.result_store:
            serialized = self.result_store.get(self.key_name)

            if serialized and serialized is not EmptyData:
                self.load_commands(pickle.loads(serialized))

    def load_commands(self, messages):
        for cmd_string in messages:
            try:
                cmd_obj = registry.get_command_for_message(cmd_string)
                self.add(cmd_obj)
            except QueueException:
                pass

    def save(self):
        if self.result_store:
            self.result_store.put(self.key_name, self.serialize_commands())

    def serialize_commands(self):
        return pickle.dumps([
            registry.get_message_for_command(c) for c in self.commands()])

    def commands(self):
        return self._schedule.values()

    def should_run(self, cmd, dt=None):
        dt = dt or datetime.datetime.now()
        return cmd.execute_time is None or cmd.execute_time <= dt

    def can_run(self, cmd, dt=None):
        return not self.huey.is_revoked(cmd, dt, False)

    def add(self, cmd):
        if not self.is_pending(cmd):
            self._schedule[cmd.task_id] = cmd

    def remove(self, cmd):
        if self.is_pending(cmd):
            del(self._schedule[cmd.task_id])

    def is_pending(self, cmd):
        return cmd.task_id in self._schedule


class QueueCommandMetaClass(type):
    def __init__(cls, name, bases, attrs):
        """
        Metaclass to ensure that all command classes are registered
        """
        registry.register(cls)


class QueueCommand(object):
    """
    A class that encapsulates the logic necessary to 'do something' given some
    arbitrary data.  When enqueued with the :class:`Invoker`, it will be
    stored in a queue for out-of-band execution via the consumer.  See also
    the :func:`queue_command` decorator, which can be used to automatically
    execute any function out-of-band.

    Example::

    class SendEmailCommand(QueueCommand):
        def execute(self):
            data = self.get_data()
            send_email(data['recipient'], data['subject'], data['body'])

    huey.enqueue(
        SendEmailCommand({
            'recipient': 'somebody@spam.com',
            'subject': 'look at this awesome website',
            'body': 'http://youtube.com'
        })
    )
    """

    __metaclass__ = QueueCommandMetaClass

    def __init__(self, data=None, task_id=None, execute_time=None, retries=0,
                 retry_delay=0):
        """
        Initialize the command object with a receiver and optional data.  The
        receiver object *must* be a django model instance.
        """
        self.set_data(data)
        self.task_id = task_id or self.create_id()
        self.revoke_id = 'r:%s' % self.task_id
        self.execute_time = execute_time
        self.retries = retries
        self.retry_delay = retry_delay

    def create_id(self):
        return str(uuid.uuid4())

    def get_data(self):
        """Called by the Invoker when a command is being enqueued"""
        return self.data

    def set_data(self, data):
        """Called by the Invoker when a command is dequeued"""
        self.data = data

    def execute(self):
        """Execute any arbitary code here"""
        raise NotImplementedError

    def __eq__(self, rhs):
        return (
            self.task_id == rhs.task_id and
            self.execute_time == rhs.execute_time and
            type(self) == type(rhs))


class PeriodicQueueCommand(QueueCommand):
    def create_id(self):
        return registry.command_to_string(type(self))

    def validate_datetime(self, dt):
        """Validate that the command should execute at the given datetime"""
        return False


def create_command(command_class, func, retries_as_argument=False, **kwargs):
    def execute(self):
        args, kwargs = self.data or ((), {})
        if retries_as_argument:
            kwargs['retries'] = self.retries
        return func(*args, **kwargs)

    attrs = {
        'execute': execute,
        '__module__': func.__module__,
        '__doc__': func.__doc__
    }
    attrs.update(kwargs)

    klass = type(
        'queuecmd_%s' % (func.__name__),
        (command_class,),
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
    min_interval = None

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
