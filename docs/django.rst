.. _django:

Using Huey with Django
======================

Huey comes with special integration for use with the Django framework.  This is
to accomodate:

1. Configuring your queue and consumer via django settings module.
2. Run the consumer as a management command.

Huey Settings
-------------

.. note::
    Huey settings are optional.  If not provided, Huey will default to using
    Redis running locally.

All configuration is kept in ``settings.HUEY``.  Here is an example:

.. code-block:: python

    HUEY = {
        'queue': 'huey.backends.redis_backend.RedisBlockingQueue',  # required.
        'queue_name': 'unique name',
        'queue_connection': {'host': 'localhost', 'port': 6379},

        # Options for configuring a result store -- *recommended*
        'result_store': 'huey.backends.redis_backend.RedisDataStore',
        'result_store_name': 'defaults to queue name',
        'result_store_connection': {'host': 'localhost', 'port': 6379},

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
