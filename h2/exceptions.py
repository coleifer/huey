class QueueException(Exception): pass
class ResultStoreException(QueueException): pass
class ScheduleException(QueueException): pass

class ConfigurationError(QueueException): pass

class TaskLockedException(QueueException): pass

class CancelExecution(Exception): pass
class RetryTask(Exception): pass
class TaskException(Exception):
    def __init__(self, metadata, *args):
        self.metadata = metadata
        super(TaskException, self).__init__(*args)

    def __unicode__(self):
        return self.metadata['error']
    __str__ = __unicode__
