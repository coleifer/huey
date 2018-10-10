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
    """
    Abstract process run by the consumer. Provides convenience methods for
    things like sleeping for a given amount of time and enqueueing tasks.

    Subclasses should implement the `loop()` method, which is called repeatedly
    until the consumer is shutdown. The `loop()` method's return value is
    ignored, but an unhandled exception will lead to the process shutting down.

    A typical pattern might be::

        class CustomProcess(BaseProcess):
            def loop(self, now=None):
                # Get the current timestamp.
                current_ts = time.time()

                # Perform some action, which may take an arbitrary amount of
                # time.
                do_some_action()

                # Sleep for 60 seconds, with respect to current_ts, so that
                # the whole loop() method repeats every ~60s.
                self.sleep_for_interval(current_ts, 60)

    You will want to ensure that the consumer starts your custom process::

        class MyConsumer(Consumer):
            def start(self):
                # Initialize workers, scheduler, signal handlers, etc.
                super(MyConsumer, self).start()

                # Create custom process and start it.
                custom_impl = CustomProcess(huey=self.huey, utc=self.utc)
                self._custom_proc = self._create_process(custom_impl, 'Custom')
                self._custom_proc.start()

    See also: Consumer._create_process().
    """
    def __init__(self, huey, utc):
        self.huey = huey
        self.utc = utc

    def initialize(self):
        pass

    def get_now(self):
        if self.utc:
            return datetime.datetime.utcnow()
        return datetime.datetime.now()

    def get_utcnow(self):
        return datetime.datetime.utcnow()

    def get_timestamp(self):
        return time.mktime(self.get_utcnow().timetuple())

    def sleep_for_interval(self, start_ts, nseconds):
        """
        Sleep for a given interval with respect to the start timestamp.

        So, if the start timestamp is 1337 and nseconds is 10, the method will
        actually sleep for nseconds - (current_timestamp - start_timestamp). So
        if the current timestamp is 1340, we'll only sleep for 7 seconds (the
        goal being to sleep until 1347, or 1337 + 10).
        """
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
        """
        Convenience method for enqueueing a task.
        """
        try:
            self.huey.enqueue(task)
        except QueueWriteException:
            self.huey.emit_task(EVENT_ERROR_ENQUEUEING, task, error=True)
            self._logger.exception('Error enqueueing task: %s', task)
        else:
            self._logger.debug('Enqueued task: %s', task)

    def loop(self, now=None):
        """
        Process-specific implementation. Called repeatedly for as long as the
        consumer is running. The `now` parameter is currently only used in the
        unit-tests (to avoid monkey-patching datetime / time). Return value is
        ignored, but an unhandled exception will lead to the process exiting.
        """
        raise NotImplementedError


