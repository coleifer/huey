from huey.decorators import queue_command
from config import test_invoker

@queue_command(test_invoker)
def test_command_xxx(val):
    return val
