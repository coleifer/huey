import datetime
import unittest

from skew.backends.dummy import DummyQueue, DummyResultStore
from skew.decorators import queue_command
from skew.exceptions import QueueException
from skew.queue import Invoker, QueueCommand, PeriodicQueueCommand
from skew.registry import registry
from skew.bin.skew_consumer import load_config, Consumer, IterableQueue


# store some global state
state = {}


class SkewConsumerTestCase(unittest.TestCase):
    def test_consumer_loader(self):
        config = load_config('skew.tests.config.Config')
        self.assertTrue(isinstance(config.QUEUE, DummyQueue))
        self.assertEqual(config.QUEUE.name, 'test-queue')
