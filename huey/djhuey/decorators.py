from huey.decorators import queue_command as _queue_command, periodic_command as _periodic_command, crontab
from huey.djhuey import invoker


def queue_command(retries=0):
    def inner(fn):
        return _queue_command(invoker, retries)(fn)
    if type(retries) == type(inner):
        return inner(retries)
    return inner

def periodic_command(crontab):
    return _periodic_command(invoker, crontab)
