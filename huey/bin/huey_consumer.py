#!/usr/bin/env python

import datetime
import logging
import optparse
import signal
import sys
import threading
import time
from logging.handlers import RotatingFileHandler

from huey.api import Huey
from huey.exceptions import DataStoreGetException
from huey.exceptions import QueueException
from huey.exceptions import QueueReadException
from huey.exceptions import DataStorePutException
from huey.exceptions import QueueWriteException
from huey.exceptions import ScheduleAddException
from huey.exceptions import ScheduleReadException
from huey.registry import registry
from huey.utils import load_class


logger = logging.getLogger('huey.consumer')


class ConsumerThread(threading.Thread):
    def __init__(self, huey, utc, shutdown):
        self.huey = huey
        self.utc = utc
        self.shutdown = shutdown
        super(ConsumerThread, self).__init__()

    def get_now(self):
        if self.utc:
            return datetime.datetime.utcnow()
        return datetime.datetime.now()

    def on_shutdown(self):
        pass

    def loop(self, now):
        raise NotImplementedError

    def run(self):
        while not self.shutdown.is_set():
            self.loop()
        logger.debug('Thread shutting down')
        self.on_shutdown()

    def enqueue(self, task):
        try:
            self.huey.enqueue(task)
            self.huey.emit_task('enqueued', task)
        except QueueWriteException:
            logger.error('Error enqueueing task: %s' % task)

    def add_schedule(self, task):
        try:
            self.huey.add_schedule(task)
            self.huey.emit_task('scheduled', task)
        except ScheduleAddException:
            logger.error('Error adding task to schedule: %s' % task)

    def is_revoked(self, task, ts):
        try:
            if self.huey.is_revoked(task, ts, peek=False):
                self.huey.emit_task('revoked', task)
                return True
            return False
        except DataStoreGetException:
            logger.error('Error checking if task is revoked: %s' % task)
            return True


class PeriodicTaskThread(ConsumerThread):
    def loop(self, now=None):
        now = now or self.get_now()
        logger.debug('Checking periodic command registry')
        start = time.time()
        for task in registry.get_periodic_tasks():
            if task.validate_datetime(now):
                logger.info('Scheduling %s for execution' % task)
                self.enqueue(task)
        time.sleep(60 - (time.time() - start))


class SchedulerThread(ConsumerThread):
    def read_schedule(self, ts):
        try:
            return self.huey.read_schedule(ts)
        except ScheduleReadException:
            logger.error('Error reading schedule', exc_info=1)
            return []

    def loop(self, now=None):
        now = now or self.get_now()
        start = time.time()

        for task in self.read_schedule(now):
            logger.info('Scheduling %s for execution' % task)
            self.enqueue(task)

        delta = time.time() - start
        if delta < 1:
            time.sleep(1 - (time.time() - start))


