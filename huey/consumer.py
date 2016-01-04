import datetime
import logging
import os
import signal
import threading
import time

from multiprocessing import Event as ProcessEvent
from multiprocessing import Process

try:
    import gevent
    from gevent import Greenlet
    from gevent.event import Event as GreenEvent
except ImportError:
    Greenlet = GreenEvent = None

from huey.exceptions import DataStoreGetException
from huey.exceptions import QueueException
from huey.exceptions import QueueReadException
from huey.exceptions import DataStorePutException
from huey.exceptions import QueueWriteException
from huey.exceptions import ScheduleAddException
from huey.exceptions import ScheduleReadException
from huey.registry import registry


class BaseProcess(object):
    def __init__(self, huey, utc):
        self.huey = huey
        self.utc = utc

    def get_now(self):
        if self.utc:
            return datetime.datetime.utcnow()
        return datetime.datetime.now()

    def sleep_for_interval(self, start_ts, nseconds):
        delta = time.time() - start_ts
        if delta < nseconds:
            time.sleep(nseconds - (time.time() - start_ts))

    def enqueue(self, task):
        try:
            self.huey.enqueue(task)
        except QueueWriteException:
            self._logger.error('Error enqueueing task: %s' % task)
        else:
            self.huey.emit_task('enqueued', task)

    def loop(self, now=None):
        raise NotImplementedError


class Worker(BaseProcess):
    def __init__(self, huey, default_delay, max_delay, backoff, utc):
        self.delay = self.default_delay = default_delay
        self.max_delay = max_delay
        self.backoff = backoff
        self._logger = logging.getLogger('huey.consumer.Worker')
        super(Worker, self).__init__(huey, utc)

    def loop(self, now=None):
        self._logger.debug('Checking for message')
        task = None
        exc_raised = True
        try:
            task = self.huey.dequeue()
        except QueueReadException as exc:
            self._logger.exception('Error reading from queue')
        except QueueException:
            self._logger.exception('Queue exception')
        except KeyboardInterrupt:
            raise
        except:
            self._logger.exception('Unknown exception')
        else:
            exc_raised = False

        if task:
            self.delay = self.default_delay
            self.handle_task(task, now or self.get_now())
        elif exc_raised or not self.huey.blocking:
            self.sleep()

    def sleep(self):
        if self.delay > self.max_delay:
            self.delay = self.max_delay

        self._logger.debug('No messages, sleeping for: %s' % self.delay)
        time.sleep(self.delay)
        self.delay *= self.backoff

    def handle_task(self, task, ts):
        if not self.huey.ready_to_run(task, ts):
            self._logger.info('Adding %s to schedule' % task)
            self.add_schedule(task)
        elif not self.is_revoked(task, ts):
            self.process_task(task, ts)
        else:
            self._logger.debug('Task %s was revoked, not running' % task)

    def process_task(self, task, ts):
        self._logger.info('Executing %s' % task)
        self.huey.emit_task('started', task)
        try:
            self.huey.execute(task)
        except DataStorePutException:
            self._logger.exception('Error storing result')
        except:
            self._logger.exception('Unhandled exception in worker thread')
            self.huey.emit_task('error', task, error=True)
            if task.retries:
                self.huey.emit_task('retrying', task)
                self.requeue_task(task, self.get_now())
        else:
            self.huey.emit_task('finished', task)

    def requeue_task(self, task, ts):
        task.retries -= 1
        self._logger.info('Re-enqueueing task %s, %s tries left' %
                          (task.task_id, task.retries))
        if task.retry_delay:
            delay = datetime.timedelta(seconds=task.retry_delay)
            task.execute_time = ts + delay
            self._logger.debug('Execute %s at: %s' % (task, task.execute_time))
            self.add_schedule(task)
        else:
            self.enqueue(task)

    def add_schedule(self, task):
        try:
            self.huey.add_schedule(task)
        except ScheduleAddException:
            self._logger.error('Error adding task to schedule: %s' % task)
        else:
            self.huey.emit_task('scheduled', task)

    def is_revoked(self, task, ts):
        try:
            if self.huey.is_revoked(task, ts, peek=False):
                self.huey.emit_task('revoked', task)
                return True
            return False
        except DataStoreGetException:
            self._logger.error('Error checking if task is revoked: %s' % task)
            return True


