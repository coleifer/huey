from huey import RedisHuey
from huey.api import crontab
from huey.api import QueueTask
from huey.registry import registry
from huey.tests.base import BaseTestCase
from huey.tests.base import DummyHuey


huey = DummyHuey(None)

@huey.task()
def test_task_one(x, y):
    pass

@huey.periodic_task(crontab(minute='0'))
def test_task_two():
    pass

@huey.task(foo='bar', priority=3)
def important():
    pass

class MyTaskClass(QueueTask):
    def execute(self):
        pass


class TestRegistry(BaseTestCase):
    def test_registry(self):
        self.assertTrue('queue_task_test_task_one' in registry)
        self.assertTrue('queue_task_test_task_two' in registry)
        self.assertFalse('MyTaskClass' in registry)

        registry.register(MyTaskClass)
        self.assertTrue('MyTaskClass' in registry)

        self.assertFalse('another' in registry)

    def test_arbitrary_parameters(self):
        Task = registry._registry['queue_task_important']
        self.assertEqual(Task.foo, 'bar')
        self.assertEqual(Task.priority, 3)

    def test_periodic_tasks(self):
        periodic = registry._periodic_tasks
        self.assertTrue(test_task_two.task_class in periodic)

    def test_non_global_task_registry(self):

        huey = RedisHuey(global_registry=False)

        @huey.task()
        def test():
            return 'test'

        self.assertIn('queue_task_test', huey.registry._registry)
        huey2 = RedisHuey(global_registry=False)
        self.assertNotIn('queue_task_test', huey2.registry._registry)
