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


class BaseDataStore(object):
    """
    Base implementation for a data store
    """
    def __init__(self, name, **connection):
        """
        Initialize the data store - this happens once when the module is loaded
        """
        self.name = name
        self.connection = connection
    
    def put(self, key, value):
        raise NotImplementedError
    
    def get(self, key):
        raise NotImplementedError
    
    def flush(self):
        raise NotImplementedError
