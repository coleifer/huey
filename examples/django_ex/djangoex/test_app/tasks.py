import random
from huey.contrib.djhuey import task, periodic_task, crontab, db_task


@task()
def count_beans(number):
    print('-- counted %s beans --' % number)
    return 'Counted %s beans' % number

@periodic_task(crontab(minute='*/5'))
def every_five_mins():
    print('Every five minutes this will be printed by the consumer')

@task(retries=3, retry_delay=10)
def try_thrice():
    if random.randint(1, 3) == 1:
        print('OK')
    else:
        print('About to fail, will retry in 10 seconds')
        raise Exception('Crap something went wrong')

@db_task()
def foo(number):
    print('foo(%s)' % number)