class Worker(BaseProcess):
    """
    Worker implementation.

    Will pull tasks from the queue, executing them or adding them to the
    schedule if they are set to run in the future.
    """
    def __init__(self, huey, default_delay, max_delay, backoff, utc):
        self.delay = self.default_delay = default_delay
        self.max_delay = max_delay
        self.backoff = backoff
        self._logger = logging.getLogger('huey.consumer.Worker')
        self._pre_execute = huey.pre_execute_hooks.items()
        self._post_execute = huey.post_execute_hooks.items()
        super(Worker, self).__init__(huey, utc)

    def initialize(self):
        for name, startup_hook in self.huey.startup_hooks.items():
            self._logger.debug('calling startup hook "%s"', name)
            try:
                startup_hook()
            except Exception as exc:
                self._logger.exception('startup hook "%s" failed', name)

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
        """
        Handle a task that was just read from the queue. There are three
        possible outcomes:

        1. Task is scheduled for the future, add to the schedule.
        2. Task is ready to run, but has been revoked. Discard.
        3. Task is ready to run and not revoked. Execute task.
        """
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
        """
        Execute a task and (optionally) store the return value in result store.

        Unhandled exceptions are caught and logged.
        """
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
            self._logger.info('Executed %s in %0.3fs', task, duration)
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
    """
    Scheduler handles enqueueing tasks when they are scheduled to execute. Note
    that the scheduler does not actually execute any tasks, but simply enqueues
    them so that they can be picked up by the worker processes.

    If periodic tasks are enabled, the scheduler will wake up every 60 seconds
    to enqueue any periodic tasks that should be run.
    """
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
        self._next_loop = time.time()

    def loop(self, now=None):
        current = self._next_loop
        self._next_loop += self.interval
        if self._next_loop < time.time():
            self._logger.info('scheduler skipping iteration to avoid race.')
            return

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
                    self.sleep_for_interval(current, self._cr)
                if self._r:
                    self._cr += self._r
                    if self._cr >= self.interval:
                        self._cr -= self.interval
                        self._counter -= 1

                self.enqueue_periodic_tasks(now or self.get_now(), current)
            self._counter += 1

        self.sleep_for_interval(current, self.interval)

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
    """
    Provide a common interface to the supported concurrent environments.
    """
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
    """
    Consumer sets up and coordinates the execution of the workers and scheduler
    and registers signal handlers.
    """
    def __init__(self, huey, workers=1, periodic=True, initial_delay=0.1,
                 backoff=1.15, max_delay=10.0, utc=True, scheduler_interval=1,
                 worker_type='thread', check_worker_health=True,
                 health_check_interval=1, flush_locks=False):

        self._logger = logging.getLogger('huey.consumer')
        if huey.always_eager:
            self._logger.warning('Consumer initialized with Huey instance '
                                 'that has "always_eager" mode enabled. This '
                                 'must be disabled before the consumer can '
                                 'be run.')
        self.huey = huey
        self.workers = workers  # Number of workers.
        self.periodic = periodic  # Enable periodic task scheduler?
        self.default_delay = initial_delay  # Default queue polling interval.
        self.backoff = backoff  # Exponential backoff factor when queue empty.
        self.max_delay = max_delay  # Maximum interval between polling events.
        self.utc = utc  # Timestamps are considered UTC.

        # Ensure that the scheduler runs at an interval between 1 and 60s.
        self.scheduler_interval = max(min(scheduler_interval, 60), 1)
        self.worker_type = worker_type  # What process model are we using?

        # Configure health-check and consumer main-loop attributes.
        self._stop_flag_timeout = 0.1
        self._health_check = check_worker_health
        self._health_check_interval = float(health_check_interval)

        # Create the execution environment helper.
        self.environment = self.get_environment(self.worker_type)

        # Create the event used to signal the process should terminate. We'll
        # also store a boolean flag to indicate whether we should restart after
        # the processes are cleaned up.
        self._received_signal = False
        self._restart = False
        self._graceful = True
        self.stop_flag = self.environment.get_stop_flag()

        # In the event the consumer was killed while running a task that held
        # a lock, this ensures that all locks are flushed before starting.
        if flush_locks:
            self.flush_locks()

        # Create the scheduler process (but don't start it yet).
        scheduler = self._create_scheduler()
        self.scheduler = self._create_process(scheduler, 'Scheduler')

        # Create the worker process(es) (also not started yet).
        self.worker_threads = []
        for i in range(workers):
            worker = self._create_worker()
            process = self._create_process(worker, 'Worker-%d' % (i + 1))

            # The worker threads are stored as [(worker impl, worker_t), ...].
            # The worker impl is not currently referenced in any consumer code,
            # but it is referenced in the test-suite.
            self.worker_threads.append((worker, process))

    def flush_locks(self):
        self._logger.debug('Flushing locks before starting up.')
        flushed = self.huey.flush_locks()
        if flushed:
            self._logger.warning('Found stale locks: %s' % (
                ', '.join(key for key in flushed)))

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
        """
        Repeatedly call the `loop()` method of the given process. Unhandled
        exceptions in the `loop()` method will cause the process to terminate.
        """
        def _run():
            process.initialize()
            try:
                while not self.stop_flag.is_set():
                    process.loop()
            except KeyboardInterrupt:
                pass
            except:
                self._logger.exception('Process %s died!', name)
        return self.environment.create_process(_run, name)

    def start(self):
        """
        Start all consumer processes and register signal handlers.
        """
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
        for command in self.huey.registry._registry:
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
        """
        Set the stop-flag.

        If `graceful=True`, this method blocks until the workers to finish
        executing any tasks they might be currently working on.
        """
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
        """
        Run the consumer.
        """
        self.start()
        timeout = self._stop_flag_timeout
        health_check_ts = time.time()

        while True:
            try:
                self.stop_flag.wait(timeout=timeout)
            except KeyboardInterrupt:
                self._logger.info('Received SIGINT')
                self.stop(graceful=True)
            except:
                self._logger.exception('Error in consumer.')
                self.stop()
            else:
                if self._received_signal:
                    self.stop(graceful=self._graceful)

            if self.stop_flag.is_set():
                break

            if self._health_check:
                now = time.time()
                if now >= health_check_ts + self._health_check_interval:
                    health_check_ts = now
                    self.check_worker_health()

        if self._restart:
            self._logger.info('Consumer will restart.')
            python = sys.executable
            os.execl(python, python, *sys.argv)
        else:
            self._logger.info('Consumer exiting.')

    def check_worker_health(self):
        """
        Check the health of the worker processes. Workers that have died will
        be replaced with new workers.
        """
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
        signal.signal(signal.SIGINT, signal.default_int_handler)
        if hasattr(signal, 'SIGHUP'):
            signal.signal(signal.SIGHUP, self._handle_restart_signal)

    def _handle_stop_signal(self, sig_num, frame):
        self._logger.info('Received SIGTERM')
        self._received_signal = True
        self._restart = False
        self._graceful = False

    def _handle_restart_signal(self, sig_num, frame):
        self._logger.info('Received SIGHUP, will restart')
        self._received_signal = True
        self._restart = True
