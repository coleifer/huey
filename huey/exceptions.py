class HueyException(Exception): pass
class ConfigurationError(HueyException): pass
class TaskLockedException(HueyException): pass
class ResultTimeout(HueyException): pass
class TaskTimeout(HueyException): pass

class RateLimitExceeded(HueyException):
    def __init__(self, key, delay, retry=True):
        self.key, self.delay, self.retry = key, delay, retry
        if retry:
            msg = 'Rate limit exceeded on "%s", retry in %0.1fs' % (key, delay)
        else:
            msg = 'Rate limit exceeded on "%s"' % key
        super(RateLimitExceeded, self).__init__(msg)

class CancelExecution(Exception):
    def __init__(self, retry=None, *args, **kwargs):
        self.retry = retry
        super(CancelExecution, self).__init__(*args, **kwargs)
class RetryTask(Exception):
    def __init__(self, msg=None, eta=None, delay=None, *args, **kwargs):
        self.eta, self.delay = eta, delay
        super(RetryTask, self).__init__(msg, *args, **kwargs)
class TaskException(Exception):
    def __init__(self, metadata=None, *args):
        self.metadata = metadata or {}
        super(TaskException, self).__init__(*args)

    def __str__(self):
        return self.metadata.get('error') or 'unknown error'
