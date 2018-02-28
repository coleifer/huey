from huey import RedisHuey
from huey.exceptions import CancelExecution
from huey.tests.base import HueyTestCase


test_huey = RedisHuey('testing-2', blocking=False, read_timeout=0.1)


@test_huey.task()
def add_values(a, b):
    return a + b


@test_huey.task()
def fail():
    raise Exception('failed')


ALLOW_TASKS = True
PRE_STATE = []
POST_STATE = []


@test_huey.pre_execute()
def pre_run(task):
    if not ALLOW_TASKS:
        raise CancelExecution()


@test_huey.pre_execute()
def pre_run2(task):
    global PRE_STATE
    PRE_STATE.append(task)


@test_huey.post_execute()
def post_run(task, task_value, exc):
    global POST_STATE
    POST_STATE.append((task, task_value, exc))


class HooksTestCase(HueyTestCase):
    def setUp(self):
        super(HooksTestCase, self).setUp()
        global ALLOW_TASKS
        global PRE_STATE
        global POST_STATE
        ALLOW_TASKS = True
        PRE_STATE = []
        POST_STATE = []

    def get_huey(self):
        return test_huey


class TestHooks(HooksTestCase):
    def test_hooks_being_run(self):
        res = add_values(1, 2)
        task = self.huey.dequeue()
        self.worker(task)

        self.assertEqual(PRE_STATE, [task])
        self.assertEqual(POST_STATE, [(task, 3, None)])

    def test_cancel_execution(self):
        res = add_values(1, 2)
        task = self.huey.dequeue()

        global ALLOW_TASKS
        ALLOW_TASKS = False
        self.worker(task)

        self.assertEqual(PRE_STATE, [])
        self.assertEqual(POST_STATE, [])

    def test_capture_error(self):
        res = fail()
        task = self.huey.dequeue()
        self.worker(task)

        self.assertEqual(PRE_STATE, [task])
        self.assertEqual(len(POST_STATE), 1)

        task_obj, ret, exc = POST_STATE[0]
        self.assertEqual(task_obj, task)
        self.assertTrue(ret is None)
        self.assertTrue(exc is not None)
