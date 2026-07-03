.. _django:

Django
------

Huey comes with special integration for use with the Django framework. The
integration provides:

1. Configuration of huey via the Django settings module.
2. Running the consumer as a Django management command.
3. Auto-discovery of ``tasks.py`` modules to simplify task importing.
4. Properly manage database connections.
5. A :ref:`backend <django-task>` for the ``django.tasks`` framework (Django
   6.0 and newer, or older Djangos using the django-tasks backport).

Supported Django versions are those officially supported at https://www.djangoproject.com/download/#supported-versions

.. note::
   For multiple-queue support, check out `gaiacoop/django-huey <https://github.com/gaiacoop/django-huey>`_.
   For a discussion of when multiple queues are useful (and when task
   priorities are the simpler answer), see :ref:`recipe-multiple-queues`.

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

Huey settings are optional. If not provided, Huey will default to using Redis
running on localhost:6379 (standard setup).

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
* ``huey.RedisExpireHuey`` - Redis implementation that expires result keys
  automatically if results are not read.
* ``huey.PriorityRedisExpireHuey`` - Redis implementation that expires result
  keys automatically if results are not read and supports priority.
* ``huey.SqliteHuey`` - uses Sqlite, full support for task priorities. Accepts
  a ``filename`` parameter for the path to the database file.
* ``huey.PostgresHuey`` - uses Postgres, full support for task priorities. See
  :ref:`django-postgres` for connection and schema configuration.
* ``huey.FileHuey`` - uses filesystem for storage. Accepts a ``path`` parameter
  for the base storage directory.

Alternatively, you can simply set ``settings.HUEY`` to a :py:class:`Huey`
instance and do your configuration directly. In the example below, I've also
shown how you can create a connection pool:

.. code-block:: python

    # settings.py -- alternative configuration method
    from huey import RedisHuey
    from redis import ConnectionPool

    pool = ConnectionPool(host='my.redis.host', port=6379, max_connections=20)
    HUEY = RedisHuey('my-app', connection_pool=pool)

.. _django-postgres:

Using Postgres for storage
^^^^^^^^^^^^^^^^^^^^^^^^^^^

:py:class:`PostgresHuey` lets you use your existing Postgres database as the
task queue, schedule and result store (``pip install huey[postgres]``). Two
integration points are worth calling out for Django users.

Schema creation
"""""""""""""""

By default the storage backend issues ``create table if not exists`` for its
tables when it is instantiated. Because ``settings.HUEY`` is evaluated at import
time, that means every process importing ``huey.contrib.djhuey`` -- including
your web workers -- will connect and attempt to create the tables, which
requires the ``CREATE`` privilege and clashes with a migrations-managed schema.

Pass ``create_tables=False`` to disable the automatic DDL and create the tables
once, explicitly, using the ``create_huey_tables`` management command:

.. code-block:: python

    # settings.py
    HUEY = {
        'huey_class': 'huey.PostgresHuey',
        'create_tables': False,
        'connection': {'dsn': 'postgresql:///my_db'},
    }

.. code-block:: shell

    ./manage.py create_huey_tables

Reusing the Django database configuration
"""""""""""""""""""""""""""""""""""""""""

Rather than duplicating your credentials in ``settings.HUEY``, you can point the
storage at the same database Django uses by passing a ``connection`` callable.
The callable must return a **new**, dedicated ``psycopg`` connection -- do not
hand back ``django.db.connection``. Huey enables autocommit on the connection
and holds a long-lived one open for ``LISTEN``, neither of which is compatible
with Django's per-request connection or its transaction handling.

.. code-block:: python

    # settings.py
    import psycopg
    from django.conf import settings

    def huey_connection():
        db = settings.DATABASES['default']
        return psycopg.connect(
            dbname=db['NAME'],
            user=db.get('USER') or None,
            password=db.get('PASSWORD') or None,
            host=db.get('HOST') or None,
            port=db.get('PORT') or None)

    HUEY = {
        'huey_class': 'huey.PostgresHuey',
        'create_tables': False,
        'connection': {'connection': huey_connection},
    }

To ensure a task is not enqueued until the surrounding transaction commits (for
example, when it references a row created in the same view), use
:py:func:`on_commit_task` as described in :ref:`django-transactions`.

Running the Consumer
^^^^^^^^^^^^^^^^^^^^

To run the consumer, use the ``run_huey`` management command.  This command
will automatically import any modules in your ``INSTALLED_APPS`` named
*tasks.py*.  The consumer can be configured using both the django settings
module and/or by specifying options from the command-line.

Options specified on the command line take precedence over those specified in
the settings module.

To start the consumer, you simply run:

.. code-block:: shell

    ./manage.py run_huey

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

``-A``, ``--disable-autoload``
    Disable automatic loading of tasks modules.

Due to a conflict with Django's base option list, the "verbose" option is set
using ``-V`` or ``--huey-verbose``. When enabled, huey logs at the DEBUG level.

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
* :py:func:`on_commit_task`, for enqueueing tasks after transaction commits.

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

.. _django-transactions:

Enqueueing After Commit
^^^^^^^^^^^^^^^^^^^^^^^

The Huey Django extension provides a helper for when you need to ensure the
active transaction has committed **before** enqueueing your task. Consider this
example code:

.. code-block:: python

    @task()
    def do_work(user_id):
        user = User.objects.get(pk=user_id)
        ...

    @transaction.atomic
    def some_view(request, ...):
        user = User.objects.create(...)
        do_work(user.id)
        return response

