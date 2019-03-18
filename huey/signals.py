import itertools


SIGNAL_CANCELED = 'canceled'
SIGNAL_COMPLETE = 'finished'
SIGNAL_ENQUEUED = 'enqueued'
SIGNAL_ERROR = 'error'
SIGNAL_EXECUTING = 'executing'
SIGNAL_LOCKED = 'locked'
SIGNAL_RETRYING = 'retrying'
SIGNAL_REVOKED = 'revoked'
SIGNAL_SCHEDULED = 'scheduled'


class Signal(object):
    __slots__ = ('receivers',)

    def __init__(self):
        self.receivers = {'any': []}

    def connect(self, receiver, *signals):
        if not signals:
            signals = ('any',)
        for signal in signals:
            self.receivers.setdefault(signal, [])
            self.receivers[signal].append(receiver)

    def disconnect(self, receiver, *signals):
        if not signals:
            signals = ('any',)
        for signal in signals:
            self.receivers[signal].remove(receiver)

    def send(self, signal, task, *args, **kwargs):
        receivers = itertools.chain(self.receivers.get(signal, ()),
                                    self.receivers['any'])
        for receiver in receivers:
            receiver(signal, task, *args, **kwargs)
