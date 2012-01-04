from huey.djhuey.decorators import queue_command, periodic_command, crontab


@queue_command
def count_beans(number):
    return 'Counted %s beans' % number

@periodic_command(crontab(minute='*/5'))
def every_five_mins():
    print 'Every five minutes this will be printed by the consumer'
