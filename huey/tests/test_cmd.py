from huey.tests.config import test_huey

@test_huey.task()
def test_command_xxx(val):
    return val
