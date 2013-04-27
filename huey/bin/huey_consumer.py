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
from logging.handlers import RotatingFileHandler

from huey.api import Huey
from huey.exceptions import QueueException
from huey.exceptions import QueueReadException
from huey.exceptions import DataStorePutException
from huey.exceptions import QueueWriteException
from huey.registry import registry
from huey.utils import load_class


log = logging.getLogger('huey.consumer.logger')

class IterableQueue(Queue.Queue):
    def __iter__(self):
        return self

    def next(self):
        result = self.get()
        if result is StopIteration:
            raise result
        return result

class ExecuteTask(object):
    def __init__(self, task, timestamp=None):
        self.task = task
        self.timestamp = timestamp

"""
Roles and Communication
=======================

* Timed thread


    - 1/s check to see what needs to run
    - keep track of commands that have been "delayed"
    - commands that always run at certain time
    - EXECUTE (executor inbox)

* Message Receiver Thread

    - DEQUEUE tasks
    - SCHEDULE tasks (timed thread inbox)
    - EXECUTE tasks (executor inbox)

* Executor Thread

    - inbox -> SPAWN WORKERS

* Worker Thread

    - RUN task
    - ENQUEUE task if it fails

"""

class ConsumerThread(threading.Thread):
    def __init__(self, utc, shutdown):
        self.utc = utc
        self.shutdown = shutdown

    def get_now(self):
        if self.use_utc:
            return datetime.datetime.utcnow()
        return datetime.datetime.now()

    def on_shutdown(self):
        pass

    def loop(self):
        raise NotImplementedError

    def run(self):
        while not self.shutdown:
            self.loop()
        self.on_shutdown()

class PeriodicTaskThread(ConsumerThread):
    def __init__(self, executor_inbox, utc, shutdown):
        self.executor_inbox = executor_inbox
        super(PeriodicTaskThread, self).__init__(utc, shutdown)

    def loop(self):
        start = time.time()
        now = self.get_now()
        for task in registry.get_periodic_tasks():
            if task.validate_datetime(now):
                self.executor_inbox.put(ExecuteTask(task, now))
        time.sleep(60 - (time.time() - start))

class SchedulerThread(ConsumerThread):
    def __init__(self, schedule, executor_inbox, utc, shutdown):
        self.schedule = schedule
        self.executor_inbox = executor_inbox
        super(SchedulerThread, self).__init__(utc, shutdown)

    def loop(self):
        start = time.time()
        now = self.get_now()
        for task in self.schedule.tasks():
            if task.execute_time is None or task.execute_time < now:
                self.schedule.remove(command)
                self.executor_inbox.put(ExecuteTask(task, now))
        delta = time.time() - start
        if delta < 1:
            time.sleep(1 - (time.time() - start))

class MessageReceiverThread(ConsumerThread):
    def __init__(self, huey, default_delay, max_delay, backoff, utc, shutdown):
        self.huey = huey
        self.delay = self.default_delay = default_delay
        self.max_delay = max_delay
        self.backoff = backoff
        super(MessageReceiverThread, self).__init__(utc, shutdown)

    def loop(self):
        try:
            task = self.huey.dequeue()
        except QueueReadException:
            self.logger.error('Error reading from queue', exc_info=1)
        except QueueException:
            self.logger.error('Queue exception', exc_info=1)
        else:
            if not task and not self.invoker.blocking:
                # no new messages and our queue doesn't block, so sleep a bit before
                # checking again
                self.sleep()
            elif command:
                now = self.get_now()
                if not self.schedule.should_run(command, now):
                    self.schedule.add(command)
                elif self.schedule.can_run(command, now):
                    self.process_command(command)

    def sleep(self):
        if self.delay > self.max_delay:
            self.delay = self.max_delay

        self.logger.debug('message receiver sleeping for: %s' % self.delay)
        time.sleep(self.delay)

        self.delay *= self.backoff_factor

class ExecutorThread(ConsumerThread):
    def __init__(self, workers, inbox, enqueue, utc, shutdown):
        self.workers = workers
        self.inbox = inbox
        self.pool = threading.BoundedSemaphore(self.workers)
        super(ExecutorThread, self).__init__(enqueue, utc, shutdown)

    def loop(self):
        for message in self.inbox:
            self.pool.acquire()
            worker_t = WorkerThread(enqueue, job)
            #
    def process_command(self, command):
        self._pool.acquire()

        # spin up a worker with the given job
        self.spawn(self.worker, job)

        log.info('processing: %s' % command)
        self.delay = self.default_delay

    def worker(self, command):
        try:
            self.huey.execute(command)
        except DataStorePutException:
            log.warn('error storing result', exc_info=1)
        except:
            log.error('unhandled exception in worker thread', exc_info=1)
            if command.retries:
                self.requeue_command(command)
        finally:
            self._pool.release()

    def requeue_command(self, command):
        command.retries -= 1
        log.info('re-enqueueing task %s, %s tries left' % (command.task_id, command.retries))
        try:
            if command.retry_delay:
                delay = datetime.timedelta(seconds=command.retry_delay)
                command.execute_time = self.get_now() + delay
                self.schedule.add(command)
            else:
                self.huey.enqueue(command)
        except QueueWriteException:
            log.error('unable to re-enqueue %s, error writing to backend' % command.task_id)


