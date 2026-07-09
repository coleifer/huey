.. _flask-admin:

Flask-Peewee admin
------------------

:py:class:`HueyPanel` adds a huey monitoring dashboard to the admin site
provided by `flask-peewee <https://github.com/coleifer/flask-peewee>`_. The
dashboard shows live queue depths, currently-running tasks, recent events,
per-task throughput and error-rates, and provides controls for revoking or
restoring tasks and flushing the queue, schedule, results or locks.

The extension has two halves, because the data comes from two places:

* :py:func:`enable_huey_admin` runs inside the **consumer** and records task
  signals (executing, complete, error, ...) into a pair of peewee tables. It
  depends only on peewee, so the consumer does not need Flask installed.
* :py:class:`HueyPanel` runs inside your **web** application and renders that
  recorded history alongside live queue introspection.

Both halves read and write the same two tables, so they must point at a shared
database that both processes can reach.

Recording task history (consumer)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Enable the recorder once, in a module the consumer imports:

.. code-block:: python

    import peewee

    from huey import SqliteHuey
    from huey.contrib.flask_admin import enable_huey_admin

    huey = SqliteHuey('/path/to/tasks.db')

    # Where the huey_event and huey_inflight tables live. This may be a peewee
    # Database or a flask-peewee Database, and need not be the huey storage.
    stats_db = peewee.SqliteDatabase('/path/to/stats.db')

    enable_huey_admin(huey, stats_db)

Registering the panel (web app)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Register the panel with your flask-peewee :py:class:`Admin` instance, passing
the huey instance as an extra argument:

.. code-block:: python

    from huey.contrib.flask_admin import HueyPanel

    admin.register_panel('Huey', HueyPanel, huey)

By default the panel reads the stats tables from your admin's authentication
database (``admin.auth.db``). If the stats live elsewhere, pass the database
explicitly:

.. code-block:: python

    admin.register_panel('Huey', HueyPanel, huey, stats_db)

If you never call :py:func:`enable_huey_admin` in the consumer, the panel still
displays the live queue counts (pending, scheduled, results), but the
throughput, per-task and event tables will be empty.

API
^^^

.. py:function:: enable_huey_admin(huey, db[, **options])

    Attach a stats recorder to ``huey`` and begin writing task events to
    ``db``. This is idempotent: calling it more than once for a given huey
    instance returns the recorder created by the first call.

    :param huey: the :py:class:`Huey` instance to monitor.
    :param db: a peewee ``Database`` or flask-peewee ``Database`` in which to
        store the ``huey_event`` and ``huey_inflight`` tables.
    :param int retention_hours: how long to keep events, in hours (default 48).
    :param int max_events: maximum number of events retained per queue
        (default 2000).
    :param bool capture_args: also store a repr of each task's args and kwargs
        (default False).
    :param bool create_tables: create the stats tables if they do not already
        exist (default True).

.. py:class:: HueyPanel

    A flask-peewee ``AdminPanel`` subclass. Register it with
    :py:meth:`Admin.register_panel`, passing the huey instance -- and,
    optionally, the stats database -- as extra arguments:

    .. code-block:: python

        admin.register_panel('Huey', HueyPanel, huey)  # db = admin.auth.db
        admin.register_panel('Huey', HueyPanel, huey, stats_db)

    Registering the panel also calls :py:func:`enable_huey_admin`, so the stats
    tables are created automatically when the admin site starts up.
