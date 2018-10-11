import datetime
import sys
import unittest

import gevent
from simpledb import Client
from simpledb import QueueServer

from huey.contrib.simple_storage import SimpleHuey
from huey.tests.base import BaseTestCase


huey = SimpleHuey(port=31339)


def run_queue_server():
    server = QueueServer(host='127.0.0.1', port=31339, use_gevent=True)
    gevent.spawn(server.run)


@huey.task()
def add_numbers(a, b):
    return a + b


class TestSimpleHuey(BaseTestCase):
    @classmethod
    def setUpClass(cls):
        run_queue_server()

    def setUp(self):
        huey.storage.flush_all()

    def test_queue(self):
        res = add_numbers(1, 2)
        task = huey.dequeue()
        self.assertEqual(huey.execute(task), 3)
        self.assertEqual(res.get(), 3)

    def test_schedule(self):
        ts = datetime.datetime.now().replace(microsecond=0)
        make_eta = lambda s: ts + datetime.timedelta(seconds=s)

        res1 = add_numbers.schedule((1, 2), eta=make_eta(4), convert_utc=False)
        res2 = add_numbers.schedule((2, 3), eta=make_eta(2), convert_utc=False)
        self.assertEqual(len(huey), 2)

        r = huey.dequeue()
        huey.add_schedule(r)
        huey.add_schedule(huey.dequeue())

        scheduled = huey.read_schedule(make_eta(1))
        self.assertEqual(len(scheduled), 0)

        scheduled = huey.read_schedule(make_eta(2))
        self.assertEqual(len(scheduled), 1)
        task, = scheduled
        self.assertEqual(huey.execute(task), 5)
        self.assertEqual(res2.get(), 5)

        scheduled = huey.read_schedule(make_eta(4))
        self.assertEqual(len(scheduled), 1)
        task, = scheduled
        self.assertEqual(huey.execute(task), 3)
        self.assertEqual(res1.get(), 3)


if __name__ == '__main__':
    unittest.main(argv=sys.argv)
