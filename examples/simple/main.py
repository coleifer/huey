import os
if os.environ.get('WORKER_CLASS') in ('greenlet', 'gevent'):
    print('Monkey-patching for gevent.')
    from gevent import monkey; monkey.patch_all()
import sys

from config import huey
from tasks import add


if __name__ == '__main__':
    if sys.version_info[0] == 2:
        input = raw_input

    print('Huey Demo -- adds two numbers.')
    a = int(input('a = '))
    b = int(input('b = '))
    result = add(a, b)
    print('Result:')
    print(result.get(True))
