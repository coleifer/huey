.. _upgrading:

Upgrading
=========

With the release of Huey 0.4, there are a number of changes to the way things
work.  Unfortunately, many of these changes are backwards incompatible as this
was a pretty big rewrite.  What follows is a list of things that changed and
how to upgrade your code.

To see working examples, be sure to check out the two example apps that
ship with huey, or `view the source on GitHub <https://github.com/coleifer/huey/tree/master/examples>`_.

Invoker became Huey
^^^^^^^^^^^^^^^^^^^

Invoker was a terrible name.  It has been renamed to the much-better "Huey",
which serves the same purpose.  :py:class:`Huey` accepts mostly the same args
as ``Invoker`` did, with the exception of the ``task_store`` argument which
has been removed as it was redundant with ``result_store``.

.. code-block:: python

    queue = RedisBlockingQueue(name='foo')
    data_store = RedisDataStore(name='foo')

    # OLD
    invoker = Invoker(queue, data_store)

    # NEW
    huey = Huey(queue, data_store)

Decorators are methods on Huey
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Formerly if you wanted to decorate a function you would import one of the
decorators from ``huey.decorators``.  Instead, these decorators are now
implemented as methods on the :py:class:`Huey` object (:py:meth:`~Huey.task` and
:py:meth:`~Huey.periodic_task`).

.. code-block:: python

    # OLD
    @queue_command(invoker)
    def do_something(a, b, c):
        return a + b + c

    # NEW
    @huey.task()
    def do_something(a, b, c):
        return a + b + c

The arguments are the same, except there is no need to pass in the ``invoker``
object anymore.

* ``queue_command`` became :py:meth:`Huey.task`
* ``periodic_command`` became :py:meth:`Huey.periodic_task`

No more ``BaseConfiguration``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Configuring the consumer used to be a bit obnoxious because of the need to
duplicate information in the ``BaseConfiguration`` subclass that was already
present in your ``Invoker``.  The ``BaseConfiguration`` object is gone -- now
instead of pointing your consumer at the config object, point it at your
application's :py:class:`Huey` instance::

    # OLD
    huey_consumer.py path.to.Configuration

    # NEW
    huey_consumer.py path.to.huey_instance

Options that were formerly hard-coded into the configuration, like threads
and logfile, are now exposed as command-line arguments.

For more information check out the :ref:`consumer docs <consuming-tasks>`.

Simplified Django Settings
^^^^^^^^^^^^^^^^^^^^^^^^^^

The Django settings are now a bit more simplified.  In fact, if you are running
Redis locally, Huey will "just work".  The new huey settings look like this:

.. code-block:: python

    HUEY = {
        'backend': 'huey.backends.redis_backend',  # required.
        'name': 'unique name',
        'connection': {'host': 'localhost', 'port': 6379},

        # Options to pass into the consumer when running ``manage.py run_huey``
        'consumer_options': {'workers': 4},
    }

Additionally, the imports changed.  Now everything is imported from ``djhuey``:

.. code-block:: python

    # NEW
    from huey.djhuey import task, periodic_task, crontab

    @task()
    def some_fn(a, b):
        return a + b

Django task autodiscovery
^^^^^^^^^^^^^^^^^^^^^^^^^

The ``run_huey`` management command no longer auto-imports ``commands.py`` --
instead it will auto-import ``tasks.py``.
