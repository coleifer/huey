import pickle

from huey.exceptions import HueyException
from huey.tests.base import BaseTestCase


class TestRegistry(BaseTestCase):
    def setUp(self):
        super(TestRegistry, self).setUp()
        self.registry = self.huey._registry

    def test_register_unique(self):
        def task_a(): pass
        def task_b(): pass

        ta = self.huey.task()(task_a)
        self.assertRaises(ValueError, self.huey.task(), task_a)
        self.assertRaises(ValueError, self.huey.task(name='task_a'), task_b)

        # We can register task_b and re-register task_a providing a new name.
        tb = self.huey.task()(task_b)
        ta2 = self.huey.task(name='task_a2')(task_a)

        t1 = ta.s()
        t2 = ta2.s()
        self.assertTrue(t1.name != t2.name)

    def test_register_unregister(self):
        @self.huey.task()
        def task_a():
            pass

        self.assertTrue(task_a.unregister())
        self.assertFalse(task_a.unregister())

    def test_message_wrapping(self):
        @self.huey.task(retries=1)
        def task_a(p1, p2, p3=3, p4=None):
            pass

        task = task_a.s('v1', 'v2', p4='v4')
        message = self.registry.create_message(task)
        self.assertEqual(message.id, task.id)
        self.assertEqual(message.retries, 1)
        self.assertEqual(message.retry_delay, 0)
        self.assertEqual(message.args, ('v1', 'v2'))
        self.assertEqual(message.kwargs, {'p4': 'v4'})
        self.assertTrue(message.on_complete is None)
        self.assertTrue(message.on_error is None)
        self.assertTrue(message.expires is None)
        self.assertTrue(message.expires_resolved is None)

        task2 = self.registry.create_task(message)
        self.assertEqual(task2.id, task.id)
        self.assertEqual(task2.retries, 1)
        self.assertEqual(task2.retry_delay, 0)
        self.assertEqual(task2.args, ('v1', 'v2'))
        self.assertEqual(task2.kwargs, {'p4': 'v4'})
        self.assertTrue(task2.on_complete is None)
        self.assertTrue(task2.on_error is None)
        self.assertTrue(task2.expires is None)
        self.assertTrue(task2.expires_resolved is None)

    def test_missing_task(self):
        @self.huey.task()
        def task_a():
            pass

        # Serialize the task invocation.
        task = task_a.s()
        message = self.registry.create_message(task)

        # Unregister the task, which will raise an error when we try to
        # deserialize the message back into a task instance.
        self.assertTrue(task_a.unregister())
        self.assertRaises(HueyException, self.registry.create_task, message)

        # Similarly, we can no longer serialize the task to a message.
        self.assertRaises(HueyException, self.registry.create_message, task)

    def test_periodic_tasks(self):
        def task_fn(): pass
        self.huey.task(name='a')(task_fn)
        p1 = self.huey.periodic_task(lambda _: False, name='p1')(task_fn)
        p2 = self.huey.periodic_task(lambda _: False, name='p2')(task_fn)
        self.huey.task(name='b')(task_fn)

        periodic = sorted(t.name for t in self.registry.periodic_tasks)
        self.assertEqual(periodic, ['p1', 'p2'])

        self.assertTrue(p1.unregister())
        periodic = sorted(t.name for t in self.registry.periodic_tasks)
        self.assertEqual(periodic, ['p2'])

    def test_huey1_compat(self):
        @self.huey.task()
        def task_a(n):
            return n + 1

        t = task_a.s(2)

        # Enqueue a message using the old message serialization format.
        tc = task_a.task_class
        old_message = (t.id, '%s.%s' % (tc.__module__, tc.__name__), None, 0,
                       0, ((2,), {}), None)
        self.huey.storage.enqueue(pickle.dumps(old_message))

        self.assertEqual(len(self.huey), 1)
        self.assertEqual(self.execute_next(), 3)
        self.assertEqual(self.huey.result(t.id), 3)
