import pickle

from huey.exceptions import QueueException


class TaskRegistry(object):
    """
    A simple Registry used to track subclasses of :class:`QueueTask` - the
    purpose of this registry is to allow translation from queue messages to
    task classes, and vice-versa.
    """
    _ignore = ['QueueTask', 'PeriodicQueueTask', 'NewBase']

    def __init__(self):
        self._registry = {}
        self._periodic_tasks = []

    def task_to_string(self, task):
        return '%s' % (task.__name__)

    def register(self, task_class):
        klass_str = self.task_to_string(task_class)
        if klass_str in self._ignore:
            return

        if klass_str not in self._registry:
            self._registry[klass_str] = task_class

            # store an instance in a separate list of periodic tasks
            if hasattr(task_class, 'validate_datetime'):
                self._periodic_tasks.append(task_class)

    def unregister(self, task_class):
        klass_str = self.task_to_string(task_class)

        if klass_str in self._registry:
            del(self._registry[klass_str])

            for task in self._periodic_tasks:
                if isinstance(task, task_class):
                    self._periodic_tasks.remove(task)

    def __contains__(self, klass_str):
        return klass_str in self._registry

    def get_message_for_task(self, task):
        """Convert a task object to a message for storage in the queue"""
        data = task.get_data()
        if data and isinstance(data, tuple) and len(data) == 2:
            args, kwargs = data
            if isinstance(kwargs, dict) and 'task' in kwargs:
                kwargs.pop('task')
                data = (args, kwargs)

        if task.on_complete is not None:
            on_complete = self.get_message_for_task(task.on_complete)
        else:
            on_complete = None

        return pickle.dumps((
            task.task_id,
            self.task_to_string(type(task)),
            task.execute_time,
            task.retries,
            task.retry_delay,
            data,
            on_complete))

    def get_task_class(self, klass_str):
        klass = self._registry.get(klass_str)

        if not klass:
            raise QueueException('%s not found in TaskRegistry' % klass_str)

        return klass

    def get_task_for_message(self, msg):
        """Convert a message from the queue into a task"""
        # parse out the pieces from the enqueued message
        raw = pickle.loads(msg)
        if len(raw) == 7:
            task_id, klass_str, ex_time, retries, delay, data, oc_raw = raw
        elif len(raw) == 6:
            task_id, klass_str, ex_time, retries, delay, data = raw
            oc_raw = None

        klass = self.get_task_class(klass_str)
        on_complete = self.get_task_for_message(oc_raw) if oc_raw else None
        return klass(data, task_id, ex_time, retries, delay, on_complete)

    def get_periodic_tasks(self):
        return [task_class() for task_class in self._periodic_tasks]


registry = TaskRegistry()
