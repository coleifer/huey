.. _imports:

Understanding how tasks are imported
====================================

Behind-the-scenes when you decorate a function with :py:meth:`~Huey.task` or
:py:meth:`~Huey.periodic_task`, the function registers itself with a centralized
in-memory registry.  When that function is called, a reference is put into the
queue (along with the arguments the function was called with, etc), and when
that message is consumed, the function is then looked-up in the consumer's
registry.  Because of the way this works, it is strongly recommended
that **all decorated functions be imported when the consumer starts up**.

.. note::
    If a task is not recognized, the consumer will throw a :py:class:`QueueException`

The consumer is executed with a single required parameter -- the import path to
a :py:class:`Huey` object.  It will import the object along with anything
else in the module -- thus you must be sure **imports of your tasks
should also occur with the import of the Huey object**.

Suggested organization of code
------------------------------

Generally, I structure things like this, which makes it very easy to avoid
circular imports.  If it looks familiar, that's because it is exactly the way
the project is laid out in the :ref:`getting started <getting-started>` guide.

* ``config.py``, the module containing the :py:class:`Huey` object.

  .. code-block:: python

      # config.py
      from huey import RedisHuey

      huey = RedisHuey('testing', host='localhost')

* ``tasks.py``, the module containing any decorated functions.  Imports the
  ``huey`` object from the ``config.py`` module:

  .. code-block:: python

      # tasks.py
      from config import huey

      @huey.task()
      def count_beans(num):
          print('Counted %s beans' % num)

* ``main.py`` / ``app.py``, the "main" module.  Imports both the ``config.py``
  module **and** the ``tasks.py`` module.

  .. code-block:: python

      # main.py
      from config import huey  # import the "huey" object.
      from tasks import count_beans  # import any tasks / decorated functions


      if __name__ == '__main__':
          beans = raw_input('How many beans? ')
          count_beans(int(beans))
          print('Enqueued job to count %s beans' % beans)

To run the consumer, point it at ``main.huey``, in this way, both the ``huey``
instance **and** the task functions are imported in a centralized location.

.. code-block:: console

    $ huey_consumer.py main.huey
