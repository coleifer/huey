.. _django:

Django
------

Huey comes with special integration for use with the Django framework. The
integration provides:

1. Configuration of huey via the Django settings module.
2. Running the consumer as a Django management command.
3. Auto-discovery of ``tasks.py`` modules to simplify task importing.
4. Properly manage database connections.

Supported Django versions are the officially supported at https://www.djangoproject.com/download/#supported-versions

Setting things up
^^^^^^^^^^^^^^^^^

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
        'huey_class': 'huey.RedisHuey',  # Huey implementation to use.
        'name': settings.DATABASES['default']['NAME'],  # Use db name for huey.
        'results': True,  # Store return values of tasks.
        'store_none': False,  # If a task returns None, do not save to results.
        'immediate': settings.DEBUG,  # If DEBUG=True, run synchronously.
        'utc': True,  # Use UTC for all times internally.
        'blocking': True,  # Perform blocking pop rather than poll Redis.
        'connection': {
            'host': 'localhost',
            'port': 6379,
            'db': 0,
            'connection_pool': None,  # Definitely you should use pooling!
            # ... tons of other options, see redis-py for details.

            # huey-specific connection parameters.
            'read_timeout': 1,  # If not polling (blocking pop), use timeout.
            'url': None,  # Allow Redis config via a DSN.
        },
        'consumer': {
            'workers': 1,
            'worker_type': 'thread',
            'initial_delay': 0.1,  # Smallest polling interval, same as -d.
            'backoff': 1.15,  # Exponential backoff using this rate, -b.
            'max_delay': 10.0,  # Max possible polling interval, -m.
            'scheduler_interval': 1,  # Check schedule every second, -s.
            'periodic': True,  # Enable crontab feature.
            'check_worker_health': True,  # Enable worker health checks.
            'health_check_interval': 1,  # Check worker health every second.
        },
    }

The following ``huey_class`` implementations are provided out-of-the-box:

* ``huey.RedisHuey`` - default.
* ``huey.PriorityRedisHuey`` - uses Redis but adds support for :ref:`priority`.
  Requires redis server 5.0 or newer.
* ``huey.SqliteHuey`` - uses Sqlite, full support for task priorities.

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
^^^^^^^^^^^^^^^^^^^^

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
    compared to threads/processes. *See note below on using gevent/greenlet*.

``-A``, ``--disable-autload``
    Disable automatic loading of tasks modules.

.. note::
    Due to a conflict with Django's base option list, the "verbose" option is
    set using ``-V`` or ``--huey-verbose``. When enabled, huey logs at the
    DEBUG level.

For more information, read the :ref:`Options for the consumer <consumer-options>` section.

Using gevent
^^^^^^^^^^^^

When using worker type *greenlet*, it's necessary to apply a monkey-patch
before any libraries or system modules are imported. Gevent monkey-patches
things like ``socket`` to provide non-blocking I/O, and if those modules are
loaded before the patch is applied, then the resulting code will execute
synchronously.

Unfortunately, because of Django's design, the only way to reliably apply this
patch is to create a custom bootstrap script that mimics the functionality of
``manage.py``. Here is the patched ``manage.py`` code:

.. code-block:: python

    #!/usr/bin/env python
    import os
    import sys

    # Apply monkey-patch if we are running the huey consumer.
    if 'run_huey' in sys.argv:
        from gevent import monkey
        monkey.patch_all()

    if __name__ == "__main__":
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "conf")
        from django.core.management import execute_from_command_line
        execute_from_command_line(sys.argv)

How to create tasks
^^^^^^^^^^^^^^^^^^^

The :py:meth:`~Huey.task` and :py:meth:`~Huey.periodic_task` decorators can be
imported from the ``huey.contrib.djhuey`` module. Here is how you might define
two tasks:

.. code-block:: python

    from huey import crontab
    from huey.contrib.djhuey import periodic_task, task

    @task()
    def count_beans(number):
        print('-- counted %s beans --' % number)
        return 'Counted %s beans' % number

    @periodic_task(crontab(minute='*/5'))
    def every_five_mins():
        print('Every five minutes this will be printed by the consumer')

The ``huey.contrib.djhuey`` module exposes a number of additional helpers:

* :py:meth:`~Huey.lock_task`
* :py:meth:`~Huey.enqueue`
* :py:meth:`~Huey.restore`, :py:meth:`~Huey.restore_all`, :py:meth:`~Huey.restore_by_id`
* :py:meth:`~Huey.revoke`, :py:meth:`~Huey.revoke_all`, :py:meth:`~Huey.revoke_by_id`
* :py:meth:`~Huey.is_revoked`
* :py:meth:`~Huey.on_startup`
* :py:meth:`~Huey.pre_execute`
* :py:meth:`~Huey.post_execute`
* :py:meth:`~Huey.signal` and :py:meth:`~Huey.disconnect_signal`

Tasks that execute queries
^^^^^^^^^^^^^^^^^^^^^^^^^^

If you plan on executing queries inside your task, it is a good idea to close
the connection once your task finishes.  To make this easier, huey provides a
special decorator to use in place of ``task`` and ``periodic_task`` which will
automatically close the connection for you.

.. code-block:: python

    from huey import crontab
    from huey.contrib.djhuey import db_periodic_task, db_task

    @db_task()
    def do_some_queries():
        # This task executes queries. Once the task finishes, the connection
        # will be closed.

    @db_periodic_task(crontab(minute='*/5'))
    def every_five_mins():
        # This is a periodic task that executes queries.

DEBUG and Synchronous Execution
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When ``settings.DEBUG = True``, tasks will be executed **synchronously** just
like regular function calls. The purpose of this is to avoid running both Redis
and an additional consumer process while developing or running tests. If you
prefer to use a live storage engine when ``DEBUG`` is enabled, you can specify
``immediate_use_memory=False`` - which still runs Huey in immediate mode, but
using a live storage API. To completely disable immediate mode when ``DEBUG``
is set, specify ``immediate=False`` in your settings.

.. code-block:: python

    # settings.py
    HUEY = {
        'name': 'my-app',

        # To run Huey in "immediate" mode with a live storage API, specify
        # immediate_use_memory=False.
        'immediate_use_memory': False,

        # OR:
        # To run Huey in "live" mode regardless of whether DEBUG is enabled,
        # specify immediate=False.
        'immediate': False,
    }

Configuration Examples
^^^^^^^^^^^^^^^^^^^^^^

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
