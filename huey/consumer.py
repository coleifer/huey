import datetime
import logging
import operator
import os
import signal
import threading
import time
from collections import defaultdict

from multiprocessing import Event as ProcessEvent
from multiprocessing import Process

try:
    import gevent
    from gevent import Greenlet
    from gevent.event import Event as GreenEvent
except ImportError:
    Greenlet = GreenEvent = None

from huey.constants import WORKER_GREENLET
from huey.constants import WORKER_PROCESS
from huey.constants import WORKER_THREAD
from huey.constants import WORKER_TYPES
from huey.exceptions import ConfigurationError
from huey.exceptions import DataStoreGetException
from huey.exceptions import QueueException
from huey.exceptions import QueueReadException
from huey.exceptions import DataStorePutException
from huey.exceptions import QueueWriteException
from huey.exceptions import ScheduleAddException
from huey.exceptions import ScheduleReadException
from huey.registry import registry


EVENT_CHECKING_PERIODIC = 'checking-periodic'
EVENT_ERROR_DEQUEUEING = 'error-dequeueing'
EVENT_ERROR_ENQUEUEING = 'error-enqueueing'
EVENT_ERROR_INTERNAL = 'error-internal'
EVENT_ERROR_SCHEDULING = 'error-scheduling'
EVENT_ERROR_STORING_RESULT = 'error-storing-result'
EVENT_ERROR_TASK = 'error-task'
EVENT_FINISHED = 'finished'
EVENT_RETRYING = 'retrying'
EVENT_REVOKED = 'revoked'
EVENT_SCHEDULED = 'scheduled'
EVENT_SCHEDULING_PERIODIC = 'scheduling-periodic'
EVENT_STARTED = 'started'
EVENT_TIMEOUT = 'timeout'


def to_timestamp(dt):
    if dt:
        return time.mktime(dt.timetuple())

