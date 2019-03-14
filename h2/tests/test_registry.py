from h2.tests.base import BaseTestCase


class TestRegistry(BaseTestCase):
    def test_register_unique(self):
        def task_a(): pass
        def task_b(): pass

        ta = self.huey.task()(task_a)
        self.assertRaises(ValueError, self.huey.task(), task_a)
