from skew.backends.base import BaseQueue, BaseDataStore
from skew.utils import EmptyData


class DummyQueue(BaseQueue):
    def __init__(self, *args, **kwargs):
        super(DummyQueue, self).__init__(*args, **kwargs)
        self._queue = []
    
    def write(self, data):
        self._queue.insert(0, data)
    
    def read(self):
        try:
            return self._queue.pop()
        except IndexError:
            return None
    
    def flush(self):
        self._queue = []
    
    def __len__(self):
        return len(self._queue)


class DummyDataStore(BaseDataStore):
    def __init__(self, *args, **kwargs):
        super(DummyDataStore, self).__init__(*args, **kwargs)
        self._results = {}
    
    def put(self, task_id, value):
        self._results[task_id] = value
    
    def get(self, task_id):
        return self._results.pop(task_id, EmptyData)
    
    def flush(self):
        self._results = {}
