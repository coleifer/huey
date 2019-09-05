from gevent import monkey; monkey.patch_all()
import gevent

from huey.contrib.mini import MiniHuey


huey = MiniHuey()

# If we want to support scheduling tasks for execution in the future, or for
# periodic execution (e.g. cron), then we need to call `huey.start()` which
# starts a scheduler thread.
huey.start()


@huey.task()
def add(a, b):
    return a + b

res = add(1, 2)
print(res())  # Result is calculated in separate greenlet.

print('Scheduling task for execution in 2 seconds.')
res = add.schedule(args=(10, 20), delay=2)
print(res())

# Stop the scheduler. Not strictly necessary, but a good idea.
huey.stop()
