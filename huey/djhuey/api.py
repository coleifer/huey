import types

from huey.api import crontab
from huey.djhuey import huey


def task(retries=0, retry_delay=0, retries_as_argument=False):
    if type(retries) == types.FunctionType:
        return huey.task()(retries)

    def inner(fn):
        return huey.task(retries, retry_delay, retries_as_argument)(fn)
    return inner

periodic_task = huey.periodic_task