class ScheduledTaskThread(ConsumerThread):
    def __init__(self, queue, schedule, huey, utc, shutdown):
        self.queue = queue
        self.schedule = schedule
        super(ScheduledTaskThread, self).__init__(huey, utc, shutdown)

    def loop(self):
        start = time.time()

        # Load any new commands into the schedule
        pass

        for command in self.schedule.commands():
            if self.schedule.should_run(command, dt):
                self.schedule.remove(command)
                if self.schedule.can_run(command, dt):
                    self.huey.enqueue(command)

        # check schedule once per second
        delta = time.time() - start
        if delta < 1:
            time.sleep(1 - (time.time() - start))


class MessageReceiverThread(ConsumerThread):
    def loop(self):
        pass


class Consumer(object):
    def __init__(self, huey, logfile=None, loglevel=logging.INFO,
                 threads=1, periodic_commands=True, initial_delay=0.1,
                 backoff_factor=1.15, max_delay=10.0, utc=True):

        self.huey = huey
        self.logfile = logfile
        self.loglevel = loglevel
        self.threads = threads
        self.periodic_commands = periodic_commands
        self.default_delay = initial_delay
        self.backoff_factor = backoff_factor
        self.max_delay = max_delay
        self.utc = utc

        self.delay = self.default_delay

        self.setup_logger()

        # Pool of workers.
        self._pool = threading.BoundedSemaphore(self.threads)
        self._shutdown = threading.Event()

        self.schedule = CommandSchedule(self.huey)

    def setup_logger(self):
        log.setLevel(self.loglevel)

        if not log.handlers and self.logfile:
            handler = RotatingFileHandler(self.logfile, maxBytes=1024*1024,
                                          backupCount=3)
            handler.setFormatter(logging.Formatter(
                "%(asctime)s:%(name)s:%(levelname)s:%(message)s"))
            log.addHandler(handler)

    def receive_messages(self):
        while not self._shutdown.is_set():
            try:
                command = self.huey.dequeue()
            except QueueReadException:
                log.error('error reading from queue', exc_info=1)
            except QueueException:
                log.error('queue exception', exc_info=1)
            else:
                if not command and not self.huey.blocking:
                    # no new messages and our queue doesn't block, so sleep a bit before
                    # checking again
                    self.sleep()
                elif command:
                    now = self.get_now()
                    if not self.schedule.should_run(command, now):
                        self.schedule.add(command)
                    elif self.schedule.can_run(command, now):
                        self.process_command(command)

    def sleep(self):
        if self.delay > self.max_delay:
            self.delay = self.max_delay

        log.debug('no commands, sleeping for: %s' % self.delay)
        time.sleep(self.delay)

        self.delay *= self.backoff_factor

    def process_command(self, command):
        self._pool.acquire()

        # spin up a worker with the given job
        self.spawn(self.worker, job)

        log.info('processing: %s' % command)
        self.delay = self.default_delay

    def worker(self, command):
        try:
            self.huey.execute(command)
        except DataStorePutException:
            log.warn('error storing result', exc_info=1)
        except:
            log.error('unhandled exception in worker thread', exc_info=1)
            if command.retries:
                self.requeue_command(command)
        finally:
            self._pool.release()

    def requeue_command(self, command):
        command.retries -= 1
        log.info('re-enqueueing task %s, %s tries left' % (command.task_id, command.retries))
        try:
            if command.retry_delay:
                delay = datetime.timedelta(seconds=command.retry_delay)
                command.execute_time = self.get_now() + delay
                self.schedule.add(command)
            else:
                self.huey.enqueue(command)
        except QueueWriteException:
            log.error('unable to re-enqueue %s, error writing to backend' % command.task_id)

    def start(self):
        self.load_schedule()

        log.info('starting scheduler thread')
        self.spawn(self.schedule_commands)

        if self.periodic_commands:
            log.info('starting periodic task scheduler thread')
            self.spawn(self.schedule_periodic_tasks)

        log.info('starting message receiver thread')
        self.spawn(self.receive_messages)

    def shutdown(self):
        self._shutdown.set()

    def handle_signal(self, sig_num, frame):
        log.info('received SIGTERM, shutting down')
        self.shutdown()

    def set_signal_handler(self):
        log.info('setting signal handler')
        signal.signal(signal.SIGTERM, self.handle_signal)

    def load_schedule(self):
        log.info('loading command schedule')
        self.schedule.load()

    def save_schedule(self):
        log.info('saving command schedule')
        self.schedule.save()

    def log_registered_commands(self):
        msg = ['huey initialized with following commands']
        for command in registry._registry:
            msg.append('+ %s' % command)

        log.info('\n'.join(msg))

    def run(self):
        self.set_signal_handler()

        self.log_registered_commands()

        try:
            self.start()

            # it seems that calling self._shutdown.wait() here prevents the
            # signal handler from executing
            while not self._shutdown.is_set():
                self._shutdown.wait(.1)
        except:
            log.error('error', exc_info=1)
            self.shutdown()

        self.save_schedule()

        log.info('shutdown...')

def err(s):
    sys.stderr.write('\033[91m%s\033[0m\n' % s)

def load_config(config):
    config_module, config_obj = config.rsplit('.', 1)
    try:
        __import__(config_module)
        mod = sys.modules[config_module]
    except ImportError:
        err('Unable to import "%s"' % config_module)

    try:
        config = getattr(mod, config_obj)
    except AttributeError:
        err('Missing module-level "%s"' % config_obj)

    return config

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

    consumer = Consumer(huey_instance, config)
    consumer.run()
