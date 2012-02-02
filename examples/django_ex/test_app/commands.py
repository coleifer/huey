import random
from huey.djhuey.decorators import queue_command, periodic_command, crontab


@queue_command
def count_beans(number):
    return 'Counted %s beans' % number

@periodic_command(crontab(minute='*/5'))
def every_five_mins():
    print 'Every five minutes this will be printed by the consumer'

@queue_command(retries=3, retry_delay=10)
def try_thrice():
    if random.randint(1, 3) == 1:
        print 'OK'
    else:
        print 'About to fail, will retry in 10 seconds'
        raise Exception('Crap something went wrong')
