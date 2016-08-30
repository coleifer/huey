.. _django:

Using Huey with Django
======================

Huey comes with special integration for use with the Django framework. The
integration provides:

1. Configuration of huey via the Django settings module.
2. Running the consumer as a Django management command.
3. Auto-discovery of ``tasks.py`` modules to simplify task importing.
4. Properly manage database connections.

Setting things up
-----------------

To use huey with Django, the first step is to add an entry to your project's
``settings.INSTALLED_APPS``:

.. code-block:: python

    # settings.py
    # ...
    INSTALLED_APPS = (
        # ...
        'huey.contrib.djhuey',  # Add this to the list.
        # ...
    )

The above is the bare minimum needed to start using huey's Django integration.
If you like, though, you can also configure both Huey and the *consumer* using
the settings module.

.. note::
    Huey settings are optional. If not provided, Huey will default to using
    Redis running on localhost:6379 (standard setup).

Configuration is kept in ``settings.HUEY``, which can be either a dictionary or
a :py:class:`Huey` instance. Here is an example that shows all of the supported
options with their default values:

.. code-block:: python

    # settings.py
    HUEY = {
        'name': settings.DATABASES['default']['name'],  # Use db name for huey.
        'result_store': True,  # Store return values of tasks.
        'events': True,  # Consumer emits events allowing real-time monitoring.
        'store_none': False,  # If a task returns None, do not save to results.
        'always_eager': settings.DEBUG,  # If DEBUG=True, run synchronously.
        'store_errors': True,  # Store error info if task throws exception.
        'blocking': False,  # Poll the queue rather than do blocking pop.
        'connection': {
            'host': 'localhost',
            'port': 6379,
            'db': 0,
            'connection_pool': None,  # Definitely you should use pooling!
            # ... tons of other options, see redis-py for details.

            # huey-specific connection parameters.
            'read_timeout': 1,  # If not polling (blocking pop), use timeout.
            'max_errors': 1000,  # Only store the 1000 most recent errors.
            'url': None,  # Allow Redis config via a DSN.
        },
        'consumer': {
            'workers': 1,
            'worker_type': 'thread',
            'initial_delay': 0.1,  # Smallest polling interval, same as -d.
            'backoff': 1.15,  # Exponential backoff using this rate, -b.
            'max_delay': 10.0,  # Max possible polling interval, -m.
            'utc': True,  # Treat ETAs and schedules as UTC datetimes.
            'scheduler_interval': 1,  # Check schedule every second, -s.
            'periodic': True,  # Enable crontab feature.
            'check_worker_health': True,  # Enable worker health checks.
            'health_check_interval': 1,  # Check worker health every second.
        },
    }

Alternatively, you can simply set ``settings.HUEY`` to a :py:class:`Huey`
instance and do your configuration directly. In the example below, I've also
shown how you can create a connection pool:

.. code-block:: python

    # settings.py -- alternative configuration method
    from huey import RedisHuey
    from redis import ConnectionPool

    pool = ConnectionPool(host='my.redis.host', port=6379, max_connections=20)
    HUEY = RedisHuey('my-app', connection_pool=pool)

Running the Consumer
--------------------

To run the consumer, use the ``run_huey`` management command.  This command
will automatically import any modules in your ``INSTALLED_APPS`` named
*tasks.py*.  The consumer can be configured using both the django settings
module and/or by specifying options from the command-line.

.. note::
    Options specified on the command line take precedence over those specified
    in the settings module.

To start the consumer, you simply run:

.. code-block:: console
    $ ./manage.py run_huey

In addition to the ``HUEY.consumer`` setting dictionary, the management command
supports all the same options as the standalone consumer. These options are
listed and described in the :ref:`Options for the consumer <consumer-options>`
section.

For quick reference, the most important command-line options are briefly
listed here.

``-w``, ``--workers``
    Number of worker threads/processes/greenlets. Default is 1, but most
    applications should use at least 2.

``-k``, ``--worker-type``
    Worker type, must be "thread", "process" or "greenlet". The default is
    *thread*, which provides good all-around performance. For CPU-intensive
    workloads, *process* is likely to be more performant. The *greenlet* worker
    type is suited for IO-heavy workloads. When using *greenlet* you can
    specify tens or hundreds of workers since they are extremely lightweight
    compared to threads/processes.

.. note::
    Due to a conflict with Django's base option list, the "verbose" option is
    set using ``-V`` or ``--huey-verbose``. When enabled, huey logs at the
    DEBUG level.

For more information, read the :ref:`Options for the consumer <consumer-options>` section.

How to create tasks
-------------------

The :py:meth:`~Huey.task` and :py:meth:`~Huey.periodic_task` decorators can be
imported from the ``huey.contrib.djhuey`` module. Here is how you might define
two tasks:

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

DEBUG and Synchronous Execution
-------------------------------

When ``settings.DEBUG = True``, tasks will be executed **synchronously** just like
regular function calls. The purpose of this is to avoid running both Redis and
an additional consumer process while developing or running tests. If, however,
you would like to enqueue tasks regardless of whether ``DEBUG = True``, then
explicitly specify ``always_eager=False`` in your huey settings:

.. code-block:: python

    # settings.py
    HUEY = {
        'name': 'my-app',
        # Other settings ...
        'always_eager': False,
    }

Configuration Examples
----------------------

This section contains example ``HUEY`` configurations.


.. code-block:: python

    # Redis running locally with four worker threads.
    HUEY = {
        'name': 'my-app',
        'consumer': {'workers': 4, 'worker_type': 'thread'},
    }


.. code-block:: python

    # Redis on network host with 64 worker greenlets and connection pool
    # supporting up to 100 connections.
    from redis import ConnectionPool

    pool = ConnectionPool(
        host='192.168.1.123',
        port=6379,
        max_connections=100)

    HUEY = {
        'name': 'my-app',
        'connection': {'connection_pool': pool},
        'consumer': {'workers': 64, 'worker_type': 'greenlet'},
    }

It is also possible to specify the connection using a Redis URL, making it easy
to configure this setting using a single environment variable:

.. code-block:: python

    HUEY = {
        'name': 'my-app',
        'url': os.environ.get('REDIS_URL', 'redis://localhost:6379/?db=1')
    }

Alternatively, you can just assign a :py:class:`Huey` instance to the ``HUEY`` setting:

.. code-block:: python

    from huey import RedisHuey

    HUEY = RedisHuey('my-app')
