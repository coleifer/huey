.. _django:

Using Huey with Django
======================

Huey comes with special integration for use with the Django framework. This is to accomodate:

1. Configuring Huey via the Django settings module.
2. Running the consumer as a management command.

Apps
----

``huey.contrib.djhuey`` must be included in the ``INSTALLED_APPS`` within the Django settings.py file.

.. code-block:: python

    INSTALLED_APPS = (
        'huey.contrib.djhuey',
        ...

Huey Settings
-------------

.. note::
    Huey settings are optional. If not provided, Huey will default to using Redis running locally.

All configuration is kept in ``settings.HUEY``.  Here are some examples:

Using redis running locally with four worker threads.

.. code-block:: python

    HUEY = {
        'name': 'my-app',

        # Options to pass into the consumer when running ``manage.py run_huey``
        'consumer': {'workers': 4, 'worker_type': 'thread'},
    }

Using redis on a network host with 16 worker greenlets.

.. code-block:: python

    HUEY = {
        'name': 'my-app',
        'connection': {'host': '192.168.1.123', 'port': 6379},

        # Options to pass into the consumer when running ``manage.py run_huey``
        'consumer': {'workers': 16, 'worker_type': 'greenlet'},
    }

Alternatively, you can just assign a :py:class:`Huey` instance to the ``HUEY`` setting:

.. code-block:: python

    from huey import RedisHuey

    HUEY = RedisHuey('my-app')


Running the Consumer
--------------------

To run the consumer, use the ``run_huey`` management command.  This command
will automatically import any modules in your ``INSTALLED_APPS`` named
"tasks.py".  The consumer can be configured by the ``consumer`` setting dictionary.

In addition to the ``consumer`` settings, you can also pass some options to the
consumer at run-time.

``-w``, ``--workers``
    Number of worker threads/processes/greenlets.

``-k``, ``--worker-type``
    Worker type, must be "thread", "process" or "greenlet".

``-n``, ``--no-periodic``
    Indicate that this consumer process should *not* enqueue periodic tasks.

For more information, check the :ref:`consumer docs <consuming-tasks>`.

Task API
--------

The task decorators are available in the ``huey.contrib.djhuey`` module. Here is how you might create two tasks:

.. code-block:: python

    from huey.contrib.djhuey import crontab, periodic_task, task

    @task()
    def count_beans(number):
        print('-- counted %s beans --' % number)
        return 'Counted %s beans' % number

    @periodic_task(crontab(minute='*/5'))
    def every_five_mins():
        print('Every five minutes this will be printed by the consumer')

Tasks that execute queries
^^^^^^^^^^^^^^^^^^^^^^^^^^

If you plan on executing queries inside your task, it is a good idea to close
the connection once your task finishes.  To make this easier, huey provides a
special decorator to use in place of ``task`` and ``periodic_task`` which will
automatically close the connection for you.

.. code-block:: python

    from huey.contrib.djhuey import crontab, db_periodic_task, db_task

    @db_task()
    def do_some_queries():
        # This task executes queries. Once the task finishes, the connection
        # will be closed.

    @db_periodic_task(crontab(minute='*/5'))
    def every_five_mins():
        # This is a periodic task that executes queries.
