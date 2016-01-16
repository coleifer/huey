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

class MyTaskClass(QueueTask):
    def execute(self):
        pass


class TestRegistry(BaseTestCase):
    def test_registry(self):
        self.assertTrue('queuecmd_test_task_one' in registry)
        self.assertTrue('queuecmd_test_task_two' in registry)
        self.assertTrue('MyTaskClass' in registry)
        self.assertFalse('another' in registry)

    def test_periodic_tasks(self):
        periodic = registry._periodic_tasks
        task_classes = [type(task) for task in periodic]
        self.assertTrue(test_task_two.task_class in task_classes)
