import random

from huey.api import crontab
from huey.contrib.djhuey import task, periodic_task, db_task


@task('first-queue')
def count_beans(number):
    print('-- counted %s beans --' % number)
    return 'Counted %s beans' % number


@periodic_task(crontab(minute='*/5'))  # If no queue is given, the default queue is used.
def every_five_mins():
    print('Every five minutes this will be printed by the consumer')


@task('second-queue', retries=3, retry_delay=10)
def try_thrice():
    if random.randint(1, 3) == 1:
        print('OK')
    else:
        print('About to fail, will retry in 10 seconds')
        raise Exception('Crap something went wrong')

