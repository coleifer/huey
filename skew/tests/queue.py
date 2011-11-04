import datetime
import unittest

from skew.backends.dummy import DummyQueue, DummyResultStore
from skew.decorators import queue_command, periodic_command, crontab
from skew.exceptions import QueueException
from skew.queue import Invoker, QueueCommand, PeriodicQueueCommand
from skew.registry import registry


queue_name = 'test-queue'
queue = DummyQueue(queue_name, None)
invoker = Invoker(queue)

res_queue_name = 'test-queue-2'
res_queue = DummyQueue(res_queue_name, None)
res_store = DummyResultStore(res_queue_name, None)

res_invoker = Invoker(res_queue, res_store)

# store some global state
state = {}

# create a decorated queue command
@queue_command(invoker)
def add(key, value):
    state[key] = value

# create a periodic queue command
@periodic_command(invoker, crontab(minute='0'))
def add_on_the_hour():
    state['periodic'] = 'x'

# define a command using the class
class AddCommand(QueueCommand):
    def execute(self):
        k, v = self.data
        state[k] = v

# create a command that raises an exception
class BampfException(Exception):
    pass

@queue_command(invoker)
def throw_error():
    raise BampfException('bampf')

@queue_command(res_invoker)
def add2(a, b):
    return a + b


class SkewTestCase(unittest.TestCase):
    def setUp(self):
        global state
        queue.flush()
        state = {}
    
    def test_registration(self):
        self.assertTrue('skew.tests.queue.queuecmd_add' in registry)
        self.assertTrue('skew.tests.queue.queuecmd_add_on_the_hour' in registry)
        self.assertTrue('skew.tests.queue.AddCommand' in registry)
    
    def test_enqueue(self):
        # sanity check
        self.assertEqual(len(queue), 0)
        
        # initializing the command does not enqueue it
        ac = AddCommand(('k', 'v'))
        self.assertEqual(len(queue), 0)
        
        # ok, enqueue it, then check that it was enqueued
        invoker.enqueue(ac)
        self.assertEqual(len(queue), 1)
        
        # it can be enqueued multiple times
        invoker.enqueue(ac)
        self.assertEqual(len(queue), 2)
        
        # no changes to state
        self.assertFalse('k' in state)
    
    def test_enqueue_decorator(self):
        # sanity check
        self.assertEqual(len(queue), 0)
        
        add('k', 'v')
        self.assertEqual(len(queue), 1)
        
        add('k', 'v')
        self.assertEqual(len(queue), 2)
        
        # no changes to state
        self.assertFalse('k' in state)
    
    def test_enqueue_periodic(self):
        dt = datetime.datetime(2011, 1, 1, 0, 1)
        invoker.enqueue_periodic_commands(dt)
        self.assertEqual(len(queue), 0)
        
        dt = datetime.datetime(2011, 1, 1, 0, 0)
        invoker.enqueue_periodic_commands(dt)
        self.assertEqual(len(queue), 1)
        
        self.assertFalse('periodic' in state)
        
        invoker.dequeue()
        self.assertEqual(state['periodic'], 'x')
    
    def test_error_raised(self):
        throw_error()
        
        self.assertRaises(BampfException, invoker.dequeue)
    
    def test_dequeueing(self):
        invoker.dequeue() # no error raised if queue is empty
        
        self.assertFalse('k' in state)
        add('k', 'v')
        
        invoker.dequeue()
        self.assertEqual(state['k'], 'v')
        
        add('k', 'X')
        self.assertEqual(state['k'], 'v')
        
        invoker.dequeue()
        self.assertEqual(state['k'], 'X')
    
    def test_result_store(self):
        res = add2(1, 2)
        res2 = add2(4, 5)
        res3 = add2(0, 0)
        self.assertEqual(res.get(), None)
        self.assertEqual(res2.get(), None)
        self.assertEqual(res3.get(), None)

        res_invoker.dequeue()
        self.assertEqual(res.get(), 3)
        self.assertEqual(res2.get(), None)
        self.assertEqual(res3.get(), None)
        
        res_invoker.dequeue()
        self.assertEqual(res.get(), 3)
        self.assertEqual(res2.get(), 9)
        self.assertEqual(res3.get(), None)
        
        res_invoker.dequeue()
        self.assertEqual(res.get(), 3)
        self.assertEqual(res2.get(), 9)
        self.assertEqual(res3.get(), 0)
