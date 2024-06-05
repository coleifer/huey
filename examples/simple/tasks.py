import os
import threading
import time
from huey import crontab
from huey.signals import *

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

@huey.signal(SIGNAL_INTERRUPTED)
def on_interrupted(signal, task, exc=None):
    tprint('received interrupted task signal for task: %s' % task)


# Example of retrying a task if it is *currently* running.

from huey.constants import EmptyData
from huey.exceptions import RetryTask
@huey.task(context=True)
def hold_on(a, task=None):
    if task is not None and huey.storage.peek_data('hold_on') is not EmptyData:
        print('appears to be running...will retry in 60s')
        raise RetryTask(delay=60)

    huey.storage.put_data('hold_on', '1')
    try:
        print('in task, sleeping for %s' % a)
        time.sleep(a)
    finally:
        huey.storage.pop_data('hold_on')
    return True

# Example of limiting the time a task can run for (10s).

@huey.task()
def limit_time(n):
    s = time.time()
    evt = threading.Event()
    def run_computation():
        for i in range(n):
            # Here we would do some kind of computation, checking our event
            # along the way.
            print('.', end='', flush=True)
            if evt.wait(1):
                print('CANCELED')
                return

        evt.set()

    t = threading.Thread(target=run_computation)
    t.start()

    # Attempt to wait for the thread to finish for a total of 10s.
    for i in range(10):
        t.join(1)

    if not evt.is_set():
        # The thread still hasn't finished -- flag it that it must stop now.
        evt.set()
        t.join()

    print('limit_time() completed in %0.2f' % (time.time() - s))

# Task that blocks CPU, used for testing.

@huey.task()
def slow_cpu():
    for i in range(1000000000):
        j = i % 13331
