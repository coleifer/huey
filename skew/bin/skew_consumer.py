import datetime
import logging
import os
import Queue
import signal
import sys
import time
import threading
from logging.handlers import RotatingFileHandler

from skew.exceptions import QueueException, QueueReadException, DataStorePutException
from skew.queue import Invoker
from skew.registry import registry
from skew.utils import load_class


class IterableQueue(Queue.Queue):
    def __iter__(self):
        return self
    
    def next(self):
        result = self.get()
        if result is StopIteration:
            raise result
        return result


class Consumer(object):
    def __init__(self, invoker, config):
        self.invoker = invoker
        self.config = config
        
        self.logfile = config.LOGFILE
        self.loglevel = config.LOGLEVEL
        
        self.threads = config.THREADS
        self.periodic_commands = config.PERIODIC

        self.default_delay = config.INITIAL_DELAY
        self.backoff_factor = config.BACKOFF
        self.max_delay = config.MAX_DELAY
        
        # initialize delay
        self.delay = self.default_delay
        
        self.logger = self.get_logger()
        
        # queue to track messages to be processed
        self._queue = IterableQueue()
        self._pool = threading.BoundedSemaphore(self.threads)
        
        self._shutdown = threading.Event()
    
    def get_logger(self):
        log = logging.getLogger('skew.consumer.logger')
        log.setLevel(self.loglevel)
        
        if not log.handlers and self.logfile:
            handler = RotatingFileHandler(self.logfile, maxBytes=1024*1024, backupCount=3)
            handler.setFormatter(logging.Formatter("%(asctime)s:%(name)s:%(levelname)s:%(message)s"))
            
            log.addHandler(handler)
        
        return log
    
    def spawn(self, func, *args, **kwargs):
        t = threading.Thread(target=func, args=args, kwargs=kwargs)
        t.daemon = True
        t.start()
        return t
    
    def start_scheduler(self):
        self.logger.info('starting scheduler thread')
        return self.spawn(self.schedule_commands)

    def schedule_commands(self):
        while 1:
            start = time.time()
            self.logger.debug('enqueueing periodic commands')
            
            try:
                self.invoker.enqueue_periodic_commands()
            except:
                self.logger.error('error enqueueing periodic commands', exc_info=1)
            
            time.sleep(60 - (time.time() - start))
    
    def start_message_receiver(self):
        self.logger.info('starting message receiver thread')
        return self.spawn(self.receive_messages)
    
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
        
        if not command and not self.invoker.blocking:
            # no new messages and our queue doesn't block, so sleep a bit before
            # checking again
            self.sleep()
        elif command:
            self.process_command(command)
    
    def process_command(self, command):
        self._pool.acquire()
        
        self.logger.info('processing: %s' % command)
        self.delay = self.default_delay
        
        # put the command into the queue for the scheduler
        self._queue.put(command)
        
        # wait to acknowledge receipt of the command
        self.logger.debug('waiting for receipt of command')
        self._queue.join()

    def sleep(self):
        if self.delay > self.max_delay:
            self.delay = self.max_delay
        
        self.logger.debug('no commands, sleeping for: %s' % self.delay)
        time.sleep(self.delay)
        
        self.delay *= self.backoff_factor
    
    def start_worker_pool(self):
        self.logger.info('starting worker threadpool')
        return self.spawn(self.worker_pool)
    
    def worker_pool(self):
        for job in self._queue:
            # spin up a worker with the given job
            self.spawn(self.worker, job)
            
            # indicate receipt of the task
            self._queue.task_done()
    
    def worker(self, command):        
        try:
            self.invoker.execute(command)
        except DataStorePutException:
            self.logger.warn('error storing result', exc_info=1)
        except:
            self.logger.error('unhandled exception in worker thread', exc_info=1)
        finally:
            self._pool.release()
    
    def start(self):
        if self.periodic_commands:
            self.start_scheduler()
        
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

    def log_registered_commands(self):
        msg = ['skew initialized with following commands']
        for command in registry._registry:
            msg.append('+ %s' % command)

        self.logger.info('\n'.join(msg))
    
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
            self.logger.error('error', exc_info=1)
            self.shutdown()
        
        self.logger.info('shutdown...')

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
        parser.print_help()
        err('Error, missing required parameter config.module')
        sys.exit(1)
    
    config = load_config(args[0])
    
    queue = config.QUEUE
    result_store = config.RESULT_STORE
    task_store = config.TASK_STORE
    invoker = Invoker(queue, result_store, task_store)
    
    consumer = Consumer(invoker, config)
    consumer.run()
