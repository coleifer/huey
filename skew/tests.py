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
        self.assertTrue('skew.tests.queuecmd_add' in registry)
        self.assertTrue('skew.tests.queuecmd_add_on_the_hour' in registry)
        self.assertTrue('skew.tests.AddCommand' in registry)
    
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


class SkewCrontabTestCase(unittest.TestCase):
    def test_crontab_month(self):
        # validates the following months, 1, 4, 7, 8, 9
        valids = [1, 4, 7, 8, 9]
        validate_m = crontab(month='1,4,*/6,8-9')
        
        for x in xrange(1, 13):
            res = validate_m(datetime.datetime(2011, x, 1))
            self.assertEqual(res, x in valids)
    
    def test_crontab_day(self):
        # validates the following days
        valids = [1, 4, 7, 8, 9, 13, 19, 25, 31]
        validate_d = crontab(day='*/6,1,4,8-9')
        
        for x in xrange(1, 32):
            res = validate_d(datetime.datetime(2011, 1, x))
            self.assertEqual(res, x in valids)
    
    def test_crontab_hour(self):
        # validates the following hours
        valids = [0, 1, 4, 6, 8, 9, 12, 18]
        validate_h = crontab(hour='8-9,*/6,1,4')
        
        for x in xrange(24):
            res = validate_h(datetime.datetime(2011, 1, 1, x))
            self.assertEqual(res, x in valids)
        
        edge = crontab(hour=0)
        self.assertTrue(edge(datetime.datetime(2011, 1, 1, 0, 0)))
        self.assertFalse(edge(datetime.datetime(2011, 1, 1, 12, 0)))
    
    def test_crontab_minute(self):
        # validates the following minutes
        valids = [0, 1, 4, 6, 8, 9, 12, 18, 24, 30, 36, 42, 48, 54]
        validate_m = crontab(minute='4,8-9,*/6,1')
        
        for x in xrange(60):
            res = validate_m(datetime.datetime(2011, 1, 1, 1, x))
            self.assertEqual(res, x in valids)
    
    def test_crontab_day_of_week(self):
        # validates the following days of week
        # jan, 1, 2011 is a saturday
        valids = [2, 4, 9, 11, 16, 18, 23, 25, 30]
        validate_dow = crontab(day_of_week='0,2')
        
        for x in xrange(1, 32):
            res = validate_dow(datetime.datetime(2011, 1, x))
            self.assertEqual(res, x in valids)
    
    def test_crontab_all_together(self):
        # jan 1, 2011 is a saturday
        # may 1, 2011 is a sunday
        validate = crontab(
            month='1,5',
            day='1,4,7',
            day_of_week='0,6',
            hour='*/4',
            minute='1-5,10-15,50'
        )
        
        self.assertTrue(validate(datetime.datetime(2011, 5, 1, 4, 11)))
        self.assertTrue(validate(datetime.datetime(2011, 5, 7, 20, 50)))
        self.assertTrue(validate(datetime.datetime(2011, 1, 1, 0, 1)))
        
        # fails validation on month
        self.assertFalse(validate(datetime.datetime(2011, 6, 4, 4, 11)))
        
        # fails validation on day
        self.assertFalse(validate(datetime.datetime(2011, 1, 6, 4, 11)))
        
        # fails validation on day_of_week
        self.assertFalse(validate(datetime.datetime(2011, 1, 4, 4, 11)))
        
        # fails validation on hour
        self.assertFalse(validate(datetime.datetime(2011, 1, 1, 1, 11)))
        
        # fails validation on minute
        self.assertFalse(validate(datetime.datetime(2011, 1, 1, 4, 6)))
