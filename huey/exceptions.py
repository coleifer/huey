class QueueException(Exception): pass

class QueueWriteException(QueueException): pass
class QueueReadException(QueueException): pass
class QueueRemoveException(QueueException): pass

class DataStoreGetException(QueueException): pass
class DataStorePutException(QueueException): pass
class DataStoreTimeout(QueueException): pass

class ScheduleAddException(QueueException): pass
class ScheduleReadException(QueueException): pass

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
