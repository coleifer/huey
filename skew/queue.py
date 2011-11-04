import datetime
import os
import pickle
import uuid
import sys

from skew.exceptions import QueueException, QueueWriteException, QueueReadException, ResultStoreGetException, ResultStorePutException
from skew.registry import registry
from skew.utils import wrap_exception, EmptyResult


class AsyncResult(object):
    def __init__(self, result_store, task_id):
        self.result_store = result_store
        self.task_id = task_id
        
        self._result = EmptyResult
    
    def get(self):
        if self._result is EmptyResult:
            try:
                res = self.result_store.get(self.task_id)
            except:
                wrap_exception(ResultStoreGetException)
            
            if res is not EmptyResult:
                self._result = pickle.loads(res)
                return self._result
        else:
            return self._result


class Invoker(object):
    """
    The :class:`Invoker` is responsible for reading and writing to the queue
    and executing messages.  It talks to the :class:`CommandRegistry` to load
    up the proper :class:`QueueCommand` for each message
    """
    
    def __init__(self, queue, result_store=None):
        self.queue = queue
        self.result_store = result_store
    
    def write(self, msg):
        self.queue.write(msg)
    
    def enqueue(self, command):
        try:
            self.write(registry.get_message_for_command(command))
        except:
            wrap_exception(QueueWriteException)
        
        if self.result_store:
            return AsyncResult(self.result_store, command.task_id)
    
    def read(self):
        return self.queue.read()
    
    def dequeue(self):
        try:
            msg = self.read()
        except:
            wrap_exception(QueueReadException)
        
        if msg:
            command = registry.get_command_for_message(msg)
            result = command.execute()
            
            if self.result_store:
                deserialized = pickle.dumps(result)
                try:
                    self.result_store.put(command.task_id, deserialized)
                except:
                    wrap_exception(ResultStorePutException)
    
    def flush(self):
        self.queue.flush()
    
    def enqueue_periodic_commands(self, dt=None):
        dt = dt or datetime.datetime.now()
        
        for command in registry.get_periodic_commands():
            if command.validate_datetime(dt):
                self.enqueue(command)


class QueueCommandMetaClass(type):
    def __init__(cls, name, bases, attrs):
        """
        Metaclass to ensure that all command classes are registered
        """
        registry.register(cls)


class QueueCommand(object):
    """
    A class that encapsulates the logic necessary to 'do something' given some
    arbitrary data.  When enqueued with the :class:`Invoker`, it will be
    stored in a queue for out-of-band execution via the consumer.  See also
    the :func:`queue_command` decorator, which can be used to automatically
    execute any function out-of-band.
    
    Example::
    
    class SendEmailCommand(QueueCommand):
        def execute(self):
            data = self.get_data()
            send_email(data['recipient'], data['subject'], data['body'])
    
    invoker.enqueue(
        SendEmailCommand({
            'recipient': 'somebody@spam.com',
            'subject': 'look at this awesome website',
            'body': 'http://youtube.com'
        })
    )
    """
    
    __metaclass__ = QueueCommandMetaClass
    
    def __init__(self, data=None, task_id=None):
        """
        Initialize the command object with a receiver and optional data.  The
        receiver object *must* be a django model instance.
        """
        self.set_data(data)
        self.task_id = task_id or self.create_id()
    
    def create_id(self):
        return str(uuid.uuid4())

    def get_data(self):
        """Called by the Invoker when a command is being enqueued"""
        return self.data

    def set_data(self, data):
        """Called by the Invoker when a command is dequeued"""
        self.data = data

    def execute(self):
        """Execute any arbitary code here"""
        raise NotImplementedError


class PeriodicQueueCommand(QueueCommand):
    def validate_datetime(self, dt):
        """Validate that the command should execute at the given datetime"""
        return False
