import logging, sys, traceback
from huey.bin.huey_consumer import WorkerThread, SchedulerThread, PeriodicTaskThread,\
        Consumer, run_consumer, logger
from huey.exceptions import *
import redis
import json


class PubSubWorkerThread(WorkerThread):
    def __init__(self, huey, connection, default_delay, max_delay, backoff, utc,
                 shutdown):
        self.connection = connection
        self.delay = self.default_delay = default_delay
        self.max_delay = max_delay
        self.backoff = backoff
        super(PubSubWorkerThread, self).__init__(huey, default_delay, max_delay, backoff, utc, shutdown)

    def publish(self, message):
        self.connection['server'].publish(self.connection['channel'],json.dumps(message))

    def make_message(self, status=None, result=None, task_id=None):
        result = {
                    'status':status,
                    'result':result,
                    'task_id':task_id
                    }
        return result

    def process_task(self, task, ts):
        try:
            logger.info('Executing %s' % task)
            self.publish(self.make_message('Started', task_id=task.task_id))
            task_result = self.huey.execute(task)
            self.publish(self.make_message('Completed', task_result, task.task_id))
        except DataStorePutException:
            logger.warn('Error storing result', exc_info=1)
        except:
            logger.error('Unhandled exception in worker thread', exc_info=1)
            self.publish(self.make_message('Error', traceback.format_exc(), task.task_id))
            if task.retries:
                self.publish(self.make_message('Retrying', task_id=task.task_id))
                self.requeue_task(task, self.get_now())

class PubSubConsumer(Consumer):
    def __init__(self, huey, connection, logfile=None, loglevel=logging.INFO,
                 workers=1, periodic=True, initial_delay=0.1,
                 backoff=1.15, max_delay=10.0, utc=True):
        self.connection = connection # the redis connection to publish with
        super(PubSubConsumer, self).__init__(huey, logfile, loglevel,
                                       workers, periodic,
                                       initial_delay,backoff,
                                       max_delay, utc)

    def create_threads(self):
        self.scheduler_t = SchedulerThread(self.huey, self.utc, self._shutdown)
        self.scheduler_t.name = 'Scheduler'
        self.worker_threads = []
        for i in range(self.workers):
            worker_t = PubSubWorkerThread(
                self.huey,
                self.connection,
                self.default_delay,
                self.max_delay,
                self.backoff,
                self.utc,
                self._shutdown)
            worker_t.daemon = True
            worker_t.name = 'PubSubWorker %d' % (i + 1)
            self.worker_threads.append(worker_t)

        if self.periodic:
            self.periodic_t = PeriodicTaskThread(
                self.huey, self.utc, self._shutdown)
            self.periodic_t.daemon = True
            self.periodic_t.name = 'Periodic Task'
        else:
            self.periodic_t = None

    def shutdown(self):
        super(PubSubConsumer, self).shutdown()


if __name__ == '__main__':
    conn = {'server':redis.Redis(host='localhost', port=6379, db=0),
            'channel':'defaultmssgqueue'
            }
    pubsub_consumer = PubSubConsumer(
        huey_instance,
        conn,
        options.logfile,
        loglevel,
        options.workers,
        options.periodic,
        options.initial_delay,
        options.backoff,
        options.max_delay,
        options.utc)
    run_consumer(pubsub_consumer)