class Scheduler(BaseProcess):
    def __init__(self, huey, interval, utc, periodic):
        super(Scheduler, self).__init__(huey, utc)
        self.interval = min(interval, 60)
        self.periodic = periodic
        if periodic:
            # Determine the periodic task interval.
            self._q, self._r = divmod(60, self.interval)
            if not self._r:
                self._q -= 1
            self._counter = 0
        self._logger = logging.getLogger('huey.consumer.Scheduler')

    def loop(self, now=None):
        now = now or self.get_now()
        start = time.time()

        for task in self.huey.read_schedule(now):
            self._logger.info('Scheduling %s for execution' % task)
            self.enqueue(task)

        should_sleep = True
        if self.periodic:
            if self._counter == self._q:
                if self._r:
                    self.sleep_for_interval(start, self._r)
                self._logger.debug('Checking periodic tasks')
                self._counter = 0
                for task in self.huey.read_periodic(now):
                    self._logger.info('Scheduling periodic task %s.' % task)
                    self.enqueue(task)
                self.sleep_for_interval(start, self.interval - self._r)
                should_sleep = False
            else:
                self._counter += 1

        if should_sleep:
            self.sleep_for_interval(start, self.interval)


class Environment(object):
    def get_stop_flag(self):
        raise NotImplementedError

    def create_process(self, runnable, name):
        raise NotImplementedError


class ThreadEnvironment(Environment):
    def get_stop_flag(self):
        return threading.Event()

    def create_process(self, runnable, name):
        t = threading.Thread(target=runnable, name=name)
        t.daemon = True
        return t


class GreenletEnvironment(Environment):
    def get_stop_flag(self):
        return GreenEvent()

    def create_process(self, runnable, name):
        def run_wrapper():
            gevent.sleep()
            runnable()
            gevent.sleep()
        return Greenlet(run=run_wrapper)


class ProcessEnvironment(Environment):
    def get_stop_flag(self):
        return ProcessEvent()

    def create_process(self, runnable, name):
        p = Process(target=runnable, name=name)
        p.daemon = True
        return p


worker_to_environment = {
    'thread': ThreadEnvironment,
    'greenlet': GreenletEnvironment,
    'gevent': GreenletEnvironment,  # Same as greenlet.
    'process': ProcessEnvironment,
}


class Consumer(object):
    def __init__(self, huey, workers=1, periodic=True, initial_delay=0.1,
                 backoff=1.15, max_delay=10.0, utc=True, scheduler_interval=1,
                 worker_type='thread'):

        self._logger = logging.getLogger('huey.consumer')
        self.huey = huey
        self.workers = workers
        self.periodic = periodic
        self.default_delay = initial_delay
        self.backoff = backoff
        self.max_delay = max_delay
        self.utc = utc
        self.scheduler_interval = max(min(scheduler_interval, 60), 1)
        self.worker_type = worker_type
        if worker_type not in worker_to_environment:
            raise ValueError('worker_type must be one of %s.' %
                             ', '.join(worker_to_environment))
        else:
            self.environment = worker_to_environment[worker_type]()

        self._received_signal = False
        self.stop_flag = self.environment.get_stop_flag()

        scheduler = self._create_runnable(self._create_scheduler())
        self.scheduler = self.environment.create_process(
            scheduler,
            'Scheduler')

        self.worker_threads = []
        for i in range(workers):
            worker = self._create_runnable(self._create_worker())
            self.worker_threads.append(self.environment.create_process(
                worker,
                'Worker-%d' % (i + 1)))

    def _create_worker(self):
        return Worker(
            huey=self.huey,
            default_delay=self.default_delay,
            max_delay=self.max_delay,
            backoff=self.backoff,
            utc=self.utc)

    def _create_scheduler(self):
        return Scheduler(
            huey=self.huey,
            interval=self.scheduler_interval,
            utc=self.utc,
            periodic=self.periodic)

    def _create_runnable(self, consumer_process):
        def _run():
            try:
                while not self.stop_flag.is_set():
                    consumer_process.loop()
            except KeyboardInterrupt:
                pass
        return _run

    def start(self):
        self._logger.info('Huey consumer started with %s %s, PID %s' % (
            self.workers,
            self.worker_type,
            os.getpid()))
        self._logger.info('Scheduler runs every %s seconds.' % (
            self.scheduler_interval))
        self._logger.info('Periodic tasks are %s.' % (
            'enabled' if self.periodic else 'disabled'))

        self._set_signal_handler()

        msg = ['The following commands are available:']
        for command in registry._registry:
            msg.append('+ %s' % command.replace('queuecmd_', ''))
        self._logger.info('\n'.join(msg))

        self.scheduler.start()
        for worker in self.worker_threads:
            worker.start()

    def stop(self):
        self.stop_flag.set()
        self._logger.info('Shutting down')

    def run(self):
        self.start()
        while True:
            try:
                is_set = self.stop_flag.wait(timeout=0.1)
                time.sleep(0.1)
            except KeyboardInterrupt:
                self.stop()
            except:
                self._logger.exception('Error in consumer.')
                self.stop()
            else:
                if self._received_signal:
                    self.stop()
                if self.stop_flag.is_set():
                    break
        self._logger.info('Consumer exiting.')

    def _set_signal_handler(self):
        signal.signal(signal.SIGTERM, self._handle_signal)

    def _handle_signal(self, sig_num, frame):
        self._logger.info('Received SIGTERM')
        self._received_signal = True
