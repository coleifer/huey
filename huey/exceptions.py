class HueyException(Exception): pass
class ConfigurationError(HueyException): pass
class TaskLockedException(HueyException): pass

class CancelExecution(Exception): pass
class RetryTask(Exception): pass
class TaskException(Exception):
    def __init__(self, metadata=None, *args):
        self.metadata = metadata or {}
        super(TaskException, self).__init__(*args)

    def __unicode__(self):
        return self.metadata.get('error') or 'unknown error'
    __str__ = __unicode__