class BaseProcess(object):
    def __init__(self, huey, utc):
        self.huey = huey
        self.utc = utc

    def get_now(self):
        if self.utc:
            return datetime.datetime.utcnow()
        return datetime.datetime.now()

    def get_timestamp(self):
        return time.mktime(self.get_now().timetuple())

    def sleep_for_interval(self, start_ts, nseconds):
        sleep_time = nseconds - (time.time() - start_ts)
        if sleep_time <= 0:
            return
        self._logger.debug('Sleeping for %s' % sleep_time)
        # Recompute time to sleep to improve accuracy in case the process was
        # pre-empted by the kernel while logging.
        sleep_time = nseconds - (time.time() - start_ts)
        if sleep_time > 0:
            time.sleep(sleep_time)

    def enqueue(self, task):
        try:
            self.huey.enqueue(task)
        except QueueWriteException:
            self.huey.emit_task(EVENT_ERROR_ENQUEUEING, task, error=True)
            self._logger.error('Error enqueueing task: %s' % task)
        else:
            self._logger.debug('Enqueued task: %s' % task)

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
        task = None
        exc_raised = True
        try:
            task = self.huey.dequeue()
        except QueueReadException as exc:
            self.huey.emit_status(EVENT_ERROR_DEQUEUEING, error=True)
            self._logger.exception('Error reading from queue')
        except QueueException:
            self.huey.emit_status(EVENT_ERROR_INTERNAL, error=True)
            self._logger.exception('Queue exception')
        except KeyboardInterrupt:
            raise
        except:
            self.huey.emit_status(EVENT_ERROR_DEQUEUEING, error=True)
            self._logger.exception('Unknown exception dequeueing task.')
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
            self.add_schedule(task)
        elif not self.is_revoked(task, ts):
            self.process_task(task, ts)
        else:
            self.huey.emit_task(
                EVENT_REVOKED,
                task,
                timestamp=to_timestamp(ts))
            self._logger.debug('Task %s was revoked, not running' % task)

    def process_task(self, task, ts):
        self.huey.emit_task(EVENT_STARTED, task, timestamp=to_timestamp(ts))
        self._logger.info('Executing %s' % task)
        start = time.time()
        try:
            try:
                self.huey.execute(task)
            finally:
                duration = time.time() - start
                self._logger.debug('Task %s ran in %0.3fs' % (task, duration))
        except DataStorePutException:
            self.huey.emit_task(
                EVENT_ERROR_STORING_RESULT,
                task,
                error=True,
                duration=duration)
            self._logger.exception('Error storing result')
        except KeyboardInterrupt:
            self._logger.info('Received exit signal, task %s did not finish.' %
                              (task.task_id))
        except:
            self.huey.emit_task(
                EVENT_ERROR_TASK,
                task,
                error=True,
                duration=duration)
            self._logger.exception('Unhandled exception in worker thread')
            if task.retries:
                self.requeue_task(task, self.get_now())
        else:
            self.huey.emit_task(
                EVENT_FINISHED,
                task,
                duration=duration,
                timestamp=self.get_timestamp())

    def requeue_task(self, task, ts):
        task.retries -= 1
        self.huey.emit_task(EVENT_RETRYING, task)
        self._logger.info('Re-enqueueing task %s, %s tries left' %
                          (task.task_id, task.retries))
        if task.retry_delay:
            delay = datetime.timedelta(seconds=task.retry_delay)
            task.execute_time = ts + delay
            self.add_schedule(task)
        else:
            self.enqueue(task)

    def add_schedule(self, task):
        self._logger.info('Adding %s to schedule' % task)
        try:
            self.huey.add_schedule(task)
        except ScheduleAddException:
            self.huey.emit_task(EVENT_ERROR_SCHEDULING, task, error=True)
            self._logger.error('Error adding task to schedule: %s' % task)
        else:
            self.huey.emit_task(EVENT_SCHEDULED, task)

    def is_revoked(self, task, ts):
        try:
            if self.huey.is_revoked(task, ts, peek=False):
                return True
            return False
        except DataStoreGetException:
            self.huey.emit_task(EVENT_ERROR_INTERNAL, task, error=True)
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

        if self.periodic and self._counter == self._q:
            self.enqueue_periodic_tasks(now, start)
        else:
            if self.periodic:
                self._counter += 1
            self.sleep_for_interval(start, self.interval)

    def enqueue_periodic_tasks(self, now, start):
        # Sleep the remainder of 60 % Interval so we check the periodic
        # tasks consistently every 60 seconds.
        if self._r:
            self.sleep_for_interval(start, self._r)

        self.huey.emit_status(
            EVENT_CHECKING_PERIODIC,
            timestamp=self.get_timestamp())
        self._logger.debug('Checking periodic tasks')
        self._counter = 0
        for task in self.huey.read_periodic(now):
            self.huey.emit_task(
                EVENT_SCHEDULING_PERIODIC,
                task,
                timestamp=self.get_timestamp())
            self._logger.info('Scheduling periodic task %s.' % task)
            self.enqueue(task)

        # Because we only slept for part of the user-defined interval, now
        # sleep the remainder.
        self.sleep_for_interval(start, self.interval - self._r)
        return True


class Environment(object):
    def get_stop_flag(self):
        raise NotImplementedError

    def create_process(self, runnable, name):
        raise NotImplementedError

    def is_alive(self, proc):
        raise NotImplementedError


class ThreadEnvironment(Environment):
    def get_stop_flag(self):
        return threading.Event()

    def create_process(self, runnable, name):
        t = threading.Thread(target=runnable, name=name)
        t.daemon = True
        return t

    def is_alive(self, proc):
        return proc.isAlive()


class GreenletEnvironment(Environment):
    def get_stop_flag(self):
        return GreenEvent()

    def create_process(self, runnable, name):
        def run_wrapper():
            gevent.sleep()
            runnable()
            gevent.sleep()
        return Greenlet(run=run_wrapper)

    def is_alive(self, proc):
        return not proc.dead


class ProcessEnvironment(Environment):
    def get_stop_flag(self):
        return ProcessEvent()

    def create_process(self, runnable, name):
        p = Process(target=runnable, name=name)
        p.daemon = True
        return p

    def is_alive(self, proc):
        return proc.is_alive()


