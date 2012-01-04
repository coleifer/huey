import datetime
import time
from huey.decorators import queue_command, periodic_command, crontab

from config import invoker


@queue_command(invoker)
def count_beans(num):
    return 'Counted %s beans' % num

@periodic_command(invoker, crontab(minute='*/5'))
def every_five_mins():
    print 'Consumer prints this every 5 mins'
