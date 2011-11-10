class QueueException(Exception):
    pass

class QueueWriteException(QueueException):
    pass

class QueueReadException(QueueException):
    pass

class DataStoreGetException(QueueException):
    pass

class DataStorePutException(QueueException):
    pass

class DataStoreTimeout(QueueException):
    pass
