.. _imports:

Understanding how tasks are imported
====================================

Behind-the-scenes when you decorate a function with :py:meth:`~Huey.task` or
:py:meth:`~Huey.periodic_task`, the function registers itself with an in-memory
registry. When a task function is called, a reference is put into the queue,
along with the arguments the function was called with, etc. The message is then
read by the consumer, and the task function is looked-up in the consumer's
registry.  Because of the way this works, it is strongly recommended
that **all decorated functions be imported when the consumer starts up**.

.. note::
    If a task is not recognized, the consumer will raise a
    :py:class:`HueyException`.

The consumer is executed with a single required parameter -- the import path to
a :py:class:`Huey` object.  It will import the Huey instance along with
anything else in the module -- thus you must be sure **imports of your tasks
occur with the import of the Huey object**.

Suggested organization of code
------------------------------

Generally, I structure things like this, which makes it very easy to avoid
circular imports.

* ``config.py``, the module containing the :py:class:`Huey` object.

  .. code-block:: python

      # config.py
      from huey import RedisHuey

      huey = RedisHuey('testing')

* ``tasks.py``, the module containing any decorated functions.  Imports the
  ``huey`` object from the ``config.py`` module:

  .. code-block:: python

      # tasks.py
      from config import huey

      @huey.task()
      def add(a, b):
          return a + b

* ``main.py`` / ``app.py``, the "main" module.  Imports both the ``config.py``
  module **and** the ``tasks.py`` module.

  .. code-block:: python

      # main.py
      from config import huey  # import the "huey" object.
      from tasks import add  # import any tasks / decorated functions


      if __name__ == '__main__':
          result = add(1, 2)
          print('1 + 2 = %s' % result.get(blocking=True))

To run the consumer, point it at ``main.huey``, in this way, both the ``huey``
instance **and** the task functions are imported in a centralized location.

.. code-block:: console

    $ huey_consumer.py main.huey
