.. _imports:

Understanding how commands are imported
=======================================

.. note::
    If using django, commands are auto-discovered in a manner similar to
    that used by the admin -- the consumer finds modules named ``commands.py``
    in ``INSTALLED_APPS`` and imports them automatically.

Behind-the-scenes when you decorate a function with :py:func:`queue_command` or
:py:func:`periodic_command`, the function registers itself with a centralized
in-memory registry.  When that function is called, a reference is put into the 
queue (among other things), and when that message is consumed
the function is then looked-up in the consumer's registry.  Because of the way this
works, it is strongly recommended that **all decorated functions be imported when 
the consumer starts up**.

.. note::
    As of v0.1.1, if a command is not recognized, huey will try to dynamically
    import it once before throwing a :py:class:`QueueException` for an
    unrecognized command.

The consumer is executed with a single parameter -- a module to load that contains a subclass
of :py:class:`BaseConfiguration`.  It will import the class along with anything
else in the module -- thus you must be sure **imports of your commands
should also occur with the import of the configuration object**.

Suggested organization of code
------------------------------

Generally, I structure things like this, which makes it very easy to avoid
circular imports.  If it looks familiar, that's because it is exactly the way
the project is laid out in the :ref:`getting started <getting-started>` guide.

* ``config.py``, the module containing the configuration -- also a good place
  to instantiate the :py:class:`Invoker` object:
  
  .. code-block:: python
  
      # config.py
      from huey.backends.redis_backend import RedisBlockingQueue
      from huey.bin.config import BaseConfiguration
      from huey.queue import Invoker


      queue = RedisBlockingQueue('test-queue', host='localhost', port=6379)
      invoker = Invoker(queue)


      class Configuration(BaseConfiguration):
          QUEUE = queue

* ``commands.py``, the module containing any decorated functions.  Imports the
  ``invoker`` object from the ``config.py`` module:
  
  .. code-block:: python
  
      # commands.py
      from huey.decorators import queue_command

      from config import invoker # import the invoker we instantiated in config.py

      @queue_command(invoker)
      def count_beans(num):
          print 'Counted %s beans' % num

* ``main.py`` / ``app.py`` / ``whatever.py``, the "main" module.  Imports both the
  ``config.py`` module **and** the ``commands.py`` module.  The key here is that
  when starting up the consumer, we point it at the ``Configuration`` class we
  imported from the config module:
  
  .. code-block:: python
  
      # main.py
      from config import Configuration # import the configuration class
      from commands import count_beans # import any commands


      if __name__ == '__main__':
          beans = raw_input('How many beans? ')
          count_beans(int(beans))
          print 'Enqueued job to count %s beans' % beans

To run the consumer, point it at ``main.Configuration``, in this way everything
gets imported correctly:

.. code-block:: console

    $ huey_consumer.py main.Configuration
