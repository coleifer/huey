class HueyException(Exception): pass
class ConfigurationError(HueyException): pass
class TaskLockedException(HueyException): pass
class ResultTimeout(HueyException): pass

class CancelExecution(Exception):
    def __init__(self, *args, retry=None, **kwargs):
        self.retry = retry
        super(CancelExecution, self).__init__(*args, **kwargs)
class RetryTask(Exception):
    def __init__(self, *args, eta=None, delay=None, **kwargs):
        self.eta, self.delay = eta, delay
        super(RetryTask, self).__init__(*args, **kwargs)
class TaskException(Exception):
    def __init__(self, *args, metadata=None, **kwargs):
        self.metadata = metadata or {}
        super(TaskException, self).__init__(*args, **kwargs)

    def __unicode__(self):
        return self.metadata.get('error') or 'unknown error'
    __str__ = __unicode__
