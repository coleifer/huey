from huey.tests.base import BaseTestCase
from huey.wrapper import RedisHueyExt


state = {}

def pre_task():
    state['pre'] = True

def post_task():
    state['post'] = True

huey = RedisHueyExt()

@huey.task(pre_task, post_task)
def set_value(k, v):
    state[k] = v
    return v

@huey.task(pre_task)
def set_value_pre(k, v):
    state[k] = v
    return v

@huey.task(None, post_task)
def set_value_post(k, v):
    state[k] = v
    return v


class TestTaskWrapper(BaseTestCase):
    def setUp(self):
        super(TestTaskWrapper, self).setUp()
        global state
        state = {}

    def test_task_wrapper(self):
        self.assertEqual(state, {})

        set_value('foo', 'bar')
        huey.execute(huey.dequeue())

        self.assertEqual(state, {
            'pre': True,
            'post': True,
            'foo': 'bar'})

    def test_pretask_only(self):
        set_value_pre('foo', 'bar')
        huey.execute(huey.dequeue())

        self.assertEqual(state, {
            'pre': True,
            'foo': 'bar'})

    def test_posttask_only(self):
        set_value_post('foo', 'bar')
        huey.execute(huey.dequeue())

        self.assertEqual(state, {
            'post': True,
            'foo': 'bar'})
