class QueueException(Exception):
    pass

class QueueWriteException(QueueException):
    pass

class QueueReadException(QueueException):
    pass

class ResultStoreGetException(QueueException):
    pass

class ResultStorePutException(QueueException):
    pass
