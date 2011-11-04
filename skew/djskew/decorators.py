from skew.decorators import queue_command as _queue_command, periodic_command as _periodic_command
from skew.djskew import invoker


def queue_command(fn):
    return _queue_command(invoker)(fn)

def periodic_command(crontab):
    return _periodic_command(invoker, crontab)
