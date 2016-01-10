import os
if os.environ.get('WORKER_CLASS') in ('greenlet', 'gevent'):
    print('Monkey-patching for gevent.')
    from gevent import monkey; monkey.patch_all()

from config import huey
from tasks import count_beans


if __name__ == '__main__':
    try: input = raw_input
    except NameError: pass
    beans = input('How many beans? ')
    count_beans(int(beans))
    print('Enqueued job to count %s beans' % beans)
