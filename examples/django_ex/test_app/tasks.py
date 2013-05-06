import random
import time
from huey.djhuey.api import crontab
from huey.djhuey.api import periodic_task
from huey.djhuey.api import task


@task
def count_beans(number):
    return 'Counted %s beans' % number

@periodic_task(crontab(minute='*/5'))
def every_five_mins():
    print 'Every five minutes this will be printed by the consumer'

@task(retries=3, retry_delay=10)
def try_thrice():
    if random.randint(1, 3) == 1:
        print 'OK'
    else:
        print 'About to fail, will retry in 10 seconds'
        print int(time.time())
        raise Exception('Crap something went wrong')
