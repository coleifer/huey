import datetime
import logging
import os
import signal
import sys
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

from huey.constants import WORKER_GREENLET
from huey.constants import WORKER_PROCESS
from huey.constants import WORKER_THREAD
from huey.constants import WORKER_TYPES
from huey.exceptions import CancelExecution
from huey.exceptions import ConfigurationError
from huey.exceptions import DataStoreGetException
from huey.exceptions import QueueException
from huey.exceptions import QueueReadException
from huey.exceptions import DataStorePutException
from huey.exceptions import QueueWriteException
from huey.exceptions import RetryTask
from huey.exceptions import ScheduleAddException
from huey.exceptions import ScheduleReadException
from huey.exceptions import TaskLockedException
from huey.registry import registry


EVENT_CHECKING_PERIODIC = 'checking-periodic'
EVENT_ERROR_DEQUEUEING = 'error-dequeueing'
EVENT_ERROR_ENQUEUEING = 'error-enqueueing'
EVENT_ERROR_INTERNAL = 'error-internal'
EVENT_ERROR_SCHEDULING = 'error-scheduling'
EVENT_ERROR_STORING_RESULT = 'error-storing-result'
EVENT_ERROR_TASK = 'error-task'
EVENT_LOCKED = 'locked'
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

    def get_utcnow(self):
        return datetime.datetime.utcnow()

    def get_timestamp(self):
        return time.mktime(self.get_utcnow().timetuple())

    def sleep_for_interval(self, start_ts, nseconds):
        sleep_time = nseconds - (time.time() - start_ts)
        if sleep_time <= 0:
            return
        self._logger.debug('Sleeping for %s', sleep_time)
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
            self._logger.exception('Error enqueueing task: %s', task)
        else:
            self._logger.debug('Enqueued task: %s', task)

    def loop(self, now=None):
        raise NotImplementedError


class Worker(BaseProcess):
    def __init__(self, huey, default_delay, max_delay, backoff, utc):
        self.delay = self.default_delay = default_delay
        self.max_delay = max_delay
        self.backoff = backoff
        self._logger = logging.getLogger('huey.consumer.Worker')
        self._pre_execute = huey.pre_execute_hooks.items()
        self._post_execute = huey.post_execute_hooks.items()
        super(Worker, self).__init__(huey, utc)

    def loop(self, now=None):
        task = None
        exc_raised = True
        try:
            task = self.huey.dequeue()
        except QueueReadException:
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

        self._logger.debug('No messages, sleeping for: %s', self.delay)
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
            self._logger.debug('Task %s was revoked, not running', task)

    def process_task(self, task, ts):
        self.huey.emit_task(EVENT_STARTED, task, timestamp=to_timestamp(ts))
        if self._pre_execute:
            try:
                self.run_pre_execute_hooks(task)
            except CancelExecution:
                return

        self._logger.info('Executing %s', task)
        start = time.time()
        exception = None
        task_value = None

        try:
            try:
                task_value = self.huey.execute(task)
            finally:
                duration = time.time() - start
                self._logger.debug('Task %s ran in %0.3fs', task, duration)
        except DataStorePutException:
            self._logger.exception('Error storing result')
            self.huey.emit_task(
                EVENT_ERROR_STORING_RESULT,
                task,
                error=True,
                duration=duration)
        except TaskLockedException as exc:
            self._logger.warning('Task %s could not run, unable to obtain '
                                 'lock.', task.task_id)
            self.huey.emit_task(
                EVENT_LOCKED,
                task,
                error=False,
                duration=duration)
            exception = exc
        except RetryTask:
            if not task.retries:
                self._logger.error('Cannot retry task %s - no retries '
                                   'remaining.', task.task_id)
            exception = True
        except KeyboardInterrupt:
            self._logger.info('Received exit signal, task %s did not finish.',
                              task.task_id)
            return
        except Exception as exc:
            self._logger.exception('Unhandled exception in worker thread')
            self.huey.emit_task(
                EVENT_ERROR_TASK,
                task,
                error=True,
                duration=duration)
            exception = exc
        else:
            self.huey.emit_task(
                EVENT_FINISHED,
                task,
                duration=duration,
                timestamp=self.get_timestamp())

        if self._post_execute:
            self.run_post_execute_hooks(task, task_value, exception)

        if exception is not None and task.retries:
            self.requeue_task(task, self.get_now())

    def run_pre_execute_hooks(self, task):
        self._logger.info('Running pre-execute hooks for %s', task)
        for name, callback in self._pre_execute:
            self._logger.debug('Executing %s pre-execute hook.', name)
            try:
                callback(task)
            except CancelExecution:
                self._logger.info('Execution of %s cancelled by %s.', task,
                                  name)
                raise
            except Exception:
                self._logger.exception('Unhandled exception calling pre-'
                                       'execute hook %s for %s.', name, task)

    def run_post_execute_hooks(self, task, task_value, exception):
        self._logger.info('Running post-execute hooks for %s', task)
        for name, callback in self._post_execute:
            self._logger.debug('Executing %s post-execute hook.', name)
            try:
                callback(task, task_value, exception)
            except Exception as exc:
                self._logger.exception('Unhandled exception calling post-'
                                       'execute hook %s for %s.', name, task)

    def requeue_task(self, task, ts):
        task.retries -= 1
        self.huey.emit_task(EVENT_RETRYING, task)
        self._logger.info('Re-enqueueing task %s, %s tries left',
                          task.task_id, task.retries)
        if task.retry_delay:
            delay = datetime.timedelta(seconds=task.retry_delay)
            task.execute_time = ts + delay
            self.add_schedule(task)
        else:
            self.enqueue(task)

    def add_schedule(self, task):
        self._logger.info('Adding %s to schedule', task)
        try:
            self.huey.add_schedule(task)
        except ScheduleAddException:
            self.huey.emit_task(EVENT_ERROR_SCHEDULING, task, error=True)
            self._logger.error('Error adding task to schedule: %s', task)
        else:
            self.huey.emit_task(EVENT_SCHEDULED, task)

    def is_revoked(self, task, ts):
        try:
            if self.huey.is_revoked(task, ts, peek=False):
                return True
            return False
        except DataStoreGetException:
            self.huey.emit_task(EVENT_ERROR_INTERNAL, task, error=True)
            self._logger.error('Error checking if task is revoked: %s', task)
            return True


