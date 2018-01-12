from huey import RedisHuey
from huey.tests.base import BaseTestCase


huey = RedisHuey(blocking=False, max_errors=10)


state = {}


@huey.task()
def fib(a, b=1):
    a, b = a + b, a
    return (a, b)


@huey.task()
def stateful(v1=None, v2=None, v3=None):
    state = {
        'v1': v1 + 1 if v1 is not None else 0,
        'v2': v2 + 2 if v2 is not None else 0,
        'v3': v3 + 3 if v3 is not None else 0}
    return state


@huey.task()
def add(a, b):
    return a + b


@huey.task()
def mul(a, b):
    return a * b


class TestPipeline(BaseTestCase):
    def assertPipe(self, pipe, expected):
        results = huey.enqueue(pipe)
        for _ in range(len(results)):
            self.assertEqual(len(huey), 1)
            huey.execute(huey.dequeue())

        # Pipeline is finished.
        self.assertEqual(len(huey), 0)
        self.assertEqual([result.get() for result in results], expected)

    def test_pipeline_tuple(self):
        pipe = fib.s(1).then(fib).then(fib).then(fib)
        self.assertPipe(pipe, [(2, 1), (3, 2), (5, 3), (8, 5)])

    def test_pipeline_dict(self):
        pipe = stateful.s().then(stateful).then(stateful)
        self.assertPipe(pipe, [
            {'v1': 0, 'v2': 0, 'v3': 0},
            {'v1': 1, 'v2': 2, 'v3': 3},
            {'v1': 2, 'v2': 4, 'v3': 6}])

    def test_partial(self):
        pipe = add.s(1, 2).then(add, 3).then(add, 4).then(add, 5)
        self.assertPipe(pipe, [3, 6, 10, 15])

    def test_mixed(self):
        pipe = add.s(1, 2).then(mul, 4).then(add, -5).then(mul, 3).then(add, 8)
        self.assertPipe(pipe, [3, 12, 7, 21, 29])
