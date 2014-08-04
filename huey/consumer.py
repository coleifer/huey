import datetime
import logging
import signal
import threading
import time

from huey.exceptions import DataStoreGetException
from huey.exceptions import QueueException
from huey.exceptions import QueueReadException
from huey.exceptions import DataStorePutException
from huey.exceptions import QueueWriteException
from huey.exceptions import ScheduleAddException
from huey.exceptions import ScheduleReadException
from huey.registry import registry


class ConsumerThread(threading.Thread):
    def __init__(self, huey, utc, shutdown, interval=60):
        self.huey = huey
        self.utc = utc
        self.shutdown = shutdown
        self.interval = interval
        self._logger = logging.getLogger('huey.consumer.ConsumerThread')
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
        self._logger.debug('Thread shutting down')
        self.on_shutdown()

    def enqueue(self, task):
        try:
            self.huey.enqueue(task)
            self.huey.emit_task('enqueued', task)
        except QueueWriteException:
            self._logger.error('Error enqueueing task: %s' % task)

    def add_schedule(self, task):
        try:
            self.huey.add_schedule(task)
            self.huey.emit_task('scheduled', task)
        except ScheduleAddException:
            self._logger.error('Error adding task to schedule: %s' % task)

    def is_revoked(self, task, ts):
        try:
            if self.huey.is_revoked(task, ts, peek=False):
                self.huey.emit_task('revoked', task)
                return True
            return False
        except DataStoreGetException:
            self._logger.error('Error checking if task is revoked: %s' % task)
            return True

    def sleep_for_interval(self, start_ts):
        delta = time.time() - start_ts
        if delta < self.interval:
            time.sleep(self.interval - (time.time() - start_ts))


class PeriodicTaskThread(ConsumerThread):
    def loop(self, now=None):
        now = now or self.get_now()
        self._logger.debug('Checking periodic command registry')
        start = time.time()
        for task in registry.get_periodic_tasks():
            if task.validate_datetime(now):
                self._logger.info('Scheduling %s for execution' % task)
                self.enqueue(task)

        self.sleep_for_interval(start)


class SchedulerThread(ConsumerThread):
    def read_schedule(self, ts):
        try:
            return self.huey.read_schedule(ts)
        except ScheduleReadException:
            self._logger.error('Error reading schedule', exc_info=1)
            return []

    def loop(self, now=None):
        now = now or self.get_now()
        start = time.time()

        for task in self.read_schedule(now):
            self._logger.info('Scheduling %s for execution' % task)
            self.enqueue(task)

        self.sleep_for_interval(start)


class WorkerThread(ConsumerThread):
    def __init__(self, huey, default_delay, max_delay, backoff, utc,
                 shutdown):
        self.delay = self.default_delay = default_delay
        self.max_delay = max_delay
        self.backoff = backoff
        self._logger = logging.getLogger('huey.consumer.WorkerThread')
        super(WorkerThread, self).__init__(huey, utc, shutdown)

    def loop(self):
        self.check_message()

    def check_message(self):
        self._logger.debug('Checking for message')
        task = exc_raised = None
        try:
            task = self.huey.dequeue()
        except QueueReadException:
            self._logger.error('Error reading from queue', exc_info=1)
            exc_raised = True
        except QueueException:
            self._logger.error('Queue exception', exc_info=1)
            exc_raised = True
        except:
            self._logger.error('Unknown exception', exc_info=1)
            exc_raised = True

        if task:
            self.delay = self.default_delay
            self.handle_task(task, self.get_now())
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

    def process_task(self, task, ts):
        try:
            self._logger.info('Executing %s' % task)
            self.huey.emit_task('started', task)
            self.huey.execute(task)
            self.huey.emit_task('finished', task)
        except DataStorePutException:
            self._logger.warn('Error storing result', exc_info=1)
        except:
            self._logger.error('Unhandled exception in worker thread',
                               exc_info=1)
            self.huey.emit_task('error', task, error=True)
            if task.retries:
                self.huey.emit_task('retrying', task)
                self.requeue_task(task, self.get_now())

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


class Consumer(object):
    def __init__(self, huey, workers=1, periodic=True, initial_delay=0.1,
                 backoff=1.15, max_delay=10.0, utc=True, scheduler_interval=1,
                 periodic_task_interval=60):

        self._logger = logging.getLogger('huey.consumer.ConsumerThread')
        self.huey = huey
        self.workers = workers
        self.periodic = periodic
        self.default_delay = initial_delay
        self.backoff = backoff
        self.max_delay = max_delay
        self.utc = utc
        self.scheduler_interval = scheduler_interval
        self.periodic_task_interval = periodic_task_interval

        self.delay = self.default_delay

        self._shutdown = threading.Event()

    def run(self):
        try:
            self.start()
            # it seems that calling self._shutdown.wait() here prevents the
            # signal handler from executing
            while not self._shutdown.is_set():
                self._shutdown.wait(.1)
        except:
            self._logger.error('Error', exc_info=1)
            self.shutdown()

    def start(self):
        self._logger.info('%d worker threads' % self.workers)

        self._set_signal_handler()
        self._log_registered_commands()
        self._create_threads()

        self._logger.info('Starting scheduler thread')
        self.scheduler_t.start()

        self._logger.info('Starting worker threads')
        for worker in self.worker_threads:
            worker.start()

        if self.periodic:
            self._logger.info('Starting periodic task scheduler thread')
            self.periodic_t.start()

    def shutdown(self):
        self._logger.info('Shutdown initiated')
        self._shutdown.set()

    def _handle_signal(self, sig_num, frame):
        self._logger.info('Received SIGTERM')
        self.shutdown()

    def _set_signal_handler(self):
        self._logger.info('Setting signal handler')
        signal.signal(signal.SIGTERM, self._handle_signal)

    def _log_registered_commands(self):
        msg = ['Huey consumer initialized with following commands']
        for command in registry._registry:
            msg.append('+ %s' % command.replace('queuecmd_', ''))
        self._logger.info('\n'.join(msg))

    def _create_threads(self):
        self.scheduler_t = SchedulerThread(
            self.huey,
            self.utc,
            self._shutdown,
            self.scheduler_interval)
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
                self.huey,
                self.utc,
                self._shutdown,
                self.periodic_task_interval)
            self.periodic_t.daemon = True
            self.periodic_t.name = 'Periodic Task'
        else:
            self.periodic_t = None
