import os
import threading
import time
from huey import crontab
from huey.signals import SIGNAL_COMPLETE

from config import huey


def tprint(s, c=32):
    # Helper to print messages from within tasks using color, to make them
    # stand out in examples.
    print('\x1b[1;%sm%s\x1b[0m' % (c, s))


# Tasks used in examples.

@huey.task()
def add(a, b):
    return a + b

@huey.task()
def mul(a, b):
    return a * b


@huey.task()
def slow(n):
    tprint('going to sleep for %s seconds' % n)
    time.sleep(n)
    tprint('finished sleeping for %s seconds' % n)
    return n


# Example task that will fail on its first invocation, but succeed when
# retried. Also shows how to use the `context` parameter, which passes the task
# instance into the decorated function.

@huey.task(retries=1, retry_delay=5, context=True)
def flaky_task(task=None):
    if task is not None and task.retries == 0:
        tprint('flaky task succeeded on retry.')
        return 'succeeded on retry.'
    tprint('flaky task is about to raise an exception.', 31)
    raise Exception('flaky task failed!')


# Pipeline example.

@huey.task()
def add_pipeline(a, b, *nums):
    # Example task that spawns a pipeline of sub-tasks.
    # In an interactive shell, you would call this like:
    # results = add_pipeline(1, 2, 3, 4, 5, 6, 7, 8, 9, 10)
    # print(results.get(blocking=True))
    # [3, 6, 10, 15, 21, 28, 36, 45, 55]
    task = add.s(a, b)
    for num in nums:
        task = task.then(add, num)
    result_group = huey.enqueue(task)
    tprint('enqueued pipeline of add() tasks.')
    return result_group.get(blocking=True)


# Periodic tasks.

@huey.periodic_task(crontab(minute='*/2'))
def every_other_minute():
    tprint('This task runs every 2 minutes.', 35)


@huey.periodic_task(crontab(minute='*/5'))
def every_five_mins():
    tprint('This task runs every 5 minutes.', 34)


# Example of using hooks.

@huey.on_startup()
def startup_hook():
    pid = os.getpid()
    tid = threading.get_ident()
    tprint('process %s, thread %s - startup hook' % (pid, tid))


@huey.on_shutdown()
def shutdown_hook():
    pid = os.getpid()
    tid = threading.get_ident()
    tprint('process %s, thread %s - shutdown hook' % (pid, tid))


# Example of using a signal.

@huey.signal(SIGNAL_COMPLETE)
def on_complete(signal, task, exc=None):
    tprint('received signal [%s] for task [%s]' % (signal, task))
