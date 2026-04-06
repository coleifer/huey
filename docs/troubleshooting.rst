.. _troubleshooting:

Troubleshooting and Common Pitfalls
===================================

This document outlines some of the common pitfalls you may encounter when
getting set up with huey.  It is arranged in a problem/solution format.

Tasks not running
    First step is to increase logging verbosity by running the consumer with
    ``--verbose``.  You can also specify a logfile using the ``--logfile``
    option.

    Check for any exceptions.  The most common cause of tasks not running is
    that they are not being loaded, in which case you will
    see :py:class:`HueyException` "XXX not found in TaskRegistry" errors.

"HueyException: XXX not found in TaskRegistry" in log file
    Exception occurs when a task is called by a task producer, but is not
    imported by the consumer.  To fix this, ensure that by loading the
    :py:class:`Huey` object, you also import any decorated functions as well.

    For more information on how tasks are imported, see the :ref:`import documentation <imports>`.

"Error importing XXX" when starting consumer
    This error message occurs when the module containing the configuration
    specified cannot be loaded (not on the pythonpath, mistyped, etc).  One
    quick way to check is to open up a python shell and try to import the
    configuration.

    Example syntax: ``huey_consumer.py main_module.huey``

Tasks not returning results
    Ensure that you have not accidentally specified ``results=False`` when
    instantiating your :py:class:`Huey` object.

    Additionally note that, by default, Huey does not store ``None`` in the
    result-store. So if your task returns ``None``, Huey will discard the
    result. If you need to block or detect whether a task has finished, it is
    recommended that you return a non-``None`` value or in extreme
    circumstances you can initialize Huey with ``store_none=True`` (though this
    can quickly fill up your result store and is only recommended for users who
    are very familiar with Huey).

Task result is always None even though the task returns a value
    This is often caused by reading the result before the consumer has executed
    the task. When a result is not yet available, ``result.get()`` returns
    ``None``. Use ``result.get(blocking=True, timeout=5)`` to block until the
    result is ready.

    Another subtle cause: Huey's result store is destructive by default. Once
    you call ``result.get()`` or ``result()``, the value is removed from the
    store. Calling it a second time will return ``None``. If you need to read
    a result multiple times, pass ``preserve=True``:

    .. code-block:: python

        val = result.get(preserve=True)  # Value is retained in the store.
        val = result.get(preserve=True)  # Same value returned again.

Task result is stale after a retry
    When a task fails and is retried, Huey stores the error from the first
    attempt. If the retry succeeds, the new result overwrites the old one.
    However, if your code already called ``result.get()`` and received the
    error, the :py:class:`Result` object caches the error locally. You must
    call ``result.reset()`` to clear the local cache before reading again:

    .. code-block:: python

        result = flaky_task()
        try:
            result.get(blocking=True, timeout=5)
        except TaskException:
            # Task failed. Wait for the retry to finish, then:
            result.reset()
            value = result.get(blocking=True, timeout=30)

Scheduled tasks are not being run at the correct time
    Check the time on the server the consumer is running on - if different from
    the producer this may cause problems. Huey uses UTC internally by default,
    and naive datetimes will be converted from local time to UTC (if local time
    happens to not be UTC).

Cronjobs are not being run
    The consumer and scheduler run in UTC by default.

Periodic tasks running twice (or more)
    When running multiple consumers, only **one** consumer should be configured
    to enqueue periodic tasks. All other consumers should be started with the
    ``-n`` / ``--no-periodic`` flag. Without this, each consumer will
    independently enqueue the same periodic tasks, leading to duplicate
    executions.

    See :ref:`multiple-consumers` for details.

Greenlet workers seem stuck
    If you wish to use the Greenlet worker type, you need to be sure to
    monkeypatch in your application's entrypoint. At the top of your ``main``
    module, you can add the following code: ``from gevent import monkey; monkey.patch_all()``.
    Furthermore, if your tasks are CPU-bound, ``gevent`` can appear to lock up
    because it only supports cooperative multi-tasking (as opposed to
    pre-emptive multi-tasking when using threads). For Django, it is necessary
    to apply the patch inside the ``manage.py`` script. See the Django docs
    section for the code.

Task locks are stuck after consumer crash
    If the consumer is killed abruptly (``SIGKILL``, power loss, OOM killer)
    while executing a locked task, the lock key remains in the storage backend
    and the task will appear permanently locked.

    Solutions:

    * Start the consumer with ``-f`` / ``--flush-locks`` to clear all known
      locks on startup.
    * If you have locks created inside context managers (not as decorators),
      they may not be automatically discovered. Use ``-L`` / ``--extra-locks``
      to specify their names: ``huey_consumer.py app.huey -f -L my-lock-name``.
    * Manually clear a specific lock from your application code:

      .. code-block:: python

          huey.lock_task('my-lock-name').clear()

          # Or flush all discovered locks:
          huey.flush_locks()

    See :py:meth:`Huey.lock_task`, :py:meth:`Huey.flush_locks`, and the
    ``-f`` consumer option for more details.

