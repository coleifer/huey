.. _imports:

Understanding how tasks are imported
====================================

.. note::
    If using django, tasks are auto-discovered in a manner similar to
    that used by the admin -- the consumer finds modules named ``tasks.py``
    in ``INSTALLED_APPS`` and imports them automatically.

Behind-the-scenes when you decorate a function with :py:func:`task` or
:py:func:`periodic_task`, the function registers itself with a centralized
in-memory registry.  When that function is called, a reference is put into the
queue (among other things), and when that message is consumed
the function is then looked-up in the consumer's registry.  Because of the way this
works, it is strongly recommended that **all decorated functions be imported when
the consumer starts up**.

.. note::
    If a task is not recognized, the consumer will throw a :py:class:`QueueException`

The consumer is executed with a single parameter -- a module to load that contains
a :py:class:`Huey` object.  It will import the object along with anything
else in the module -- thus you must be sure **imports of your commands
should also occur with the import of the Huey object**.

Suggested organization of code
------------------------------

Generally, I structure things like this, which makes it very easy to avoid
circular imports.  If it looks familiar, that's because it is exactly the way
the project is laid out in the :ref:`getting started <getting-started>` guide.

* ``config.py``, the module containing the :py:class:`Huey` object.

  .. code-block:: python

      # config.py
      from huey import Huey
      from huey.backends.redis_backend import RedisBlockingQueue
      from huey.backends.redis_backend import RedisDataStore

      queue = RedisBlockingQueue('test-queue', host='localhost', port=6379)
      result_store = RedisDataStore('results', host='localhost', port=6379)

      huey = Huey(queue, result_store=result_store)

* ``tasks.py``, the module containing any decorated functions.  Imports the
  ``huey`` object from the ``config.py`` module:

  .. code-block:: python

      # tasks.py
      from config import huey

      @huey.task()
      def count_beans(num):
          print 'Counted %s beans' % num

* ``main.py`` / ``app.py`` / ``whatever.py``, the "main" module.  Imports both the
  ``config.py`` module **and** the ``tasks.py`` module.  The key here is that
  when starting up the consumer, we point it at the ``huey`` object we
  imported from the config module:

  .. code-block:: python

      # main.py
      from config import huey  # import the "huey" object.
      from tasks import count_beans  # import any tasks / decorated functions


      if __name__ == '__main__':
          beans = raw_input('How many beans? ')
          count_beans(int(beans))
          print 'Enqueued job to count %s beans' % beans

To run the consumer, point it at ``main.huey``, in this way everything
gets imported correctly:

.. code-block:: console

    $ huey_consumer.py main.huey
