import datetime
import importlib.util
import time
import unittest


django_tasks_available = importlib.util.find_spec('django') is not None and (
    importlib.util.find_spec('django.tasks') is not None or
    importlib.util.find_spec('django_tasks') is not None)

if django_tasks_available:
    import django
    from django.conf import settings

    from huey import MemoryHuey

    settings.configure(
        USE_TZ=True,
        DATABASES={'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': ':memory:'}},
        TASKS={'default': {
            'BACKEND': 'huey.contrib.djhuey.tasks_backend.HueyBackend'}},
        HUEY=MemoryHuey('djtasks-test'))
    django.setup()

    from django.db import transaction
    from django.test import override_settings
    from django.utils import timezone

    try:
        from django.tasks import TaskResultStatus, default_task_backend, task
        from django.tasks.exceptions import InvalidTask
        from django.tasks.exceptions import TaskResultDoesNotExist
        from django.tasks.exceptions import TaskResultMismatch
    except ImportError:
        # Django < 6.0: the django-tasks backport provides the same API.
        from django_tasks import TaskResultStatus, default_task_backend, task
        from django_tasks.exceptions import TaskResultDoesNotExist
        from django_tasks.exceptions import TaskResultMismatch
        try:
            from django_tasks.exceptions import InvalidTask
        except ImportError:
            from django_tasks.exceptions import InvalidTaskError as InvalidTask

    from huey.contrib.djhuey import HUEY
    from huey.tests.base import BaseTestCase

    @task
    def add(a, b):
        return a + b

    @task
    def explode():
        raise ValueError('kapow')

    @task(takes_context=True)
    def with_context(context, x):
        return [context.attempt, x]

    @task
    def bad_return():
        return object()

    def plain():
        pass

    async def aplain():
        pass

    anon_task = task(lambda: 1)


@unittest.skipIf(not django_tasks_available,
                 'requires django.tasks or django-tasks backport')
class TestDjangoTasksBackend(unittest.TestCase):
    def setUp(self):
        HUEY.immediate = False
        HUEY.storage.flush_all()

    def run_next(self):
        huey_task = HUEY.dequeue()
        self.assertTrue(huey_task is not None)
        return HUEY.execute(huey_task)

    def test_enqueue_execute(self):
        result = add.enqueue(2, 3)
        self.assertEqual(result.status, TaskResultStatus.READY)
        self.assertTrue(result.enqueued_at is not None)
        self.assertTrue(result.started_at is None)
        self.assertEqual(HUEY.pending_count(), 1)

        self.run_next()

        result.refresh()
        self.assertEqual(result.status, TaskResultStatus.SUCCESSFUL)
        self.assertEqual(result.return_value, 5)
        self.assertTrue(result.started_at is not None)
        self.assertTrue(result.finished_at is not None)
        self.assertEqual(result.attempts, 1)

    def test_failure(self):
        result = explode.enqueue()
        self.run_next()

        result.refresh()
        self.assertEqual(result.status, TaskResultStatus.FAILED)
        self.assertEqual(len(result.errors), 1)
        self.assertTrue(result.errors[0].exception_class is ValueError)
        self.assertTrue('kapow' in result.errors[0].traceback)
        self.assertRaises(ValueError, lambda: result.return_value)

    def test_get_result(self):
        result = add.enqueue(1, 1)
        fetched = default_task_backend.get_result(result.id)
        self.assertEqual(fetched.id, result.id)
        self.assertEqual(fetched.args, [1, 1])
        self.assertEqual(fetched.status, TaskResultStatus.READY)

        # Fetching through the matching task works, a mismatched task fails.
        self.assertEqual(add.get_result(result.id).id, result.id)
        self.assertRaises(TaskResultMismatch, explode.get_result, result.id)
        self.assertRaises(TaskResultDoesNotExist,
                          default_task_backend.get_result, 'missing')

    def test_priority_order(self):
        add.enqueue(1, 1)
        add.using(priority=10).enqueue(2, 2)
        add.using(priority=-10).enqueue(3, 3)

        order = [HUEY.dequeue().args[1] for _ in range(3)]
        self.assertEqual(order, [[2, 2], [1, 1], [3, 3]])

    def test_run_after(self):
        run_after = timezone.now() + datetime.timedelta(minutes=5)
        result = add.using(run_after=run_after).enqueue(1, 2)
        self.assertEqual(result.status, TaskResultStatus.READY)

        huey_task = HUEY.dequeue()
        self.assertTrue(huey_task.eta is not None)

        # Naive datetimes are rejected when USE_TZ is enabled.
        naive = datetime.datetime.now() + datetime.timedelta(minutes=5)
        self.assertRaises(InvalidTask, add.using, run_after=naive)

    def test_takes_context(self):
        result = with_context.enqueue(7)
        self.run_next()
        result.refresh()
        self.assertEqual(result.return_value, [1, 7])

    def test_immediate_mode(self):
        HUEY.immediate = True
        result = add.enqueue(3, 4)
        self.assertEqual(result.status, TaskResultStatus.SUCCESSFUL)
        self.assertEqual(result.return_value, 7)

    def test_invalid_tasks(self):
        self.assertRaises(InvalidTask, task(queue_name='nope'), plain)
        self.assertRaises(InvalidTask, task, aplain)

        # Module paths that do not round-trip are rejected at enqueue,
        # before anything is stored or enqueued.
        self.assertRaises(InvalidTask, anon_task.enqueue)
        self.assertEqual(HUEY.pending_count(), 0)
        self.assertEqual(HUEY.result_count(), 0)

    def test_unserializable_return(self):
        result = bad_return.enqueue()
        self.run_next()
        result.refresh()
        self.assertEqual(result.status, TaskResultStatus.FAILED)
        self.assertEqual(len(result.errors), 1)
        self.assertRaises(ValueError, lambda: result.return_value)

    def test_unsupported_priority(self):
        HUEY.storage.priority = False
        try:
            self.assertRaises(InvalidTask, add.using, priority=5)
        finally:
            HUEY.storage.priority = True

    def test_enqueue_on_commit(self):
        backend = {
            'BACKEND': 'huey.contrib.djhuey.tasks_backend.HueyBackend',
            'ENQUEUE_ON_COMMIT': True}
        with override_settings(TASKS={'default': backend}):
            with transaction.atomic():
                result = add.enqueue(5, 5)
                # Nothing is stored or enqueued until the commit fires.
                self.assertEqual(result.status, TaskResultStatus.READY)
                self.assertTrue(result.enqueued_at is None)
                self.assertEqual(HUEY.pending_count(), 0)
                self.assertRaises(TaskResultDoesNotExist, result.refresh)

            self.assertEqual(HUEY.pending_count(), 1)
            self.run_next()
            result.refresh()
            self.assertTrue(result.enqueued_at is not None)
            self.assertEqual(result.return_value, 10)


if django_tasks_available:
    class TestDjangoTasksConsumer(BaseTestCase):
        def get_huey(self):
            HUEY.immediate = False
            HUEY.storage.flush_all()
            return HUEY

        def test_consumer_integration(self):
            with self.consumer_context():
                result = add.enqueue(4, 5)
                for _ in range(100):
                    result.refresh()
                    if result.is_finished:
                        break
                    time.sleep(0.05)
            self.assertEqual(result.status, TaskResultStatus.SUCCESSFUL)
            self.assertEqual(result.return_value, 9)
