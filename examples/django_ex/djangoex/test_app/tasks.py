import time

from huey import crontab
from huey.contrib.djhuey import task, periodic_task, db_task, on_commit_task


def tprint(s, c=32):
    # Helper to print messages from within tasks using color, to make them
    # stand out in examples.
    print('\x1b[1;%sm%s\x1b[0m' % (c, s))


# Tasks used in examples.

@task()
def add(a, b):
    return a + b


@task()
def mul(a, b):
    return a * b


@db_task()  # Opens DB connection for duration of task.
def slow(n):
    tprint('going to sleep for %s seconds' % n)
    time.sleep(n)
    tprint('finished sleeping for %s seconds' % n)
    return n


@task(retries=1, retry_delay=5, context=True)
def flaky_task(task=None):
    if task is not None and task.retries == 0:
        tprint('flaky task succeeded on retry.')
        return 'succeeded on retry.'
    tprint('flaky task is about to raise an exception.', 31)
    raise Exception('flaky task failed!')


# Periodic tasks.

@periodic_task(crontab(minute='*/2'))
def every_other_minute():
    tprint('This task runs every 2 minutes.', 35)


@periodic_task(crontab(minute='*/5'))
def every_five_mins():
    tprint('This task runs every 5 minutes.', 34)


# When this task is called, it will not be enqueued until the active
# transaction commits. If no transaction is active it will enqueue immediately.
# Example:
# with transaction.atomic():
#     rh = after_commit('hello!')
#     time.sleep(5)  # Still not enqueued....
#
# # Now the task is enqueued.
# print(rh.get(True))  # prints "6".
@on_commit_task()
def after_commit(msg):
    tprint(msg, 33)
    return len(msg)
