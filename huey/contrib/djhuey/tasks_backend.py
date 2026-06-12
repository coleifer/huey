"""
Backend for the django.tasks framework (Django 6.0+, or older Djangos using
the django-tasks backport package) which enqueues tasks into huey. Tasks
declared with the ``django.tasks.task`` decorator are executed by the regular
huey consumer (``manage.py run_huey``), side-by-side with any native huey
tasks, using the shared huey instance configured by ``settings.HUEY``.

Usage::

    TASKS = {'default': {
        'BACKEND': 'huey.contrib.djhuey.tasks_backend.HueyBackend'}}

Notes:

* ``priority`` support depends on the storage backend, e.g. ``SqliteHuey`` or
  ``PriorityRedisHuey`` (plain ``RedisHuey`` does not support priorities, and
  declaring a django task with a non-zero priority will raise InvalidTask).
  ``FileHuey`` does not accept negative priorities.
* ``run_after`` is mapped onto huey's ``eta``. In immediate mode the task is
  placed on the (undrained) in-memory schedule, mirroring the behavior of
  native huey tasks scheduled while in immediate mode.
* Add ``'ENQUEUE_ON_COMMIT': True`` to the backend declaration to defer
  enqueueing until the current transaction commits. The returned result will
  have ``enqueued_at=None`` and cannot be refreshed until the commit fires.
* Task status is tracked in the huey result store under ``djt.<id>``, so
  expiring-result storages like ``RedisExpireHuey`` apply their TTL to it.
  A failed task additionally stores a regular huey error result under the
  bare task id, making failures visible to huey's own tooling and signals.
* ``get_result()`` re-imports the task function; it may raise ImportError if
  the function has since been moved or renamed.
"""
import os
import socket
from datetime import datetime
from traceback import format_exception

from django.db import transaction
from django.utils import timezone
from django.utils.module_loading import import_string

try:
    from django.tasks import Task as DjangoTask
    from django.tasks import TaskContext, TaskResult, TaskResultStatus
    from django.tasks.backends.base import BaseTaskBackend
    from django.tasks.base import TaskError
    from django.tasks.exceptions import InvalidTask
    from django.tasks.exceptions import TaskResultDoesNotExist
    from django.tasks.signals import task_enqueued, task_finished, task_started
    from django.utils.json import normalize_json
except ImportError:
    # Django < 6.0: the django-tasks backport provides the same API.
    from django_tasks.base import Task as DjangoTask
    from django_tasks.base import TaskContext, TaskResult, TaskResultStatus
    from django_tasks.backends.base import BaseTaskBackend
    from django_tasks.base import TaskError
    from django_tasks.exceptions import TaskResultDoesNotExist
    from django_tasks.signals import task_enqueued, task_finished, task_started
    from django_tasks.utils import normalize_json
    try:
        from django_tasks.exceptions import InvalidTask
    except ImportError:
        # django-tasks <= 0.12 used the InvalidTaskError name.
        from django_tasks.exceptions import InvalidTaskError as InvalidTask

from huey.contrib.djhuey import HUEY, close_db


KEY = 'djt.%s'


def _iso(dt):
    return dt.isoformat() if dt is not None else None

def _parse(value):
    return datetime.fromisoformat(value) if value is not None else None


class _RestoredTask(DjangoTask):
    # A Task reconstructed from a stored record. Skips validation, which
    # would otherwise re-run at construction and could fail on environment
    # drift (e.g. priority support or QUEUES changed since enqueue).
    def __post_init__(self):
        pass


def _initial_record(alias, dj_task, id, args, kwargs):
    return {
        'id': id,
        'backend': alias,
        'task_path': dj_task.module_path,
        'priority': dj_task.priority,
        'queue_name': dj_task.queue_name,
        'takes_context': dj_task.takes_context,
        'run_after': _iso(dj_task.run_after),
        'status': TaskResultStatus.READY.value,
        'enqueued_at': None,
        'started_at': None,
        'last_attempted_at': None,
        'finished_at': None,
        'args': args,
        'kwargs': kwargs,
        'return_value': None,
        'errors': [],
        'worker_ids': []}


def _resolve_func(task_path):
    # The module path of a decorated task resolves to the django Task
    # instance (the decorator re-binds the name), but a function wrapped
    # separately resolves to the plain function. Handle both.
    obj = import_string(task_path)
    return obj.func if isinstance(obj, DjangoTask) else obj


