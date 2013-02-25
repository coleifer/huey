#!/usr/bin/env python
import datetime
import logging
import os
import Queue
import signal
import sys
import time
import threading
from logging.handlers import RotatingFileHandler

from huey.exceptions import QueueException, QueueReadException, DataStorePutException, QueueWriteException
from huey.queue import Invoker, CommandSchedule
from huey.registry import registry
from huey.utils import load_class

try:
    import multiprocessing
    from huey.queue import MPCommandSchedule
except ImportError:
    multiprocessing = None


class IterableQueueMixin:
    def __iter__(self):
        return self

    def next(self):
        result = self.get()
        if result is StopIteration:
            raise result
        return result

class IterableQueue(IterableQueueMixin, Queue.Queue):
    pass

class BaseConsumer(object):
    def __init__(self, invoker, config):
        self.invoker = invoker
        self.config = config

        self.logfile = config.LOGFILE
        self.loglevel = config.LOGLEVEL

        self.workers = config.THREADS
        self.periodic_commands = config.PERIODIC

        self.default_delay = config.INITIAL_DELAY
        self.backoff_factor = config.BACKOFF
        self.max_delay = config.MAX_DELAY

        self.utc = config.UTC

        # initialize delay
        self.delay = self.default_delay

        self.logger = self.get_logger()

    def get_logger(self):
        log = logging.getLogger('huey.consumer.logger')
        log.setLevel(self.loglevel)

        if not log.handlers and self.logfile:
            handler = RotatingFileHandler(self.logfile, maxBytes=1024*1024, backupCount=3)
            handler.setFormatter(logging.Formatter("%(asctime)s:%(name)s:%(levelname)s:%(message)s"))

            log.addHandler(handler)

        return log

    def get_now(self):
        if self.utc:
            return datetime.datetime.utcnow()
        else:
            return datetime.datetime.now()

    def spawn_thread(self, func, *args, **kwargs):
        t = threading.Thread(target=func, args=args, kwargs=kwargs)
        t.daemon = True
        t.start()
        return t

    def spawn_worker(self, job):
        raise NotImplementedError

    def start_periodic_task_scheduler(self):
        self.logger.info('starting periodic task scheduler thread')
        return self.spawn(self.schedule_periodic_tasks)

    def schedule_periodic_tasks(self):
        while not self._shutdown.is_set():
            start = time.time()
            self.enqueue_periodic_commands(self.get_now())
            time.sleep(60 - (time.time() - start))

    def start_scheduler(self):
        self.logger.info('starting scheduler thread')
        return self.spawn_thread(self.schedule_commands)

    def schedule_commands(self):
        while not self._shutdown.is_set():
            start = time.time()
            self.check_schedule(self.get_now())

            # check schedule once per second
            delta = time.time() - start
            if delta < 1:
                time.sleep(1 - (time.time() - start))

    def check_schedule(self, dt):
        for command in self.schedule.commands():
            if self.schedule.should_run(command, dt):
                self.schedule.remove(command)
                if self.schedule.can_run(command, dt):
                    self.invoker.enqueue(command)

    def enqueue_periodic_commands(self, dt):
        self.logger.debug('enqueueing periodic commands')

        for command in registry.get_periodic_commands():
            if command.validate_datetime(dt):
                if not self.invoker.is_revoked(command, dt, False):
                    self.invoker.enqueue(command)

    def start_message_receiver(self):
        self.logger.info('starting message receiver thread')
        return self.spawn_thread(self.receive_messages)

    def receive_messages(self):
        while not self._shutdown.is_set():
            self.check_message()

    def check_message(self):
        try:
            command = self.invoker.dequeue()
        except QueueReadException:
            self.logger.error('error reading from queue', exc_info=1)
        except QueueException:
            self.logger.error('queue exception', exc_info=1)
        else:
            if not command and not self.invoker.blocking:
                # no new messages and our queue doesn't block, so sleep a bit before
                # checking again
                self.sleep()
            elif command:
                now = self.get_now()
                if not self.schedule.should_run(command, now):
                    self.schedule.add(command)
                elif self.schedule.can_run(command, now):
                    self.process_command(command)

    def process_command(self, command):
        raise NotImplementedError

    def sleep(self):
        if self.delay > self.max_delay:
            self.delay = self.max_delay

        self.logger.debug('no commands, sleeping for: %s' % self.delay)
        time.sleep(self.delay)

        self.delay *= self.backoff_factor

    def start_worker_pool(self):
        self.logger.info('starting worker threadpool')
        return self.spawn_thread(self.worker_pool)

    def worker_pool(self):
        raise NotImplementedError

    def worker(self, command):
        raise NotImplementedError

    def sync_worker(self, command):
        raise NotImplementedError

    def retries_for_command(self, command):
        return command.retries

    def requeue_command(self, command):
        command.retries -= 1
        self.logger.info('re-enqueueing task %s, %s tries left' % (command.task_id, command.retries))
        try:
            if command.retry_delay:
                delay = datetime.timedelta(seconds=command.retry_delay)
                command.execute_time = self.get_now() + delay
                self.schedule.add(command)
            else:
                self.invoker.enqueue(command)
        except QueueWriteException:
            self.logger.error('unable to re-enqueue %s, error writing to backend' % command.task_id)

    def start(self):
        self.load_schedule()

        self.start_scheduler()

        if self.periodic_commands:
            self.start_periodic_task_scheduler()

        self._receiver_t = self.start_message_receiver()
        self._worker_pool_t = self.start_worker_pool()

    def shutdown(self):
        self._shutdown.set()
        self._queue.put(StopIteration)

    def handle_signal(self, sig_num, frame):
        self.logger.info('received SIGTERM, shutting down')
        self.shutdown()

    def set_signal_handler(self):
        self.logger.info('setting signal handler')
        signal.signal(signal.SIGTERM, self.handle_signal)

    def load_schedule(self):
        self.logger.info('loading command schedule')
        self.schedule.load()

    def save_schedule(self):
        self.logger.info('saving command schedule')
        self.schedule.save()

    def log_registered_commands(self):
        msg = ['huey initialized with following commands']
        for command in registry._registry:
            msg.append('+ %s' % command)

        self.logger.info('\n'.join(msg))

    def run_main_loop(self):
        # it seems that calling self._shutdown.wait() here prevents the
        # signal handler from executing
        while not self._shutdown.is_set():
            self._shutdown.wait(.1)
        self.cleanup()

    def cleanup(self):
        pass

    def run(self):
        self.set_signal_handler()

        self.log_registered_commands()

        try:
            self.start()
            self.run_main_loop()
        except:
            self.logger.error('error', exc_info=1)
            self.shutdown()

        self.save_schedule()

        self.logger.info('shutdown...')