Task function not found after renaming or moving
    Huey registers tasks by their module path and function name (e.g.,
    ``myapp.tasks.process_order``). If you rename a function or move it to
    another module while tasks are still queued, the consumer will fail to
    deserialize those tasks and raise a ``HueyException``.

    Solutions:

    * Drain the queue before deploying (let the old consumer process all
      remaining tasks before starting the new code).
    * Use the ``name`` parameter on the :py:meth:`~Huey.task` decorator to
      give the task a stable name that survives refactoring:

      .. code-block:: python

          @huey.task(name='myapp.tasks.process_order')
          def handle_order(order_id):
              ...

Tasks running out of order
    With :py:class:`SqliteHuey` and ``strict_fifo=False`` (the default), SQLite
    may reuse rowids for deleted tasks, which can cause tasks to be dequeued in
    a different order than the order in which they were enqueued.

    If strict FIFO ordering is important, initialize with ``strict_fifo=True``:

    .. code-block:: python

        huey = SqliteHuey('my-app', filename='huey.db', strict_fifo=True)

    With Redis storage, the default ``RedisHuey`` uses a list and preserves
    insertion order. ``PriorityRedisHuey`` orders by priority score.

Result store growing without bound (Redis)
    When using :py:class:`RedisHuey`, task results are stored in a Redis hash.
    Results are only removed when read (via ``result.get()`` or
    ``huey.result()``). If your tasks return values that nobody reads, the hash
    will grow indefinitely.

    Solutions:

    * Switch to :py:class:`RedisExpireHuey`, which stores results as individual
      keys with a TTL. Unread results are automatically cleaned up by Redis.
    * Have your tasks return ``None`` if you do not need the result.
    * Initialize Huey with ``results=False`` if you **never** read results.
    * Periodically read and discard results from the application side.

Consumer seems slow / tasks have high latency
    Several things to check:

    * **Worker count:** The default is 1 worker. Increase it with ``-w``.
      Most applications benefit from at least 2-4 workers.
    * **Blocking vs polling:** ``RedisHuey`` defaults to ``blocking=True``,
      which reacts instantly to new messages. ``SqliteHuey`` uses polling. If
      you are using polling, the ``-d`` (delay) and ``-b`` (backoff) parameters
      control how frequently Huey checks for new messages.
    * **Scheduler interval:** The default scheduler interval is 1 second
      (``-s 1``) (lowest possible value). If you have very few scheduled tasks
      and want to save CPU, you can increase the interval to 10 or 30 seconds.
    * **Worker type:** For CPU-bound tasks, use ``-k process``. For IO-bound
      tasks, consider ``-k greenlet`` with many workers.
    * **Verbose logging:** Run with ``-v`` to see exactly when tasks are
      dequeued, executed, and completed. Large gaps between "dequeued" and
      "executing" indicate worker saturation.

Memory growing in consumer process
    When using process workers (``-k process``), child processes are not
    recycled -- they run for the lifetime of the consumer. If tasks allocate
    large data structures, memory may accumulate over time.

    Solutions:

    * Restart the consumer periodically (``supervisord``'s ``autorestart`` or
      a cron job that sends ``SIGHUP``).
    * Use thread or greenlet workers, which share memory with the main process
      and are subject to garbage collection.
    * Structure tasks to process data in smaller chunks rather than loading
      everything into memory at once.

"TypeError: can't pickle ..." or "PicklingError"
    Task arguments and return values must be serializable by ``pickle``. Common
    offenders include: database connections, open file handles, lambda
    functions, generators, and class instances with unpicklable attributes
    (e.g., locks, sockets).

    Solutions:

    * Pass IDs, keys, or file paths instead of objects. Look up the object
      inside the task function.
    * If you need a database connection, use :py:meth:`~Huey.on_startup` or
      :py:meth:`~Huey.context_task` to initialize it inside the worker.
    * For custom classes, implement ``__getstate__`` and ``__setstate__``, or
      convert to a plain ``dict`` before returning.
    * If you need a different serialization format entirely, subclass
      :py:class:`Serializer` and override ``_serialize`` / ``_deserialize``.

Testing projects using Huey
    Use ``immediate=True``:

    .. code-block:: python

        test_mode = os.environ.get('TEST_MODE')

        # When immediate=True, Huey will default to using an in-memory
        # storage layer.
        huey = RedisHuey(immediate=test_mode)

        # Alternatively, you can set the `immediate` attribute:
        huey.immediate = True if test_mode else False

    For more details, see the :ref:`testing guidelines <immediate>` section of
    the guide.

Task decorated with ``@huey.task()`` blocks when called
    If calling a task-decorated function blocks instead of returning a result
    handle immediately, check whether ``immediate=True`` is set on your Huey
    instance. In immediate mode, tasks are executed synchronously by the caller.
    This is by design for testing and debugging, but if you see this behavior
    unexpectedly, ensure ``huey.immediate`` is ``False`` in production.
