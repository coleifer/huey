import functools
import sys


if sys.version_info[0] == 2:
    str_type = basestring
else:
    str_type = (bytes, str)

EVENT_CHECKING_PERIODIC = 'checking-periodic'
EVENT_ERROR_DEQUEUEING = 'error-dequeueing'
EVENT_ERROR_ENQUEUEING = 'error-enqueueing'
EVENT_ERROR_INTERNAL = 'error-internal'
EVENT_ERROR_SCHEDULING = 'error-scheduling'
EVENT_ERROR_STORING_RESULT = 'error-storing-result'
EVENT_ERROR_TASK = 'error-task'
EVENT_LOCKED = 'locked'
EVENT_FINISHED = 'finished'
EVENT_RETRYING = 'retrying'
EVENT_REVOKED = 'revoked'
EVENT_SCHEDULED = 'scheduled'
EVENT_SCHEDULING_PERIODIC = 'scheduling-periodic'
EVENT_STARTED = 'started'
EVENT_TIMEOUT = 'timeout'


class Signal(object):
    __slots__ = ('receivers', 'receiver_list')

    def __init__(self):
        self.receivers = set()
        self.receiver_list = []

    def connect(self, receiver, name=None):
        name = name or '%s.%s' % (reciever.__module__, receiver.__name__)
        if name not in self.receivers:
            self.receivers.add(name)
            self.receiver_list.append((name, receiver))
        else:
            raise ValueError('receiver named "%s" already connected.' % name)

    def disconnect(self, receiver=None, name=None):
        if receiver and not name:
            name = '%s.%s' % (receiver.__module__, receiver.__name__)
        if not name:
            raise ValueError('a receiver or a name must be provided.')
        if name not in self.receivers:
            raise ValueError('receiver named %s not found.' % name)
        self.receivers.remove(name)
        self.receiver_list = [(n, r) for n, r in self.reciever_list
                              if n != name]

    def __call__(self, name_or_fn=None):
        # Decorating a function without using parentheses.
        if not isinstance(name_or_fn, str_type):
            self.connect(name_or_fn)
            return name_or_fn

        # Specifying parameters when decorating.
        @functools.wraps(fn)
        def decorator(fn):
            self.connect(fn, name_or_fn)
            return fn
        return decorator

    def send(self, task, *args, **kwargs):
        for _, receiver in self.receiver_list:
            receiver(task, *args, **kwargs)