class Consumer(BaseConsumer):
    def __init__(self, invoker, config):
        super(Consumer, self).__init__(invoker, config)

        # initialize the command schedule
        self.schedule = CommandSchedule(self.invoker)

        # queue to track messages to be processed
        self._queue = IterableQueue()
        self._pool = threading.BoundedSemaphore(self.workers)

        self._shutdown = threading.Event()

    def spawn_worker(self, job):
        return self.spawn_thread(self.worker, job)

    def process_command(self, command):
        self._pool.acquire()

        self.logger.info('processing: %s' % command)
        self.delay = self.default_delay

        # put the command into the queue for the worker pool
        self._queue.put(command)

        # wait to acknowledge receipt of the command
        self.logger.debug('waiting for receipt of command')
        self._queue.join()

    def worker_pool(self):
        for job in self._queue:
            # spin up a worker with the given job
            self.spawn_worker(job)

            # indicate receipt of the task
            self._queue.task_done()

    def worker(self, command):
        try:
            self.invoker.execute(command)
        except DataStorePutException:
            self.logger.warn('error storing result', exc_info=1)
        except:
            self.logger.error('unhandled exception in worker thread', exc_info=1)
            if command.retries:
                self.requeue_command(command)
        finally:
            self._pool.release()

    def sync_worker(self, command):
        self._pool.acquire()
        self.worker(command)

