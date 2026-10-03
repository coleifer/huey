.. _task-stats:

Task statistics
---------------

:py:func:`enable_stats` attaches a recorder to a :py:class:`Huey` instance that
persists task signals into a pair of `peewee <https://docs.peewee-orm.com/>`_
tables.

The recorder depends only on peewee (``pip install huey[stats]``). It is the
engine behind the :ref:`Flask-Peewee admin panel <flask-admin>` and the
:ref:`Django admin dashboard <django-admin-stats>`.

Enabling
^^^^^^^^

Signals fire in the process where a task runs, so to record task **execution**
the recorder must be enabled in the **consumer**. Call :py:func:`enable_stats`
once, in a module the consumer imports:

.. code-block:: python

    import peewee

    from huey import SqliteHuey
    from huey.contrib.stats import enable_stats

    huey = SqliteHuey('/path/to/tasks.db')

    # Any peewee (or flask-peewee) Database. It need not be the huey storage,
    # and a networked database (Postgres/MySQL) lets a separate web process
    # read the same statistics.
    stats_db = peewee.SqliteDatabase('/path/to/stats.db', pragmas={
        'journal_mode': 'wal'})

    stats = enable_stats(huey, stats_db)

Enabling it in additional processes (for example a web app that enqueues
tasks) is harmless and captures the signals that occur there. Statistics are
scoped by ``huey.name``, so several huey instances may share one database.

Querying
^^^^^^^^

The :py:class:`HueyStats` object returned by :py:func:`enable_stats` (also
available afterwards as ``huey._stats``) exposes read helpers:

.. code-block:: python

    stats = enable_stats(huey, stats_db)

    stats.window_counts()
    stats.task_breakdown()
    stats.throughput(minutes=60)
    stats.recent_events(limit=50)
    stats.inflight()

Two tables are created when the recorder starts (unless
``create_tables=False``): ``huey_event``, an append-only event log trimmed to
the retention settings, and ``huey_inflight``, one row per currently-executing
task. Writes are buffered and flushed by a background thread, so recording
adds negligible overhead to task execution.

API
^^^

.. py:function:: enable_stats(huey, db[, **options])

    Attach a stats recorder to ``huey`` and begin writing task events to
    ``db``. Idempotent per huey instance. Returns a :py:class:`HueyStats`.

    :param huey: the :py:class:`Huey` instance to monitor.
    :param db: a peewee ``Database`` or flask-peewee ``Database`` in which the
        ``huey_event`` and ``huey_inflight`` tables live.
    :param int retention_hours: how long to keep events, in hours (default 48).
    :param int max_events: maximum events retained per queue (default 2000).
    :param int inflight_hours: how long a task may remain in-flight before its
        row is presumed orphaned and pruned, in hours (default 6).
    :param bool capture_args: also store a truncated repr of each task's args
        and kwargs (default False).
    :param bool create_tables: create the tables if they do not exist
        (default True).

.. py:class:: HueyStats

    Returned by :py:func:`enable_stats`. Query helpers:

    .. py:method:: window_counts(seconds=86400)

        Return ``{signal: count}`` over the last ``seconds``.

    .. py:method:: task_breakdown()

        Return a list of per-task dicts with ``executed``, ``completed``,
        ``errors``, ``retries`` and average ``avg`` duration.

    .. py:method:: throughput(minutes=60)

        Return ``{'complete': [...], 'error': [...]}``, one bucket per minute,
        oldest first.

    .. py:method:: recent_events(limit=50)

        Return the most recent events, newest first.

    .. py:method:: inflight()

        Return the tasks that are currently executing.
