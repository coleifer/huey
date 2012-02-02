import datetime
import random
import time
from huey.decorators import queue_command, periodic_command, crontab

from config import invoker


@queue_command(invoker)
def count_beans(num):
    return 'Counted %s beans' % num

@periodic_command(invoker, crontab(minute='*/5'))
def every_five_mins():
    print 'Consumer prints this every 5 mins'

@queue_command(invoker, retries=3, retry_delay=10)
def try_thrice():
    if random.randint(1, 3) == 1:
        print 'OK'
    else:
        print 'About to fail, will retry in 10 seconds'
        raise Exception('Crap something went wrong')
