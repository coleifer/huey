class BaseQueue(object):
    """
    Base implementation for a Queue, all backends should subclass
    """

    # whether this backend blocks while waiting for new results or should be
    # polled by the consumer
    blocking = False

    def __init__(self, name, **connection):
        """
        Initialize the Queue - this happens once when the module is loaded

        :param name: A string representation of the name for this queue
        :param connection: Connection parameters for the queue
        """
        self.name = name
        self.connection = connection

    def write(self, data):
        """
        Push 'data' onto the queue
        """
        raise NotImplementedError

    def read(self):
        """
        Pop 'data' from the queue, returning None if no data is available --
        an empty queue should not raise an Exception!
        """
        raise NotImplementedError

    def remove(self, data):
        """
        Remove the given data from the queue
        """
        raise NotImplementedError

    def flush(self):
        """
        Delete everything from the queue
        """
        raise NotImplementedError

    def __len__(self):
        """
        Used primarily in tests, but return the number of items in the queue
        """
        raise NotImplementedError


class BaseSchedule(object):
    def __init__(self, name, **connection):
        """
        Initialize the Queue - this happens once when the module is loaded

        :param name: A string representation of the name for this queue
        :param connection: Connection parameters for the queue
        """
        self.name = name
        self.connection = connection

    def add(self, data, ts):
        """
        Add the timestamped data to the task schedule.
        """
        raise NotImplementedError

    def read(self, ts):
        """
        Read scheduled items for the given timestamp
        """
        raise NotImplementedError

    def flush(self):
        """Delete all items in schedule."""
        raise NotImplementedError


class BaseDataStore(object):
    """
    Base implementation for a data store
    """
    def __init__(self, name, **connection):
        """
        Initialize the data store
        """
        self.name = name
        self.connection = connection

    def put(self, key, value):
        raise NotImplementedError

    def peek(self, key):
        raise NotImplementedError

    def get(self, key):
        raise NotImplementedError

    def flush(self):
        raise NotImplementedError


class BaseEventEmitter(object):
    def __init__(self, channel, **connection):
        self.channel = channel
        self.connection = connection

    def emit(self, message):
        raise NotImplementedError


Components = (BaseQueue, BaseDataStore, BaseSchedule, BaseEventEmitter)
