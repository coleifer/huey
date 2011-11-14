import datetime
import unittest

from huey.backends.dummy import DummyQueue, DummyDataStore
from huey.decorators import queue_command, periodic_command, crontab
from huey.exceptions import QueueException
from huey.queue import Invoker, QueueCommand, PeriodicQueueCommand, CommandSchedule
from huey.registry import registry
from huey.utils import EmptyData, local_to_utc


queue_name = 'test-queue'
queue = DummyQueue(queue_name)
invoker = Invoker(queue)

res_queue_name = 'test-queue-2'
res_queue = DummyQueue(res_queue_name)
res_store = DummyDataStore(res_queue_name)
task_store = DummyDataStore(res_queue_name)

res_invoker = Invoker(res_queue, res_store, task_store)
res_invoker_nones = Invoker(res_queue, res_store, task_store, store_none=True)

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

@queue_command(res_invoker)
def returns_none():
    return None

@queue_command(res_invoker_nones)
def returns_none2():
    return None

class SkewTestCase(unittest.TestCase):
    def setUp(self):
        global state
        queue.flush()
        state = {}
    
    def test_registration(self):
        self.assertTrue('huey.tests.queue.queuecmd_add' in registry)
        self.assertTrue('huey.tests.queue.queuecmd_add_on_the_hour' in registry)
        self.assertTrue('huey.tests.queue.AddCommand' in registry)
    
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
    
    def test_schedule(self):
        dt = datetime.datetime(2011, 1, 1, 0, 1)
        add('k', 'v')
        self.assertEqual(len(queue), 1)
        
        cmd = invoker.dequeue()
        self.assertEqual(cmd.execute_time, None)
        
        add.schedule(args=('k2', 'v2'), eta=dt)
        self.assertEqual(len(queue), 1)
        cmd = invoker.dequeue()
        self.assertEqual(cmd.execute_time, local_to_utc(dt))
        
        add.schedule(args=('k3', 'v3'), eta=dt, convert_utc=False)
        self.assertEqual(len(queue), 1)
        cmd = invoker.dequeue()
        self.assertEqual(cmd.execute_time, dt)
    
    def test_error_raised(self):
        throw_error()
        
        # no error
        cmd = invoker.dequeue()
        
        # error
        self.assertRaises(BampfException, invoker.execute, cmd)
    
    def test_dequeueing(self):
        res = invoker.dequeue() # no error raised if queue is empty
        self.assertEqual(res, None)
                
        add('k', 'v')
        cmd = invoker.dequeue()
        
        self.assertTrue(isinstance(cmd, QueueCommand))
        self.assertEqual(cmd.get_data(), (('k', 'v'), {}))
    
    def test_execution(self):
        self.assertFalse('k' in state)
        add('k', 'v')
        
        cmd = invoker.dequeue()
        self.assertFalse('k' in state)
        
        invoker.execute(cmd)
        self.assertEqual(state['k'], 'v')
        
        add('k', 'X')
        self.assertEqual(state['k'], 'v')
        
        invoker.execute(invoker.dequeue())
        self.assertEqual(state['k'], 'X')
        
        self.assertRaises(TypeError, invoker.execute, invoker.dequeue())
    
    def test_result_store(self):
        res = add2(1, 2)
        res2 = add2(4, 5)
        res3 = add2(0, 0)
        
        # none have been executed as yet
        self.assertEqual(res.get(), None)
        self.assertEqual(res2.get(), None)
        self.assertEqual(res3.get(), None)

        # execute the first task
        res_invoker.execute(res_invoker.dequeue())
        self.assertEqual(res.get(), 3)
        self.assertEqual(res2.get(), None)
        self.assertEqual(res3.get(), None)
        
        # execute the second task
        res_invoker.execute(res_invoker.dequeue())
        self.assertEqual(res.get(), 3)
        self.assertEqual(res2.get(), 9)
        self.assertEqual(res3.get(), None)
        
        # execute the 3rd, which returns a zero value
        res_invoker.execute(res_invoker.dequeue())
        self.assertEqual(res.get(), 3)
        self.assertEqual(res2.get(), 9)
        self.assertEqual(res3.get(), 0)
    
        # check that it returns None when nothing is present
        res = returns_none()
        self.assertEqual(res.get(), None)
        
        # execute, it will still return None, but underneath it is an EmptyResult
        # indicating its actual result was not persisted
        res_invoker.execute(res_invoker.dequeue())
        self.assertEqual(res.get(), None)
        self.assertEqual(res._result, EmptyData)

        # execute again, this time note that we're pointing at the invoker
        # that *does* accept None as a store-able result
        res = returns_none2()
        self.assertEqual(res.get(), None)

        # it stores None
        res_invoker_nones.execute(res_invoker_nones.dequeue())
        self.assertEqual(res.get(), None)
        self.assertEqual(res._result, None)
    
    def test_task_store(self):
        schedule = CommandSchedule(res_invoker)
        
        dt1 = datetime.datetime(2011, 1, 1, 0, 0)
        dt2 = datetime.datetime(2035, 1, 1, 0, 0)
        
        add2.schedule(args=('k', 'v'), eta=dt1)
        cmd1 = res_invoker.dequeue()
        
        add2.schedule(args=('k2', 'v2'), eta=dt2)
        cmd2 = res_invoker.dequeue()
        
        add2('k3', 'v3')
        cmd3 = res_invoker.dequeue()
        
        # add the command to the schedule
        schedule.add(cmd1)
        self.assertEqual(schedule.commands(), [cmd1])
        
        # cmd1 is in the schedule, cmd2 is not
        self.assertTrue(schedule.is_pending(cmd1))
        self.assertFalse(schedule.is_pending(cmd2))
        
        # multiple adds do not result in the list growing
        schedule.add(cmd1)
        self.assertEqual(schedule.commands(), [cmd1])
        
        # removing a non-existant cmd does not error
        schedule.remove(cmd2)
        
        # add a future-dated command
        schedule.add(cmd2)
        
        # sanity check what should be run
        self.assertTrue(schedule.should_run(cmd1))
        self.assertFalse(schedule.should_run(cmd2))
        self.assertTrue(schedule.should_run(cmd3))
        
        # check remove works
        schedule.remove(cmd1)
        self.assertEqual(schedule.commands(), [cmd2])
        
        # check saving works
        schedule.save()
        schedule._schedule = {}
        self.assertEqual(schedule.commands(), [])
        
        # check loading works
        schedule.load()
        self.assertEqual(schedule.commands(), [cmd2])
        
        schedule.add(cmd1)
        schedule.add(cmd3)
        schedule.save()
        schedule._schedule = {}
        
        schedule.load()
        self.assertEqual(len(schedule.commands()), 3)
        self.assertTrue(cmd1 in schedule.commands())
        self.assertTrue(cmd2 in schedule.commands())
        self.assertTrue(cmd3 in schedule.commands())