When ``some_view`` is executed, the ``do_work()`` task is enqueued with the ID
of the newly-created user row. If the task is enqueued and executed **before**
the transaction commits, then the task will report that the user matching that
ID does not exist (because it has not been committed yet).

To avoid this situation, we provide a special-purpose decorator
:py:func:`on_commit_task`, which registers a callback with Django that ensures
the task is enqueued **after** the transaction is committed. If no transaction
is active, the task will be enqueued normally.

Here is the safe version:

.. code-block:: python

    @on_commit_task()
    def do_work(user_id):
        user = User.objects.get(pk=user_id)
        ...

    @transaction.atomic
    def some_view(request, ...):
        user = User.objects.create(...)
        do_work(user.id)  # Will not be enqueued until txn commits.
        return response

Because we have to setup a callback to run after commit, the full functionality
of the :py:class:`TaskWrapper` is not available with tasks decorated with
:py:func:`on_commit_task`. If you anticipate needing all the TaskWrapper
methods, you can decorate the same function twice by given them two different
identifier names:

.. code-block:: python

    def do_work(user_id):
        user = User.objects.get(pk=user_id)
        ...

    do_work_task = task(name="do_work_task")(do_work)
    do_work_on_commit = on_commit_task(name="do_work_on_commit")(do_work)


.. py:function:: on_commit_task(*args, **kwargs)

    :param args: See :py:meth:`~Huey.task` for supported parameters.
    :param kwargs: See :py:meth:`~Huey.task` for supported parameters.

    Enqueue the decorated function for execution after the transaction commits.
    If no transaction is active, task will be enqueued immediately.


.. _django-task:

Django task framework
---------------------

Django 6.0 includes `django.tasks
<https://docs.djangoproject.com/en/stable/topics/tasks/>`_, a standard
interface for defining and enqueueing background tasks. Django does not ship
a production backend for actually running them - huey provides one. Tasks
declared with the ``django.tasks.task`` decorator are stored and executed by
the regular huey consumer, side-by-side with your native huey tasks. On older
Django versions, the backend works identically with the `django-tasks
<https://github.com/RealOrangeOne/django-tasks>`_ backport package.

To use it, declare the backend in ``settings.TASKS``. The backend uses the
shared huey instance configured by ``settings.HUEY``, as described above:

.. code-block:: python

    # settings.py
    TASKS = {
        'default': {
            'BACKEND': 'huey.contrib.djhuey.tasks_backend.HueyBackend',
        },
    }

Tasks are declared and enqueued using the standard django.tasks APIs - no
huey imports are necessary:

.. code-block:: python

    from django.tasks import task

    @task
    def send_welcome_email(user_id):
        ...

    # In a view, etc:
    result = send_welcome_email.enqueue(user.id)
    result.id      # Unique identifier, usable with get_result().
    result.status  # READY -> RUNNING -> SUCCESSFUL or FAILED.

    # Later, check on it:
    result.refresh()
    if result.is_finished:
        print(result.return_value)

The consumer is run exactly as before - ``manage.py run_huey`` - and executes
django.tasks tasks and native huey tasks side-by-side.

Supported functionality:

* ``run_after`` is mapped onto huey's ``eta`` and handled by the scheduler.
* ``priority`` is supported when the storage engine supports priorities, e.g.
  ``SqliteHuey`` or ``PriorityRedisHuey``. With plain ``RedisHuey``, declaring
  a task with a non-zero priority raises ``InvalidTask``.
* Results: ``get_result()``, ``refresh()``, return values and errors (with
  tracebacks) are fully supported. Task status is tracked in the huey result
  store, so ``RedisExpireHuey`` will expire result data automatically.
* Database connections are closed after each task, equivalent to
  :py:func:`db_task`.
* Transactional enqueueing: add ``'ENQUEUE_ON_COMMIT': True`` to the backend
  declaration to defer enqueueing until the active transaction commits
  (equivalent to :py:func:`on_commit_task`).
* Immediate mode applies as usual: when ``DEBUG=True``, tasks execute
  synchronously, through the same code-path the consumer uses.

.. note::
    The django.tasks framework requires task functions to be defined at the
    module level, and the huey backend additionally requires that they are
    importable from their module path - lambdas cannot be enqueued.
    Coroutine (``async def``) tasks are not supported.


DEBUG and Synchronous Execution
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When ``settings.DEBUG = True``, and ``settings.HUEY`` is a ``dict`` that does
not explicitly specify a value for ``immediate``, tasks will be executed
**synchronously** just like regular function calls. The purpose of this is to
avoid running both Redis and an additional consumer process while developing or
running tests. If you prefer to use a live storage engine when ``DEBUG`` is
enabled, you can specify ``immediate_use_memory=False`` - which still runs Huey
in immediate mode, but using a live storage API. To completely disable
immediate mode when ``DEBUG`` is set, you can specify ``immediate=False`` in
your settings.

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

Getting the Huey Instance
^^^^^^^^^^^^^^^^^^^^^^^^^

If you want to interact with Huey APIs that are not exposed through ``djhuey``
explicitly, you can get the actual ``Huey`` instance in the following way:

.. code-block:: python

    from huey.contrib.djhuey import HUEY as huey

    # E.g., get the underlying Storage instance.
    storage = huey.storage

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
