from huey import crontab

from app import huey


@huey.task()
def example_task(n):
    # Example task -- prints the following line to the stdout of the
    # consumer process and returns the argument that was passed in (n).
    print('-- RUNNING EXAMPLE TASK: CALLED WITH n=%s --' % n)
    return n


@huey.periodic_task(crontab(minute='*/5'))
def print_every5_minutes():
    # Example periodic task -- this runs every 5 minutes and prints the
    # following line to the stdout of the consumer process.
    print('-- PERIODIC TASK -- THIS RUNS EVERY 5 MINUTES --')