if multiprocessing:
    import multiprocessing.queues
    class MPIterableQueue(IterableQueueMixin, multiprocessing.queues.JoinableQueue):
        pass

def mp_requeue_command(schedule, command, logger, retries, utc):
    # only one worker should be working on a given task at a time, so I don't *think* there's
    # a need for atomic decrement here...
    retries[command.task_id] -= 1
    logger.info('re-enqueueing task %s, %s tries left' % (command.task_id, retries[command.task_id]))
    try:
        if command.retry_delay:
            delay = datetime.timedelta(seconds=command.retry_delay)
            command.execute_time = (datetime.datetime.utcnow() if utc else datetime.datetime.now()) + delay
            schedule.add(command)
        else:
            schedule.invoker.enqueue(command)
    except QueueWriteException:
        logger.error('unable to re-enqueue %s, error writing to backend' % command.task_id)

def mp_worker(schedule, command, retries, utc, logger=None):
    if not logger:
        logger = logging.getLogger('huey.consumer.logger')
    try:
        schedule.invoker.execute(command)
        del retries[command.task_id]
    except DataStorePutException:
        logger.warn('error storing result', exc_info=1)
    except:
        logger.error('unhandled exception in worker thread', exc_info=1)
        if retries[command.task_id]:
            mp_requeue_command(schedule, command, logger, retries, utc)
        else:
            del retries[command.task_id]

class MPConsumer(BaseConsumer):
    def __init__(self, invoker, config):
        super(MPConsumer, self).__init__(invoker, config)

        # initialize the command schedule
        self.schedule = MPCommandSchedule(self.invoker)

        self._queue = MPIterableQueue()
        self._shutdown = multiprocessing.Event()

        self._manager = multiprocessing.Manager()
        self._retries = self._manager.dict()

        self._pool = multiprocessing.Pool(processes=self.workers)

    def spawn_worker(self, job):
        if job.task_id not in self._retries:
            self._retries[job.task_id] = job.retries
        return self._pool.apply_async(mp_worker, args=[self.schedule, job, self._retries, self.utc])

    def requeue_command(self, command):
        return mp_requeue_command(self.schedule, command, self.logger, self._retries, self.utc)

    def process_command(self, command):
        self.logger.info('processing: %s' % command)
        self.delay = self.default_delay

        # put the command into the queue for the worker pool
        self._queue.put(command)

        # wait to acknowledge receipt of the command
        self.logger.debug('waiting for receipt of command')
        self._queue.join()

    def worker_pool(self):
        for job in self._queue:
            # spin up a worker with the given job
            self.spawn_worker(job)

            # indicate receipt of the task
            self._queue.task_done()

    def sync_worker(self, command):
        if command.task_id not in self._retries:
            self._retries[command.task_id] = command.retries
        return mp_worker(self.schedule, command, self._retries, self.utc, self.logger)

    def retries_for_command(self, command):
        return self._retries[command.task_id]

    def cleanup(self):
        self._pool.terminate()
        self._manager.shutdown()

def err(s):
    print '\033[91m%s\033[0m' % s
    sys.exit(1)

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

if __name__ == '__main__':
    args = sys.argv[1:]

    if len(args) == 0:
        err('Error, missing required parameter config.module')
        sys.exit(1)

    config = load_config(args[0])

    queue = config.QUEUE
    result_store = config.RESULT_STORE
    task_store = config.TASK_STORE
    invoker = Invoker(queue, result_store, task_store)

    consumer = Consumer(invoker, config)
    consumer.run()
