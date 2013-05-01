#!/usr/bin/env python

import datetime
import logging
import optparse
import os
import Queue
import signal
import sys
import threading
import time
from collections import namedtuple
from logging.handlers import RotatingFileHandler

from huey.api import Huey
from huey.exceptions import QueueException
from huey.exceptions import QueueReadException
from huey.exceptions import DataStorePutException
from huey.exceptions import QueueWriteException
from huey.registry import registry
from huey.utils import load_class


logger = logging.getLogger('huey.consumer')

class IterableQueue(Queue.Queue):
    def __iter__(self):
        return self

    def next(self):
        result = self.get()
        if result is StopIteration:
            raise result
        return result

ExecuteTask = namedtuple('ExecuteTask', ('task', 'timestamp'))


class ConsumerThread(threading.Thread):
    def __init__(self, utc, shutdown):
        self.utc = utc
        self.shutdown = shutdown
        super(ConsumerThread, self).__init__()

    def get_now(self):
        if self.utc:
            return datetime.datetime.utcnow()
        return datetime.datetime.now()

    def on_shutdown(self):
        pass

    def loop(self):
        raise NotImplementedError

    def run(self):
        while not self.shutdown.is_set():
            self.loop()
        logger.debug('Thread shutting down')
        self.on_shutdown()


class PeriodicTaskThread(ConsumerThread):
    def __init__(self, executor_inbox, utc, shutdown):
        self.executor_inbox = executor_inbox
        super(PeriodicTaskThread, self).__init__(utc, shutdown)

    def loop(self):
        logger.debug('Checking periodic command registry')
        start = time.time()
        now = self.get_now()
        for task in registry.get_periodic_tasks():
            if task.validate_datetime(now):
                logger.info('Scheduling %s for execution' % task)
                self.executor_inbox.put(ExecuteTask(task, now))
        time.sleep(60 - (time.time() - start))


class SchedulerThread(ConsumerThread):
    def __init__(self, huey, executor_inbox, utc, shutdown):
        self.huey = huey
        self.executor_inbox = executor_inbox
        super(SchedulerThread, self).__init__(utc, shutdown)

    def loop(self):
        logger.debug('Checking schedule')
        start = time.time()
        now = self.get_now()
        for task in self.huey.schedule():
            if self.huey.ready_to_run(task, now):
                logger.info('Scheduling %s for execution' % task)
                self.huey.remove_schedule(task)
                self.executor_inbox.put(ExecuteTask(task, now))
        delta = time.time() - start
        if delta < 1:
            time.sleep(1 - (time.time() - start))


class MessageReceiverThread(ConsumerThread):
    def __init__(self, huey, executor_inbox, default_delay, max_delay, backoff, utc, shutdown):
        self.huey = huey
        self.executor_inbox = executor_inbox
        self.delay = self.default_delay = default_delay
        self.max_delay = max_delay
        self.backoff = backoff
        super(MessageReceiverThread, self).__init__(utc, shutdown)

    def loop(self):
        logger.debug('Checking for message')
        try:
            task = self.huey.dequeue()
        except QueueReadException:
            logger.error('Error reading from queue', exc_info=1)
        except QueueException:
            logger.error('Queue exception', exc_info=1)
        else:
            if not task and not self.huey.blocking:
                self.sleep()
            elif task:
                now = self.get_now()
                self.executor_inbox.put(ExecuteTask(task, now))

    def sleep(self):
        if self.delay > self.max_delay:
            self.delay = self.max_delay

        logger.debug('No messages, sleeping for: %s' % self.delay)
        time.sleep(self.delay)
        self.delay *= self.backoff_factor


class ExecutorThread(threading.Thread):
    def __init__(self, inbox, workers, huey):
        self.inbox = inbox
        self.workers = workers
        self.huey = huey
        self.pool = threading.BoundedSemaphore(self.workers)
        super(ExecutorThread, self).__init__()

    def run(self):
        for execute_task in self.inbox:
            task, ts = execute_task
            if not self.huey.ready_to_run(task, ts):
                logger.info('Adding %s to schedule' % task)
                self.huey.add_schedule(task)
            elif not self.huey.is_revoked(task, ts):
                self.process_task(task, ts)
        logger.debug('Finished processing messages')

    def process_task(self, task, ts):
        self.pool.acquire()
        logger.info('Processing: %s' % task)
        worker_t = WorkerThread(self.huey, task, ts, self.pool)
        worker_t.start()


class WorkerThread(threading.Thread):
    def __init__(self, huey, task, ts, pool):
        self.huey = huey
        self.task = task
        self.ts = ts
        self.pool = pool
        super(WorkerThread, self).__init__(name='Worker')

    def run(self):
        try:
            self.huey.execute(self.task)
        except DataStorePutException:
            logger.warn('Error storing result', exc_info=1)
        except:
            logger.error('Unhandled exception in worker thread', exc_info=1)
            if self.task.retries:
                self.requeue_task()
        finally:
            self.pool.release()

    def requeue_task(self):
        task = self.task
        task.retries -= 1
        logger.info('Re-enqueueing task %s, %s tries left' %
                    (task.task_id, task.retries))
        try:
            if task.retry_delay:
                delay = datetime.timedelta(seconds=task.retry_delay)
                task.execute_time = self.ts + delay
                self.huey.add_schedule(task)
            else:
                self.huey.enqueue(task)
        except QueueWriteException:
            logger.error('Unable to re-enqueue %s' % task)


