import pickle

from huey.exceptions import QueueException


class CommandRegistry(object):
    """
    A simple Registry used to track subclasses of :class:`QueueCommand` - the
    purpose of this registry is to allow translation from queue messages to
    command classes, and vice-versa.
    """
    
    _registry = {}
    _periodic_commands = []
    
    message_template = '%(TASK_ID)s:%(CLASS)s:%(TIME)s:%(DATA)s'

    def command_to_string(self, command):
        return '%s.%s' % (command.__module__, command.__name__)
    
    def register(self, command_class):
        klass_str = self.command_to_string(command_class)
        
        if klass_str not in self._registry:
            self._registry[klass_str] = command_class
            
            # store an instance in a separate list of periodic commands
            if hasattr(command_class, 'validate_datetime'):
                self._periodic_commands.append(command_class())

    def unregister(self, command_class):
        klass_str = self.command_to_string(command_class)
        
        if klass_str in self._registry:
            del(self._registry[str(command_class)])
            
            for command in self._periodic_commands:
                if isinstance(command, command_class):
                    self._periodic_commands.remove(command)
    
    def __contains__(self, command_class):
        return str(command_class) in self._registry

    def get_message_for_command(self, command):
        """Convert a command object to a message for storage in the queue"""
        return self.message_template % {
            'TASK_ID': command.task_id,
            'CLASS': self.command_to_string(type(command)),
            'TIME': pickle.dumps(command.execute_time),
            'DATA': pickle.dumps(command.get_data())
        }

    def get_command_for_message(self, msg):
        """Convert a message from the queue into a command"""
        # parse out the pieces from the enqueued message
        task_id, klass_str, execute_time, data = msg.split(':', 3)
        
        klass = self._registry.get(klass_str)
        if not klass:
            raise QueueException, '%s not found in CommandRegistry' % klass_str
        
        return klass(pickle.loads(str(data)), task_id, pickle.loads(execute_time))
    
    def get_periodic_commands(self):
        return self._periodic_commands


registry = CommandRegistry()
