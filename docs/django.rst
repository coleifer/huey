.. _django:

Using Huey with Django
======================

Huey comes with special integration for use with the Django framework.  This is
to accomodate:

1. Configuring your queue and consumer via django settings module.
2. Run the consumer as a management command.

Apps
----

``huey.djhuey`` must be included in the INSTALLED_APPS within the Django settings.py file.

.. code-block:: python

    INSTALLED_APPS = (
        'huey.djhuey',
        ...

Huey Settings
-------------

.. note::
    Huey settings are optional.  If not provided, Huey will default to using
    Redis running locally.

All configuration is kept in ``settings.HUEY``.  Here is an example:

.. code-block:: python

    HUEY = {
        'backend': 'huey.backends.redis_backend',  # required.
        'name': 'unique name',
        'connection': {'host': 'localhost', 'port': 6379},
        'always_eager': False, # Defaults to False when running via manage.py run_huey

        # Options to pass into the consumer when running ``manage.py run_huey``
        'consumer_options': {'workers': 4},
    }

Running the Consumer
--------------------

To run the consumer, use the ``run_huey`` management command.  This command
will automatically import any modules in your ``INSTALLED_APPS`` named
"tasks.py".  The consumer can be configured by the ``consumer_options``
settings.

In addition to the ``consumer_options``, you can also pass some options to the
consumer at run-time.

``-w``, ``--workers``
    Number of worker threads.

``-p``, ``--periodic``
    Indicate that this consumer process should start a thread dedicated to
    enqueueing "periodic" tasks (crontab-like functionality).  This defaults
    to ``True``, so should not need to be specified in practice.

``-n``, ``--no-periodic``
    Indicate that this consumer process should *not* enqueue periodic tasks.

For more information, check the :ref:`consumer docs <consuming-tasks>`.

Task API
--------

The task API is a little bit simplified for Django.  The function decorators
are available in the ``huey.djhuey`` module.

Here is how you might create two tasks:

.. code-block:: python

    from huey.djhuey import crontab, periodic_task, task

    @task()
    def count_beans(number):
        print '-- counted %s beans --' % number
        return 'Counted %s beans' % number

    @periodic_task(crontab(minute='*/5'))
    def every_five_mins():
        print 'Every five minutes this will be printed by the consumer'

Tasks that execute queries
^^^^^^^^^^^^^^^^^^^^^^^^^^

If you plan on executing queries inside your task, it is a good idea to close
the connection once your task finishes.  To make this easier, huey provides a
special decorator to use in place of ``task`` and ``periodic_task`` which will
automatically close the connection for you.

.. code-block:: python

    from huey.djhuey import crontab, db_periodic_task, db_task

    @db_task()
    def do_some_queries():
        # This task executes queries. Once the task finishes, the connection
        # will be closed.

    @db_periodic_task(crontab(minute='*/5'))
    def every_five_mins():
        # This is a periodic task that executes queries.