class Consumer(object):
    def __init__(self, huey, logfile=None, loglevel=logging.INFO,
                 workers=1, periodic=True, initial_delay=0.1,
                 backoff=1.15, max_delay=10.0, utc=True):

        self.huey = huey
        self.logfile = logfile
        self.loglevel = loglevel
        self.workers = workers
        self.periodic = periodic
        self.default_delay = initial_delay
        self.backoff = backoff
        self.max_delay = max_delay
        self.utc = utc

        self.delay = self.default_delay

        self.setup_logger()

        self._shutdown = threading.Event()
        self._executor_inbox = IterableQueue()

    def setup_logger(self):
        logger.setLevel(self.loglevel)
        formatter = logging.Formatter(
            '%(threadName)s %(asctime)s %(name)s %(levelname)s %(message)s')

        if self.logfile or not logger.handlers:
            if self.logfile:
                handler = RotatingFileHandler(
                    self.logfile, maxBytes=1024*1024, backupCount=3)
            else:
                handler = logging.StreamHandler()
            handler.setFormatter(formatter)
            logger.addHandler(handler)

    def spawn(self, t, daemon=False):
        t.daemon = daemon
        t.start()

    def start(self):
        logger.info('Starting scheduler thread')
        scheduler_t = SchedulerThread(self.huey, self._executor_inbox,
                                      self.utc, self._shutdown)
        scheduler_t.name = 'Scheduler'
        self.spawn(scheduler_t)

        if self.periodic:
            logger.info('Starting periodic task scheduler thread')
            periodic_t = PeriodicTaskThread(self._executor_inbox, self.utc,
                                        self._shutdown)
            periodic_t.name = 'Periodic Task'
            self.spawn(periodic_t, daemon=True)

        logger.info('Starting message receiver thread')
        message_t = MessageReceiverThread(
            self.huey, self._executor_inbox, self.default_delay, self.max_delay,
            self.backoff, self.utc, self._shutdown)
        message_t.name = 'Message Receiver'
        self.spawn(message_t, daemon=True)

        logger.info('Starting task executor thread')
        executor_t = ExecutorThread(self._executor_inbox, self.workers,
                                    self.huey)
        executor_t.name = 'Executor'
        self.spawn(executor_t)

    def shutdown(self):
        logger.info('Shutdown initiated')
        self._shutdown.set()
        self._executor_inbox.put(StopIteration)

    def handle_signal(self, sig_num, frame):
        logger.info('Received SIGTERM')
        self.shutdown()

    def set_signal_handler(self):
        logger.info('Setting signal handler')
        signal.signal(signal.SIGTERM, self.handle_signal)

    def log_registered_commands(self):
        msg = ['Huey consumer initialized with following commands']
        for command in registry._registry:
            msg.append('+ %s' % command.replace('queuecmd_', ''))
        logger.info('\n'.join(msg))

    def run(self):
        self.set_signal_handler()
        self.log_registered_commands()

        self.huey.load_schedule()
        try:
            self.start()
            # it seems that calling self._shutdown.wait() here prevents the
            # signal handler from executing
            while not self._shutdown.is_set():
                self._shutdown.wait(.1)
        except:
            logger.error('Error', exc_info=1)
            self.shutdown()

        self.huey.save_schedule()
        logger.info('Exiting')

def err(s):
    sys.stderr.write('\033[91m%s\033[0m\n' % s)

def get_option_parser():
    parser = optparse.OptionParser('Usage: %prog [options] path.to.huey_instance')
    parser.add_option('-l', '--logfile', dest='logfile',
                      help='write logs to FILE', metavar='FILE')
    parser.add_option('-v', '--verbose', dest='verbose',
                      help='verbose logging', action='store_true')
    parser.add_option('-q', '--quiet', dest='verbose',
                      help='log exceptions only', action='store_false')
    parser.add_option('-t', '--threads', dest='threads', type='int',
                      help='worker threads (default=1)', default=1)
    parser.add_option('-p', '--periodic', dest='periodic', default=True,
                      help='execute periodic tasks (default=True)',
                      action='store_true')
    parser.add_option('-n', '--no-periodic', dest='periodic',
                      help='do NOT execute periodic tasks',
                      action='store_false')
    parser.add_option('-d', '--delay', dest='initial_delay', type='float',
                      help='initial delay in seconds (default=0.1)',
                      default=0.1)
    parser.add_option('-m', '--max-delay', dest='max_delay', type='float',
                      help='maximum time to wait between polling the queue '
                          '(default=10)',
                      default=10)
    parser.add_option('-b', '--backoff', dest='backoff', type='float',
                      help='amount to backoff delay when no results present '
                          '(default=1.15)',
                      default=1.15)
    parser.add_option('-u', '--utc', dest='utc', action='store_true',
                      help='use UTC time for all tasks (default=True)',
                      default=True)
    parser.add_option('--localtime', dest='utc', action='store_false',
                      help='use local time for all tasks')
    return parser

if __name__ == '__main__':
    parser = get_option_parser()
    options, args = parser.parse_args()

    if options.verbose is None:
        loglevel = logging.INFO
    elif options.verbose:
        loglevel = logging.DEBUG
    else:
        loglevel = logging.ERROR

    if len(args) == 0:
        err('Error:   missing import path to `Huey` instance')
        err('Example: huey_consumer.py app.queue.huey_instance')
        sys.exit(1)

    try:
        huey_instance = load_class(args[0])
    except:
        err('Error importing %s' % args[0])
        sys.exit(2)

    loglevel = logging.INFO if options.verbose else logging.DEBUG
    consumer = Consumer(
        huey_instance,
        options.logfile,
        loglevel,
        options.threads,
        options.periodic,
        options.initial_delay,
        options.backoff,
        options.max_delay,
        options.utc)
    consumer.run()