class WorkerThread(ConsumerThread):
    def __init__(self, huey, default_delay, max_delay, backoff, utc,
                 shutdown):
        self.delay = self.default_delay = default_delay
        self.max_delay = max_delay
        self.backoff = backoff
        super(WorkerThread, self).__init__(huey, utc, shutdown)

    def loop(self):
        self.check_message()

    def check_message(self):
        logger.debug('Checking for message')
        task = exc_raised = None
        try:
            task = self.huey.dequeue()
        except QueueReadException:
            logger.error('Error reading from queue', exc_info=1)
            exc_raised = True
        except QueueException:
            logger.error('Queue exception', exc_info=1)
            exc_raised = True
        except:
            logger.error('Unknown exception', exc_info=1)
            exc_raised = True

        if task:
            self.delay = self.default_delay
            self.handle_task(task, self.get_now())
        elif exc_raised or self.huey.blocking:
            self.sleep()

    def sleep(self):
        if self.delay > self.max_delay:
            self.delay = self.max_delay

        logger.debug('No messages, sleeping for: %s' % self.delay)
        time.sleep(self.delay)
        self.delay *= self.backoff

    def handle_task(self, task, ts):
        if not self.huey.ready_to_run(task, ts):
            logger.info('Adding %s to schedule' % task)
            self.add_schedule(task)
        elif not self.is_revoked(task, ts):
            self.process_task(task, ts)

    def process_task(self, task, ts):
        try:
            logger.info('Executing %s' % task)
            self.huey.emit_task('started', task)
            self.huey.execute(task)
            self.huey.emit_task('finished', task)
        except DataStorePutException:
            logger.warn('Error storing result', exc_info=1)
        except:
            logger.error('Unhandled exception in worker thread', exc_info=1)
            self.huey.emit_task('error', task, error=True)
            if task.retries:
                self.huey.emit_task('retrying', task)
                self.requeue_task(task, self.get_now())

    def requeue_task(self, task, ts):
        task.retries -= 1
        logger.info('Re-enqueueing task %s, %s tries left' %
                    (task.task_id, task.retries))
        if task.retry_delay:
            delay = datetime.timedelta(seconds=task.retry_delay)
            task.execute_time = ts + delay
            logger.debug('Execute %s at: %s' % (task, task.execute_time))
            self.add_schedule(task)
        else:
            self.enqueue(task)


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

        if not logger.handlers:
            self.setup_logger()

        self._shutdown = threading.Event()

    def create_threads(self):
        self.scheduler_t = SchedulerThread(self.huey, self.utc, self._shutdown)
        self.scheduler_t.name = 'Scheduler'

        self.worker_threads = []
        for i in range(self.workers):
            worker_t = WorkerThread(
                self.huey,
                self.default_delay,
                self.max_delay,
                self.backoff,
                self.utc,
                self._shutdown)
            worker_t.daemon = True
            worker_t.name = 'Worker %d' % (i + 1)
            self.worker_threads.append(worker_t)

        if self.periodic:
            self.periodic_t = PeriodicTaskThread(
                self.huey, self.utc, self._shutdown)
            self.periodic_t.daemon = True
            self.periodic_t.name = 'Periodic Task'
        else:
            self.periodic_t = None

    def setup_logger(self):
        logger.setLevel(self.loglevel)
        formatter = logging.Formatter(
            '%(threadName)s %(asctime)s %(name)s %(levelname)s %(message)s')

        if self.logfile or not logger.handlers:
            handler = None
            if self.logfile:
                handler = RotatingFileHandler(
                    self.logfile, maxBytes=1024*1024, backupCount=3)
            elif self.loglevel < logging.INFO:
                handler = logging.StreamHandler()
            if handler:
                handler.setFormatter(formatter)
                logger.addHandler(handler)

    def start(self):
        logger.info('Starting scheduler thread')
        self.scheduler_t.start()

        logger.info('Starting worker threads')
        for worker in self.worker_threads:
            worker.start()

        if self.periodic:
            logger.info('Starting periodic task scheduler thread')
            self.periodic_t.start()

    def shutdown(self):
        logger.info('Shutdown initiated')
        self._shutdown.set()

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
        logger.info('%d worker threads' % self.workers)

        self.create_threads()
        try:
            self.start()
            # it seems that calling self._shutdown.wait() here prevents the
            # signal handler from executing
            while not self._shutdown.is_set():
                self._shutdown.wait(.1)
        except:
            logger.error('Error', exc_info=1)
            self.shutdown()

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
    parser.add_option('-w', '--workers', dest='workers', type='int',
                      help='worker threads (default=1)', default=1)
    parser.add_option('-t', '--threads', dest='workers', type='int',
                      help='same as "workers"', default=1)
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
        raise

    consumer = Consumer(
        huey_instance,
        options.logfile,
        loglevel,
        options.workers,
        options.periodic,
        options.initial_delay,
        options.backoff,
        options.max_delay,
        options.utc)
    consumer.run()
