import datetime
import os
import time

from huey.contrib.djhuey import task
finished_tasks = []


@task()
def hardtask():
    time.sleep(10)
    now = datetime.datetime.now()
    path = os.path.join(
        os.path.dirname(__file__),
        'time_%s.txt' % datetime.datetime.strftime(now, '%Y%d%m_%H%M%S'))
    with open(path, 'w') as f:
        f.write('Task done.')

    msg = 'Finished task started on: %s' % \
        datetime.datetime.strftime(now, '%Y-%d-%m %H:%M:%S')

    finished_tasks.append(msg)  # This list works only when
    # 'always_eager' is False ( run synchronously is on )

    print '[DEBUG] Hardtask finished'
    return msg
