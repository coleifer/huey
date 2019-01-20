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

@huey.task(name='three')
def test_task_three():
    pass

@huey.task(foo='bar', priority=3)
def important():
    pass

class MyTaskClass(QueueTask):
    def execute(self):
        pass


class TestRegistry(BaseTestCase):
    def test_registry(self):
        self.assertTrue('huey.tests.test_registry.test_task_one' in registry)
        self.assertTrue('huey.tests.test_registry.test_task_two' in registry)
        self.assertTrue('huey.tests.test_registry.three' in registry)
        self.assertFalse('huey.tests.test_registry.MyTaskClass' in registry)

        registry.register(MyTaskClass)
        self.assertTrue('huey.tests.test_registry.MyTaskClass' in registry)

        self.assertFalse('huey.tests.test_registry.another' in registry)
        self.assertFalse(
            'huey.tests.test_registry.test_task_three' in registry)

    def test_arbitrary_parameters(self):
        Task = registry._registry['huey.tests.test_registry.important']
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

        self.assertIn('huey.tests.test_registry.test', huey.registry._registry)
        huey2 = RedisHuey(global_registry=False)
        self.assertNotIn('huey.tests.test_registry.test',
                         huey2.registry._registry)