class Scheduler(BaseProcess):
    def __init__(self, huey, interval, utc, periodic):
        super(Scheduler, self).__init__(huey, utc)
        self.interval = min(interval, 60)
        self.periodic = periodic
        if periodic:
            # Determine the periodic task interval.
            self._counter = 0
            self._q, self._r = divmod(60, self.interval)
            self._cr = self._r
        self._logger = logging.getLogger('huey.consumer.Scheduler')

    def loop(self, now=None):
        start = time.time()

        try:
            task_list = self.huey.read_schedule(now or self.get_now())
        except ScheduleReadException:
            #self.huey.emit_task(EVENT_ERROR_SCHEDULING, task, error=True)
            self._logger.exception('Error reading from task schedule.')
        else:
            for task in task_list:
                self._logger.info('Scheduling %s for execution', task)
                self.enqueue(task)

        if self.periodic:
            # The scheduler has an interesting property of being able to run at
            # intervals that are not factors of 60. Suppose we ask our
            # scheduler to run every 45 seconds. We still want to schedule
            # periodic tasks once per minute, however. So we use a running
            # remainder to ensure that no matter what interval the scheduler is
            # running at, we still are enqueueing tasks once per minute at the
            # same time.
            if self._counter >= self._q:
                self._counter = 0
                if self._cr:
                    self.sleep_for_interval(start, self._cr)
                if self._r:
                    self._cr += self._r
                    if self._cr >= self.interval:
                        self._cr -= self.interval
                        self._counter -= 1

                self.enqueue_periodic_tasks(now or self.get_now(), start)
            self._counter += 1

        self.sleep_for_interval(start, self.interval)

    def enqueue_periodic_tasks(self, now, start):
        self.huey.emit_status(
            EVENT_CHECKING_PERIODIC,
            timestamp=self.get_timestamp())
        self._logger.debug('Checking periodic tasks')
        for task in self.huey.read_periodic(now):
            self.huey.emit_task(
                EVENT_SCHEDULING_PERIODIC,
                task,
                timestamp=self.get_timestamp())
            self._logger.info('Scheduling periodic task %s.', task)
            self.enqueue(task)

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

        # Create the event used to signal the process should terminate. We'll
        # also store a boolean flag to indicate whether we should restart after
        # the processes are cleaned up.
        self._received_signal = False
        self._restart = False
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
                self._logger.exception('Process %s died!', name)
        return self.environment.create_process(_run, name)

    def start(self):
        if self.huey.always_eager:
            raise ConfigurationError(
                'Consumer cannot be run with Huey instances where always_eager'
                ' is enabled. Please check your configuration and ensure that'
                ' "huey.always_eager = False".')
        # Log startup message.
        self._logger.info('Huey consumer started with %s %s, PID %s',
                          self.workers, self.worker_type, os.getpid())
        self._logger.info('Scheduler runs every %s second(s).',
                          self.scheduler_interval)
        self._logger.info('Periodic tasks are %s.',
                          'enabled' if self.periodic else 'disabled')
        self._logger.info('UTC is %s.', 'enabled' if self.utc else 'disabled')

        self._set_signal_handlers()

        msg = ['The following commands are available:']
        for command in registry._registry:
            msg.append('+ %s' % command.replace('queuecmd_', ''))

        self._logger.info('\n'.join(msg))

        # We'll temporarily ignore SIGINT and SIGHUP (so that it is inherited
        # by the child-processes). Once the child processes are created, we
        # restore the handler.
        original_sigint_handler = signal.signal(signal.SIGINT, signal.SIG_IGN)
        if hasattr(signal, 'SIGHUP'):
            original_sighup_handler = signal.signal(signal.SIGHUP, signal.SIG_IGN)

        self.scheduler.start()
        for _, worker_process in self.worker_threads:
            worker_process.start()

        signal.signal(signal.SIGINT, original_sigint_handler)
        if hasattr(signal, 'SIGHUP'):
            signal.signal(signal.SIGHUP, original_sighup_handler)

    def stop(self, graceful=False):
        self.stop_flag.set()
        if graceful:
            self._logger.info('Shutting down gracefully...')
            try:
                for _, worker_process in self.worker_threads:
                    worker_process.join()
            except KeyboardInterrupt:
                self._logger.info('Received request to shut down now.')
            else:
                self._logger.info('All workers have stopped.')
        else:
            self._logger.info('Shutting down')

    def run(self):
        self.start()
        timeout = self._stop_flag_timeout
        while True:
            try:
                is_set = self.stop_flag.wait(timeout=timeout)
                time.sleep(timeout)
            except KeyboardInterrupt:
                self._logger.info('Received SIGINT')
                self.stop(graceful=True)
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

        if self._restart:
            self._logger.info('Consumer will restart.')
            python = sys.executable
            os.execl(python, python, *sys.argv)
        else:
            self._logger.info('Consumer exiting.')

    def check_worker_health(self):
        self._logger.debug('Checking worker health.')
        workers = []
        restart_occurred = False
        for i, (worker, worker_t) in enumerate(self.worker_threads):
            if not self.environment.is_alive(worker_t):
                self._logger.warning('Worker %d died, restarting.', i + 1)
                worker = self._create_worker()
                worker_t = self._create_process(worker, 'Worker-%d' % (i + 1))
                worker_t.start()
                restart_occurred = True
            workers.append((worker, worker_t))

        if restart_occurred:
            self.worker_threads = workers
        else:
            self._logger.debug('Workers are up and running.')

        if not self.environment.is_alive(self.scheduler):
            self._logger.warning('Scheduler died, restarting.')
            scheduler = self._create_scheduler()
            self.scheduler = self._create_process(scheduler, 'Scheduler')
            self.scheduler.start()
        else:
            self._logger.debug('Scheduler is up and running.')

        return not restart_occurred

    def _set_signal_handlers(self):
        signal.signal(signal.SIGTERM, self._handle_stop_signal)
        if hasattr(signal, 'SIGHUP'):
            signal.signal(signal.SIGHUP, self._handle_restart_signal)

    def _handle_stop_signal(self, sig_num, frame):
        self._logger.info('Received SIGTERM')
        self._received_signal = True
        self._restart = False

    def _handle_restart_signal(self, sig_num, frame):
        self._logger.info('Received SIGHUP, will restart')
        self._received_signal = True
        self._restart = True