def _record_to_result(rec):
    dj_task = _RestoredTask(
        priority=rec['priority'],
        func=_resolve_func(rec['task_path']),
        backend=rec['backend'],
        queue_name=rec['queue_name'],
        run_after=_parse(rec['run_after']),
        takes_context=rec['takes_context'])

    result = TaskResult(
        task=dj_task,
        id=rec['id'],
        status=TaskResultStatus(rec['status']),
        enqueued_at=_parse(rec['enqueued_at']),
        started_at=_parse(rec['started_at']),
        last_attempted_at=_parse(rec['last_attempted_at']),
        finished_at=_parse(rec['finished_at']),
        args=rec['args'],
        kwargs=rec['kwargs'],
        backend=rec['backend'],
        errors=[TaskError(exception_class_path=e[0], traceback=e[1])
                for e in rec['errors']],
        worker_ids=list(rec['worker_ids']))
    if rec['status'] == TaskResultStatus.SUCCESSFUL.value:
        object.__setattr__(result, '_return_value', rec['return_value'])
    return result


def _execute_django_task(task_path, args, kwargs, task=None):
    key = KEY % task.id
    rec = HUEY.get(key, peek=True)

    func = _resolve_func(task_path)
    takes_context = False

    if rec is not None:
        takes_context = rec['takes_context']
        now = _iso(timezone.now())
        rec['status'] = TaskResultStatus.RUNNING.value
        rec['started_at'] = rec['last_attempted_at'] = now
        rec['worker_ids'].append('%s.%s' % (socket.gethostname(), os.getpid()))
        HUEY.put_result(key, rec)
        task_started.send(sender=HueyBackend,
                          task_result=_record_to_result(rec))

    try:
        if takes_context:
            ret = func(TaskContext(task_result=_record_to_result(rec)),
                       *args, **kwargs)
        else:
            ret = func(*args, **kwargs)
        ret = normalize_json(ret)
    except Exception as exc:
        if rec is not None:
            exc_type = type(exc)
            rec['status'] = TaskResultStatus.FAILED.value
            rec['finished_at'] = _iso(timezone.now())
            rec['errors'].append([
                '%s.%s' % (exc_type.__module__, exc_type.__qualname__),
                ''.join(format_exception(exc))])
            HUEY.put_result(key, rec)
            task_finished.send(sender=HueyBackend,
                               task_result=_record_to_result(rec))
        raise
    else:
        if rec is not None:
            rec['status'] = TaskResultStatus.SUCCESSFUL.value
            rec['finished_at'] = _iso(timezone.now())
            rec['return_value'] = ret
            HUEY.put_result(key, rec)
            task_finished.send(sender=HueyBackend,
                               task_result=_record_to_result(rec))


_shim = HUEY.task(name='djtasks.run', context=True)(
    close_db(_execute_django_task))


class HueyBackend(BaseTaskBackend):
    supports_defer = True
    supports_get_result = True

    def __init__(self, alias, params):
        super(HueyBackend, self).__init__(alias, params)
        self.enqueue_on_commit = params.get(
            'ENQUEUE_ON_COMMIT',
            self.options.get('enqueue_on_commit', False))

    @property
    def supports_priority(self):
        return bool(HUEY.storage.priority)

    def _check_resolvable(self, task):
        # validate_task() accepts module-level lambdas and class-body
        # functions, but their module paths cannot be imported by the
        # consumer. Reject them before anything is stored or enqueued.
        # This cannot live in validate_task(), which runs at decoration
        # time, before the module being imported has bound the name.
        try:
            func = _resolve_func(task.module_path)
        except ImportError:
            func = None
        if func is not task.func:
            raise InvalidTask(
                'Task function must be importable from its module path '
                '(%r) - lambdas and class-body functions cannot be used.'
                % task.module_path)

    def enqueue(self, task, args, kwargs):
        self.validate_task(task)
        self._check_resolvable(task)
        args = normalize_json(list(args))
        kwargs = normalize_json(kwargs)
        huey_task = _shim.s(task.module_path, args, kwargs,
                            priority=task.priority or None,
                            eta=task.run_after)
        rec = _initial_record(self.alias, task, huey_task.id, args, kwargs)

        def _enqueue():
            rec['enqueued_at'] = _iso(timezone.now())
            HUEY.put_result(KEY % huey_task.id, rec)
            task_enqueued.send(sender=HueyBackend,
                               task_result=_record_to_result(rec))
            HUEY.enqueue(huey_task)

        if self.enqueue_on_commit:
            transaction.on_commit(_enqueue)
            return _record_to_result(rec)

        _enqueue()
        # Re-read the record, as in immediate mode the task has already run.
        stored = HUEY.get(KEY % huey_task.id, peek=True) or rec
        return _record_to_result(stored)

    def get_result(self, result_id):
        rec = HUEY.get(KEY % result_id, peek=True)
        if rec is None:
            raise TaskResultDoesNotExist(result_id)
        return _record_to_result(rec)