WORKER_TO_ENVIRONMENT = {
    WORKER_THREAD: ThreadEnvironment,
    WORKER_GREENLET: GreenletEnvironment,
    'gevent': GreenletEnvironment,  # Preserved for backwards-compat.
    WORKER_PROCESS: ProcessEnvironment,
}


class Consumer(object):
    def __init__(self, huey, workers=1, periodic=True, initial_delay=0.1,
                 backoff=1.15, max_delay=10.0, utc=True, scheduler_interval=1,
                 worker_type='thread', check_worker_health=True,
                 health_check_interval=1):

        self._logger = logging.getLogger('huey.consumer')
        if huey.always_eager:
            self._logger.warning('Consumer initialized with Huey instance '
                                 'that has "always_eager" mode enabled. This '
                                 'must be disabled before the consumer can '
                                 'be run.')
        self.huey = huey
        self.workers = workers
        self.periodic = periodic
        self.default_delay = initial_delay
        self.backoff = backoff
        self.max_delay = max_delay
        self.utc = utc
        self.scheduler_interval = max(min(scheduler_interval, 60), 1)
        self.worker_type = worker_type

        # Configure health-check and consumer main-loop attributes.
        self._stop_flag_timeout = 0.1
        self._health_check = check_worker_health
        self._health_check_interval = (float(health_check_interval) /
                                       self._stop_flag_timeout)
        self.__health_check_counter = 0

        # Create the execution environment helper.
        self.environment = self.get_environment(self.worker_type)

        # Create the event used to signal the process should exit.
        self._received_signal = False
        self.stop_flag = self.environment.get_stop_flag()

        # Create the scheduler process (but don't start it yet).
        scheduler = self._create_scheduler()
        self.scheduler = self._create_process(scheduler, 'Scheduler')

        # Create the worker process(es) (also not started yet).
        self.worker_threads = []
        for i in range(workers):
            worker = self._create_worker()
            process = self._create_process(worker, 'Worker-%d' % (i + 1))
            self.worker_threads.append((worker, process))

    def get_environment(self, worker_type):
        if worker_type not in WORKER_TO_ENVIRONMENT:
            raise ValueError('worker_type must be one of %s.' %
                             ', '.join(WORKER_TYPES))
        return WORKER_TO_ENVIRONMENT[worker_type]()

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

    def _create_process(self, process, name):
        def _run():
            try:
                while not self.stop_flag.is_set():
                    process.loop()
            except KeyboardInterrupt:
                pass
            except:
                self._logger.exception('Process %s died!' % name)
        return self.environment.create_process(_run, name)

    def start(self):
        if self.huey.always_eager:
            raise ConfigurationError(
                'Consumer cannot be run with Huey instances where always_eager'
                ' is enabled. Please check your configuration and ensure that'
                ' "huey.always_eager = False".')
        # Log startup message.
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
        for _, worker_process in self.worker_threads:
            worker_process.start()

    def stop(self):
        self.stop_flag.set()
        self._logger.info('Shutting down')

    def run(self):
        self.start()
        timeout = self._stop_flag_timeout
        while True:
            try:
                is_set = self.stop_flag.wait(timeout=timeout)
                time.sleep(timeout)
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

            if self._health_check:
                self.__health_check_counter += 1
                if self.__health_check_counter == self._health_check_interval:
                    self.__health_check_counter = 0
                    self.check_worker_health()

        self._logger.info('Consumer exiting.')

    def check_worker_health(self):
        self._logger.debug('Checking worker health.')
        workers = []
        restart_occurred = False
        for i, (worker, worker_t) in enumerate(self.worker_threads):
            if not self.environment.is_alive(worker_t):
                self._logger.warning('Worker %d died, restarting.' % (i + 1))
                worker = self._create_worker()
                worker_t = self._create_process(worker, 'Worker-%d' % (i + 1))
                worker_t.start()
                restart_occurred = True
            workers.append((worker, worker_t))

        if restart_occurred:
            self.worker_threads = workers
        else:
            self._logger.debug('Workers are up and running.')

        return not restart_occurred

    def _set_signal_handler(self):
        signal.signal(signal.SIGTERM, self._handle_signal)

    def _handle_signal(self, sig_num, frame):
        self._logger.info('Received SIGTERM')
        self._received_signal = True
