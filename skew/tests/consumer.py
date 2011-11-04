import datetime
import threading
import time
import unittest

from skew.backends.dummy import DummyQueue, DummyResultStore
from skew.decorators import queue_command
from skew.exceptions import QueueException
from skew.queue import Invoker, QueueCommand, PeriodicQueueCommand
from skew.registry import registry
from skew.bin.config import BaseConfiguration
from skew.bin.skew_consumer import load_config, Consumer, IterableQueue


# store some global state
state = {}

test_queue = DummyQueue('test-queue', None)
test_result_store = DummyResultStore('test-queue', None)

class DummyConfiguration(BaseConfiguration):
    QUEUE = test_queue
    RESULT_STORE = test_result_store

test_invoker = Invoker(test_queue, test_result_store)


class SkewConsumerTestCase(unittest.TestCase):
    def setUp(self):
        self.orig_sleep = time.sleep
        time.sleep = lambda x: None
        
        self.consumer = Consumer(test_invoker, DummyConfiguration)
    
    def tearDown(self):
        time.sleep = self.orig_sleep
    
    def test_consumer_loader(self):
        config = load_config('skew.tests.config.Config')
        self.assertTrue(isinstance(config.QUEUE, DummyQueue))
        self.assertEqual(config.QUEUE.name, 'test-queue')
    
    def spawn(self, func, *args, **kwargs):
        t = threading.Thread(target=func, args=args, kwargs=kwargs)
        t.start()
        return t
    
    def test_iterable_queue(self):
        store = []
        q = IterableQueue()
        
        def do_queue(queue, result):
            for message in queue:
                result.append(message)
        
        t = self.spawn(do_queue, q, store)
        q.put(1)
        q.put(2)
        q.put(StopIteration)
        
        self.assertFalse(t.is_alive())
        self.assertEqual(store, [1, 2])
