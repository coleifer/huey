.. _api:

Huey's API
==========

Most end-users will interact with the API using the two decorators:

* :py:meth:`Huey.task`
* :py:meth:`Huey.periodic_task`

The API documentation will follow the structure of the huey ``api.py`` module.

Huey types
----------

Implementations of :py:class:`Huey` which handle task and result persistence.

.. note::
    See the documentation for :py:class:`Huey` for the list of initialization
    parameters common to all Huey implementations.

.. warning::
    If you have a busy application and plan to switch from one of the Redis
    implementations to another (e.g. switch from ``RedisHuey`` to the
    ``PriorityRedisHuey``) you may want to start the new huey consumer on a
    different Redis database (e.g. ``db=15``). Then let your old consumer drain
    any pre-existing tasks while the new consumer accepts new tasks.

.. py:class:: RedisHuey

    :py:class:`Huey` that utilizes `redis <https://redis.io/>`_ for queue and
    result storage. Requires `redis-py <https://github.com/andymccurdy/redis-py>`_.

    Commonly-used keyword arguments for storage configuration:

    :param bool blocking: Use blocking-pop when reading from the queue (as
        opposed to polling). Default is true.
    :param connection_pool: a redis-py ``ConnectionPool`` instance.
    :param url: url for Redis connection.
    :param host: hostname of the Redis server.
    :param port: port number.
    :param password: password for Redis.
    :param int db: Redis database to use (typically 0-15, default is 0).
    :param bool notify_result: use a blocking-pop on a result-ready key to
        enable low-latency result reading.
    :param int notify_result_ttl: TTL for result-ready key to automatically
        expire un-awaited results.

    The `redis-py documentation <https://redis-py.readthedocs.io/en/latest/>`_
    contains the complete list of arguments supported by the Redis client.

    .. note::
        RedisHuey does not support task priorities. If you wish to use task
        priorities with Redis, use :py:class:`PriorityRedisHuey`.

    RedisHuey uses a Redis LIST to store the queue of pending tasks. Redis
    lists are a natural fit, as they offer O(1) append and pop from either end
    of the list. Redis also provides blocking-pop commands which allow the
    consumer to react to a new message as soon as it is available without
    resorting to polling.

    For low-latency result-fetching, you can specify ``notify_result=True``
    when instantiating ``RedisHuey`` (or subclasses). This works by
    coordinating result readiness through a blocking pop on a dedicated result
    list. By default this result-readiness list will expire after 86400 seconds,
    but this can be controlled with the ``notify_result_ttl`` parameter.
    **All RedisHuey** implementations support these options.

    .. seealso:: :py:class:`RedisStorage`

.. py:class:: PriorityRedisHuey

    :py:class:`Huey` that utilizes `redis <https://redis.io/>`_ for queue and
    result storage. Requires `redis-py <https://github.com/andymccurdy/redis-py>`_.
    Accepts the same arguments as :py:class:`RedisHuey`.

    PriorityRedisHuey supports :ref:`task priorities <priority>`, and requires
    Redis **5.0 or newer**.

    PriorityRedisHuey uses a Redis SORTED SET to store the queue of pending
    tasks. Sorted sets consist of a unique value and a numeric score. In
    addition to being sorted by numeric score, Redis also orders the items
    within the set lexicographically. Huey takes advantage of these two
    characteristics to implement the priority queue. Redis 5.0 added a new
    command, ZPOPMIN, which pops the lowest-scoring item from the sorted set
    (and BZPOPMIN, the blocking variety).

.. py:class:: RedisExpireHuey

    Identical to :py:class:`RedisHuey` except for the way task result values
    are stored. RedisHuey keeps all task results in a Redis hash, and whenever
    a task result is read (via the result handle), it is also removed from the
    result hash. This is done to prevent the task result storage from growing
    without bound. Additionally, using a Redis hash for all results helps avoid
    cluttering up the Redis keyspace and utilizes less RAM for storing the keys
    themselves.

    ``RedisExpireHuey`` uses a different approach: task results are stored in
    ordinary Redis keys with a special prefix. Result keys are then given a
    time-to-live, and will be expired automatically by the Redis server. This
    removes the necessity to remove results from the result store after they
    are read once.

    Commonly-used keyword arguments for storage configuration:

    :param int expire_time: Expire time in seconds, default is 86400 (1 day).
    :param bool blocking: Use blocking-pop when reading from the queue (as
        opposed to polling). Default is true.
    :param connection_pool: a redis-py ``ConnectionPool`` instance.
    :param url: url for Redis connection.
    :param host: hostname of the Redis server.
    :param port: port number.
    :param password: password for Redis.
    :param int db: Redis database to use (typically 0-15, default is 0).
    :param bool notify_result: use a blocking-pop on a result-ready key to
        enable low-latency result reading.
    :param int notify_result_ttl: TTL for result-ready key to automatically
        expire un-awaited results.

.. py:class:: PriorityRedisExpireHuey

    Combines behavior of :py:class:`RedisExpireHuey` and
    :py:class:`PriorityRedisHuey`.

.. py:class:: SqliteHuey

    :py:class:`Huey` that utilizes sqlite3 for queue and result storage. Only
    requirement is the standard library ``sqlite3`` module.

    Commonly-used keyword arguments:

    :param str filename: filename for database, defaults to 'huey.db'.
    :param int cache_mb: megabytes of memory to allow for sqlite page-cache.
    :param bool fsync: use durable writes. Slower but more resilient to
        corruption in the event of sudden power loss. Defaults to false.

    SqliteHuey fully supports task priorities.

    .. seealso:: :py:class:`SqliteStorage`

.. py:class:: MemoryHuey

    :py:class:`Huey` that uses in-memory storage. Only should be used when
    testing or when using ``immediate`` mode. MemoryHuey fully supports task
    priorities.

.. py:class:: FileHuey

    :py:class:`Huey` that uses the file-system for storage. Should not be used
    in high-throughput, highly-concurrent environments, as the
    :py:class:`FileStorage` utilizes exclusive locks around all file-system
    operations.

    :param str path: base-path for huey data (queue tasks, schedule and results
        will be stored in sub-directories of this path).
    :param int levels: number of levels in result-file directory structure to
        ensure the results directory does not contain an unmanageable number of
        files.
    :param bool use_thread_lock: use the standard lib ``threading.Lock``
        instead of a lockfile for file-system operations. This should only be
        enabled when using the greenlet or thread consumer worker models.

    FileHuey fully supports task priorities.

.. py:class:: BlackHoleHuey

    :py:class:`Huey` that uses :py:class:`BlackHoleStorage`. All storage
    operations are no-ops: enqueued tasks are silently discarded and the result
    store is always empty. Intended for testing scenarios where you want to
    verify that tasks are being called without actually running them or storing
    anything.


Huey object
-----------

.. py:class:: Huey(name='huey', results=True, store_none=False, utc=True, immediate=False, serializer=None, compression=False, use_zlib=False, immediate_use_memory=True, storage_kwargs)

    :param str name: the name of the task queue, e.g. your application's name.
    :param bool results: whether to store task results.
    :param bool store_none: whether to store ``None`` in the result store.
    :param bool utc: use UTC internally, convert naive datetimes from local
        time to UTC (if local time is other than UTC).
    :param bool immediate: useful for debugging; causes tasks to be executed
        synchronously in the application.
    :param Serializer serializer: serializer implementation for tasks and
        result data. The default implementation uses ``pickle``.
    :param bool compression: compress tasks and result data.
    :param bool use_zlib: use zlib for compression instead of gzip.
    :param bool immediate_use_memory: automatically switch to a local in-memory
        storage backend whenever immediate-mode is enabled.
    :param storage_kwargs: arbitrary keyword arguments that will be passed to
        the storage backend for additional configuration.

    Huey executes tasks by exposing function decorators that cause the function
    call to be enqueued for execution by the consumer.

    Typically your application will only need one Huey instance, but you can
    have as many as you like -- the only caveat is that one consumer process
    must be executed for each Huey instance.

    Example usage:

    .. code-block:: python

        # demo.py
        from huey import RedisHuey

        # Create a huey instance.
        huey = RedisHuey('my-app')

        @huey.task()
        def add_numbers(a, b):
            return a + b

        @huey.periodic_task(crontab(minute='0', hour='2'))
        def nightly_report():
            generate_nightly_report()

    To run the consumer with 4 worker threads:

    .. code-block:: console

        $ huey_consumer.py demo.huey -w 4

    To add two numbers, the "huey" way:

    .. code-block:: pycon

        >>> from demo import add_numbers
        >>> res = add_numbers(1, 2)
        >>> res(blocking=True)  # Blocks until result is available.
        3

    To test huey without using a consumer, you can use "immediate" mode.
    Immediate mode follows all the same code paths as Huey does when running
    the consumer process, but does so synchronously within the application.

    .. code-block:: pycon

        >>> from demo import add_numbers, huey
        >>> huey.immediate = True  # Tasks executed immediately.
        >>> res = add_numbers(2, 3)
        >>> res()
        5

    .. py:attribute:: immediate

        The ``immediate`` property is used to enable and disable :ref:`immediate mode <immediate>`.
        When immediate mode is enabled, task-decorated functions are executed
        synchronously by the caller, making it very useful for development and
        testing. Calling a task function still returns a :py:class:`Result`
        handle, but the task itself is executed immediately.

        By default, when immediate mode is enabled, Huey will switch to using
        in-memory storage. This is to help prevent accidentally writing to a
        live Redis server while testing. To disable this functionality, specify
        ``immediate_use_memory=False`` when initializing :py:class:`Huey`.

        Enabling immediate mode:

        .. code-block:: python

            huey = RedisHuey()

            # Enable immediate mode. Tasks now executed synchronously.
            # Additionally, huey will now use in-memory storage.
            huey.immediate = True

            # Disable immediate mode. Tasks will now be enqueued in a Redis
            # queue.
            huey.immediate = False

        Immediate mode can also be specified when your Huey instance is
        created:

        .. code-block:: python

            huey = RedisHuey(immediate=True)

    .. py:method:: create_consumer(**options)

        :param options: keyword arguments passed to the :py:class:`Consumer`
            constructor (e.g. ``workers``, ``worker_type``, ``periodic``,
            ``initial_delay``, etc.).
        :returns: a :py:class:`Consumer` instance.

        Create a consumer programmatically, rather than using the
        ``huey_consumer.py`` command-line tool. This is useful for embedding
        the consumer within your own application process, or for advanced
        testing scenarios.

        .. code-block:: python

            consumer = huey.create_consumer(workers=4, worker_type='thread')
            consumer.start()
            # ... later ...
            consumer.stop(graceful=True)

    .. py:method:: task(retries=0, retry_delay=0, priority=None, context=False, name=None, expires=None, timeout=None, **kwargs)

        :param int retries: number of times to retry the function if an
            unhandled exception occurs when it is executed.
        :param int retry_delay: number of seconds to wait between retries.
        :param int priority: priority assigned to task, higher numbers are
            processed first by the consumer when there is a backlog.
        :param bool context: when the task is executed, include the
            :py:class:`Task` instance as a keyword argument.
        :param str name: name for this task. If not provided, Huey will default
            to using the module name plus function name.
        :param expires: set expiration time for task - if task is not run
            before ``expires``, it will be discarded. The ``expires`` parameter
            can be either an integer (seconds), a timedelta, or a datetime. For
            relative expiration values, the expire time will be resolved when
            the task is enqueued.
        :param int timeout: set execution timeout for task. Implementation
            used by the consumer is specific to the worker type and is NOT
            available for threads. Processes use SIGALRM, greenlet uses
            ``gevent.Timeout``. When using with threads it is necessary to use
            cooperative timeout checking. See :ref:`cooperative-timeout` for
            example.
        :param kwargs: arbitrary key/value arguments that are passed to the
            :py:class:`TaskWrapper` instance.
        :returns: a :py:class:`TaskWrapper` that wraps the decorated function
            and exposes a number of APIs for enqueueing the task.

        Function decorator that marks the decorated function for processing by
        the consumer. Calls to the decorated function will do the following:

        1. Serialize the function call into a :py:class:`Message` suitable for
           storing in the queue.
        2. Enqueue the message for execution by the consumer.
        3. Return a :py:class:`Result` handle, which can be used to check the
           result of the task function, revoke the task (assuming it hasn't
           started yet), reschedule the task, and more.

        The ``task()`` decorator returns a :py:class:`TaskWrapper`, which
        implements special methods for enqueueing the decorated function,
        :py:meth:`~TaskWrapper.schedule` it for the future, chain tasks to
        form a pipeline, and more.

        Example task:

        .. code-block:: python

            @huey.task()
            def slow(n):
                time.sleep(n)
                return n

        Calling the ``slow()`` task will return immediately. We can block until
        the task finishes by waiting for the result:

        .. code-block:: pycon

            >>> res = slow(10)  # Returns immediately.

            >>> res()  # Non-blocking read - returns None if not ready.

            >>> res(blocking=True)  # Block until task finishes, ~10s.
            10

        When ``context=True``, the :py:class:`Task` instance is passed to
        your function as a ``task`` keyword argument. This gives access to
        the task ID, remaining retries, and :ref:`cooperative timeout
        <cooperative-timeout>` APIs.

        When the result store is disabled (``results=False``), calling a
        task-decorated function returns ``None`` instead of a
        :py:class:`Result` handle.

        If you stack additional decorators on a task function, note that
        decorators **above** ``@huey.task()`` run in the calling process,
        while decorators **below** it run in the consumer worker.

        For a thorough walkthrough with examples, see the :ref:`guide`. For
        the full :py:class:`TaskWrapper` API (scheduling, pipelines,
        revocation, etc.), see :py:class:`TaskWrapper`, :py:class:`Task`,
        and :py:class:`Result`.

    .. py:method:: periodic_task(validate_datetime, retries=0, retry_delay=0, priority=None, context=False, name=None, expires=None, timeout=None, **kwargs)

        :param function validate_datetime: function which accepts a
            ``datetime`` instance and returns whether the task should be
            executed at the given time.
        :param int retries: number of times to retry the function if an
            unhandled exception occurs when it is executed.
        :param int retry_delay: number of seconds to wait in-between retries.
        :param int priority: priority assigned to task, higher numbers are
            processed first by the consumer when there is a backlog.
        :param bool context: when the task is executed, include the
            :py:class:`Task` instance as a parameter.
        :param str name: name for this task. If not provided, Huey will default
            to using the module name plus function name.
        :param expires: set expiration time for task - if task is not run
            before ``expires``, it will be discarded. The ``expires`` parameter
            can be either an integer (seconds), a timedelta, or a datetime. For
            relative expiration values, the expire time will be resolved when
            the task is enqueued.
        :param int timeout: set execution timeout for task. Implementation
            used by the consumer is specific to the worker type and is NOT
            available for threads. Processes use SIGALRM, greenlet uses
            ``gevent.Timeout``. When using with threads it is necessary to use
            cooperative timeout checking. See :ref:`cooperative-timeout` for
            example.
        :param kwargs: arbitrary key/value arguments that are passed to the
            :py:class:`TaskWrapper` instance.
        :returns: a :py:class:`TaskWrapper` that wraps the decorated function
            and exposes a number of APIs for enqueueing the task.

        The ``periodic_task()`` decorator marks a function for automatic
        execution by the consumer *at a specific interval*, like ``cron``.
        The ``validate_datetime`` parameter is typically the :py:func:`crontab`
        helper (described below). The consumer checks once per minute whether
        the function should run.

        Example — execute every three hours, on the hour:

        .. code-block:: python

            @huey.periodic_task(crontab(minute='0', hour='*/3'))
            def update_feeds():
                for feed in my_list_of_feeds:
                    fetch_feed_data(feed)

        .. note::
            Because functions decorated with ``periodic_task`` are meant to be
            executed at intervals in isolation, they should not take any
            required parameters nor should they be expected to return a
            meaningful value.

        Like :py:meth:`~Huey.task`, the periodic task decorator adds helpers
        to the decorated function. These helpers allow you to
        :py:meth:`~TaskWrapper.revoke` and :py:meth:`~TaskWrapper.restore` the
        periodic task, enabling you to pause it or prevent its execution. For
        more information, see :py:class:`TaskWrapper`.

        .. note::
            The result (return value) of a periodic task is not stored in the
            result store. This is primarily due to the fact that there is not
            an obvious way one would read such results, since the invocation of
            the periodic task happens inside the consumer scheduler. As such,
            there is no task result handle which the user could use to read the
            result. To store the results of periodic tasks, you will need to
            use your own storage or use the storage APIs directly:

            .. code-block:: python

                @huey.periodic_task(crontab(minute='*/10'))
                def my_task():
                    # do some work...
                    do_something()

                    # Manually store some data in the result store.
                    huey.put('my-task', some_data_to_store)

            More info:

            * :py:meth:`Huey.put`
            * :py:meth:`Huey.get`

    .. py:method:: context_task(obj, as_argument=False, **kwargs)

        :param obj: object that implements the context-manager APIs.
        :param bool as_argument: pass the return value of the context-manager's
            ``__enter__`` method into the decorated task as the first argument.
        :param kwargs: additional keyword arguments are forwarded to
            :py:meth:`~Huey.task` (e.g. ``retries``, ``retry_delay``,
            ``priority``, ``context``, ``name``, ``expires``, ``timeout``).
        :returns: a :py:class:`TaskWrapper` that wraps the decorated function
            and exposes a number of APIs for enqueueing the task.

        This is an extended implementation of the :py:meth:`Huey.task`
        decorator, which wraps the decorated task in a ``with obj:`` block.
        Roughly equivalent to:

        .. code-block:: python

            db = PostgresqlDatabase(...)

            @huey.task()
            def without_context_task(n):
                with db:
                    do_something(n)

            @huey.context_task(db)
            def with_context_task(n):
                return do_something(n)

        When ``as_argument=True``, the value returned by ``__enter__`` is
        passed as the first positional argument to the task function:

        .. code-block:: python

            @huey.context_task(db, as_argument=True)
            def with_ctx(conn, n):
                # conn is the value returned by db.__enter__()
                return conn.execute(n)

    .. py:method:: pre_execute(name=None)

        :param name: (optional) name for the hook.
        :returns: a decorator used to wrap the actual pre-execute function.

        Decorator for registering a pre-execute hook. The callback will be
        executed before the execution of every task. Execution of the task can
        be cancelled by raising a :py:class:`CancelExecution` exception.
        Uncaught exceptions will be logged but will not cause the task itself
        to be cancelled.

        The callback function should accept a single task instance, the return
        value is ignored.

        Hooks are executed in the order in which they are registered.

        Usage:

        .. code-block:: python

            @huey.pre_execute()
            def my_pre_execute_hook(task):
                if datetime.datetime.now().weekday() == 6:
                    raise CancelExecution('Sunday -- no work will be done.')

    .. py:method:: unregister_pre_execute(name_or_fn)

        :param name_or_fn: the name given to the pre-execute hook, or the
            function object itself.
        :returns: boolean

        Unregister the specified pre-execute hook.

    .. py:method:: post_execute(name=None)

        :param name: (optional) name for the hook.
        :returns: a decorator used to wrap the actual post-execute function.

        Register a post-execute hook. The callback will be executed after the
        execution of every task. Uncaught exceptions will be logged but will
        have no other effect on the overall operation of the consumer.

        The callback function should accept:

        * a :py:class:`Task` instance
        * the return value from the execution of the task (which may be None)
        * any exception that was raised during the execution of the task (which
          will be None for tasks that executed normally).

        The return value of the callback itself is ignored.

        Hooks are executed in the order in which they are registered.

        Usage:

        .. code-block:: python

            @huey.post_execute()
            def my_post_execute_hook(task, task_value, exc):
                do_something()

    .. py:method:: unregister_post_execute(name_or_fn)

        :param name_or_fn: the name given to the post-execute hook, or the
            function object itself.
        :returns: boolean

        Unregister the specified post-execute hook.

    .. py:method:: on_startup(name=None)

        :param name: (optional) name for the hook.
        :returns: a decorator used to wrap the actual on-startup function.

        Register a startup hook. The callback will be executed whenever a
        worker comes online. Uncaught exceptions will be logged but will
        have no other effect on the overall operation of the worker.

        The callback function must not accept any parameters.

        This API is provided to simplify setting up shared resources that, for
        whatever reason, should not be created as import-time side-effects. For
        example, your tasks need to write data into a Postgres database. If you
        create the connection at import-time, before the worker processes are
        spawned, you'll likely run into errors when attempting to use the
        connection from the child (worker) processes. To avoid this problem,
        you can register a startup hook which executes once when the worker
        starts up.

        Usage:

        .. code-block:: python

            db_connection = None

            @huey.on_startup()
            def setup_db_connection():
                global db_connection
                db_connection = psycopg2.connect(database='my_db')

            @huey.task()
            def write_data(rows):
                cursor = db_connection.cursor()
                # ...

    .. py:method:: unregister_on_startup(name_or_fn)

        :param name_or_fn: the name given to the on-startup hook, or the
            function object itself.
        :returns: boolean

        Unregister the specified on-startup hook.

    .. py:method:: on_shutdown(name=None)

        :param name: (optional) name for the hook.
        :returns: a decorator used to wrap the actual on-shutdown function.

        Register a shutdown hook. The callback will be executed by a worker
        immediately before it goes offline. Uncaught exceptions will be logged
        but will have no other effect on the overall shutdown of the worker.

        The callback function must not accept any parameters.

        This API is provided to simplify cleaning-up shared resources.

    .. py:method:: unregister_on_shutdown(name_or_fn)

        :param name_or_fn: the name given to the on-shutdown hook, or the
            function object itself.
        :returns: boolean

        Unregister the specified on-shutdown hook.

    .. py:method:: signal(*signals)

        :param signals: zero or more signals to handle.
        :returns: a decorator used to wrap the actual signal handler.

        Attach a signal handler callback, which will be executed when the
        specified signals are sent by the consumer. If no signals are listed,
        then the handler will be bound to **all** signals. The list of signals
        and additional information can be found in the :ref:`signals`
        documentation.

        Example:

        .. code-block:: python

            from huey.signals import SIGNAL_ERROR, SIGNAL_LOCKED

            @huey.signal(SIGNAL_ERROR, SIGNAL_LOCKED)
            def task_not_run_handler(signal, task, exc=None):
                # Do something in response to the "ERROR" or "LOCKED" signals.
                # Note that the "ERROR" signal includes a third parameter,
                # which is the unhandled exception that was raised by the task.
                # Since this parameter is not sent with the "LOCKED" signal, we
                # provide a default of ``exc=None``.
                pass

    .. py:method:: disconnect_signal(receiver, *signals)

        :param receiver: the signal handling function to disconnect.
        :param signals: zero or more signals to stop handling.

        Disconnect the signal handler from the provided signals. If no signals
        are provided, then the handler is disconnected from any signals it may
        have been connected to.

    .. py:method:: notify_interrupted_tasks()

        Emit ``SIGNAL_INTERRUPTED`` for every task that is currently being
        executed (i.e. in-flight). This is called automatically by the consumer
        during shutdown. Application code should not normally need to call this
        method directly, but it is available for custom consumer implementations
        or advanced testing.

        Tasks are tracked from the moment execution begins until execution
        completes (or fails). If the consumer is killed mid-task, those tasks
        remain in the ``_tasks_in_flight`` set, and this method emits
        ``SIGNAL_INTERRUPTED`` for each one.

    .. py:method:: enqueue(task)

        :param task: a :py:class:`Task` instance, a :py:class:`group`, or a
            :py:class:`chord`.

        :returns: depends on the input type (see below).

        Enqueue the given task, group, or chord for execution. When the result
        store is enabled (default), the return value depends on what was
        enqueued:

        * A single :py:class:`Task`: returns a :py:class:`Result` handle.
        * A :py:class:`Task` with a pipeline (via :py:meth:`Task.then`):
          returns a :py:class:`ResultGroup` containing a :py:class:`Result`
          for each task in the pipeline.
        * A :py:class:`group`: returns a :py:class:`ResultGroup` containing a
          :py:class:`Result` for each member task.
        * A :py:class:`chord`: returns a :py:class:`ChordResult`, which
          provides access to the member results, the callback result, and any
          tasks chained after the callback.

        .. note::
            Calling (or scheduling) a ``task``-decorated function will
            automatically enqueue a task for execution. You only need to call
            :py:meth:`~Huey.enqueue` directly when working with pipelines,
            groups, or chords.

    .. py:method:: revoke(task, revoke_until=None, revoke_once=False)

        .. seealso:: Use :py:meth:`Result.revoke` instead.

    .. py:method:: revoke_by_id(task_id, revoke_until=None, revoke_once=False)

        :param str task_id: task instance id.
        :param datetime revoke_until: optional expiration date for revocation.
        :param bool revoke_once: revoke once and then re-enable.

        Revoke a :py:class:`Task` instance using the task id.

    .. py:method:: revoke_all(task_class, revoke_until=None, revoke_once=False)

        .. seealso:: Use :py:meth:`TaskWrapper.revoke` instead.

    .. py:method:: restore(task)

        .. seealso:: Use :py:meth:`Result.restore` instead.

    .. py:method:: restore_by_id(task_id)

        :param str task_id: task instance id.
        :returns: boolean indicating success.

        Restore a :py:class:`Task` instance using the task id. Returns boolean
        indicating if the revocation was successfully removed.

    .. py:method:: restore_all(task_class)

        .. seealso:: Use :py:meth:`TaskWrapper.restore` instead.

    .. py:method:: is_revoked(task, timestamp=None)

        :param task: either a task instance, a task ID, a Result, or a Task class.

        This method should rarely need to be called directly. Typically you
        should rather use the ``is_revoked`` method on the object that is being
        revoked, for example:

        .. code-block:: python

            @huey.task()
            def greet(name):
                return 'Hello %s' % name

            r = greet.schedule(delay=60, args=('Huey',))
            r.revoke()  # Revoke this task.
            r.is_revoked()  # True.

            greet.revoke()  # Revoke ALL invocations of this task.
            greet.is_revoked()  # True.

        .. seealso::
            For task instances, use :py:meth:`Result.is_revoked`.

            For task functions, use :py:meth:`TaskWrapper.is_revoked`.

    .. py:method:: result(task_id, blocking=False, timeout=None, backoff=1.15, max_delay=1.0, revoke_on_timeout=False, preserve=False)

        :param task_id: the task's unique identifier.
        :param bool blocking: whether to block while waiting for task result
        :param timeout: number of seconds to block (if ``blocking=True``)
        :param backoff: amount to backoff delay each iteration of loop
        :param max_delay: maximum amount of time to wait between iterations when
            attempting to fetch result.
        :param bool revoke_on_timeout: if a timeout occurs, revoke the task,
            thereby preventing it from running if it is has not started yet.
        :param bool preserve: when set to ``True``, this parameter ensures that
            the task result will be preserved after having been successfully
            retrieved. Ordinarily, Huey will discard results after they have
            been read, to prevent the result store from growing without bounds.

        Attempts to retrieve the return value of a task. By default, :py:meth:`~Huey.result`
        will simply check for the value, returning ``None`` if it is not ready
        yet. If you want to wait for the result, specify ``blocking=True``.
        This will loop, backing off up to the provided ``max_delay``, until the
        value is ready or the ``timeout`` is reached. If the ``timeout`` is
        reached before the result is ready, a :py:class:`ResultTimeout` will be
        raised.

        .. seealso::
            :py:class:`Result` - the :py:meth:`~Huey.result` method is simply a
            wrapper that creates a ``Result`` object and calls its
            :py:meth:`~Result.get` method.

        .. note:: If the task failed with an exception, then a
            :py:class:`TaskException` that wraps the original exception will be
            raised.

        .. warning:: By default the result store will delete a task's return
            value after the value has been successfully read (by a successful
            call to the :py:meth:`~Huey.result` or :py:meth:`Result.get`
            methods). If you intend to access the task result multiple times,
            you must specify ``preserve=True`` when calling these methods.

    .. py:method:: lock_task(lock_name)

        :param str lock_name: Name to use for the lock.
        :returns: :py:class:`TaskLock` instance, which can be used as a
            decorator or context-manager.

        Utilize the Storage key/value APIs to implement simple locking.

        This lock is designed to be used to prevent multiple invocations of a
        task from running concurrently. Can be used as either a context-manager
        within the task, or as a task decorator. If using as a decorator, place
        it directly above the function declaration.

        If a second invocation occurs and the lock cannot be acquired, then a
        :py:class:`TaskLockedException` is raised, which is handled by the
        consumer. The task will not be executed and a ``SIGNAL_LOCKED`` will be
        sent. If the task is configured to be retried, then it will be retried
        normally.

        Examples:

        .. code-block:: python

            @huey.periodic_task(crontab(minute='*/5'))
            @huey.lock_task('reports-lock')  # Goes *after* the task decorator.
            def generate_report():
                # If a report takes longer than 5 minutes to generate, we do
                # not want to kick off another until the previous invocation
                # has finished.
                run_report()

            @huey.periodic_task(crontab(minute='0'))
            def backup():
                # Generate backup of code
                do_code_backup()

                # Generate database backup. Since this may take longer than an
                # hour, we want to ensure that it is not run concurrently.
                with huey.lock_task('db-backup'):
                    do_db_backup()

    .. py:method:: is_locked(lock_name)

        :param str lock_name: Name of lock to check.
        :returns: boolean value indicating whether lock is held or not.

    .. py:method:: flush_locks(*names)

        :param names: optional additional lock-names to flush.
        :returns: set of lock names that were held and subsequently cleared.

        Flush any locks that may be held. Locks created by using
        :py:meth:`~Huey.lock_task` as a **decorator** are automatically
        discovered (registered at import time). Locks created inside a
        function body using the **context-manager** form are not automatically
        discovered, and their names must be passed explicitly.

        When ``names`` are provided, both the discovered locks **and** the
        explicitly named locks are flushed.

        .. code-block:: python

            # Decorator form — automatically discovered:
            @huey.periodic_task(crontab(minute='*/5'))
            @huey.lock_task('reports-lock')
            def generate_report():
                run_report()

            # Context-manager form — NOT automatically discovered:
            @huey.task()
            def backup():
                with huey.lock_task('db-backup'):
                    do_db_backup()

            # Flush discovered locks only:
            huey.flush_locks()  # Clears 'reports-lock' if held.

            # Flush discovered locks AND the context-manager lock:
            huey.flush_locks('db-backup')  # Clears both.

    .. py:method:: rate_limit(name, limit, per, retry=True)

        :param str name: Name to use for the rate-limiter.
        :param int limit: Maximum invocations in the given window.
        :param int per: Size of rate-limiting window in seconds.
        :param bool retry: Automatically reschedule rate-limited tasks to run
            at beginning of next rate-limit window.
        :returns: :py:class:`RateLimit` instance, which can be used as a
            decorator or context-manager.

        Simple fixed-window rate-limiting for tasks.

        When a task fails due to being rate-limited, it will be automatically
        rescheduled to run at the start of the next window when ``retry=True`` or
        the task itself has one or more ``retries``.

        Tasks that fail due to rate-limiting will emit a ``SIGNAL_RATE_LIMITED``.

        By default any task that is rate-limited will be retried at the start
        of the next rate-limiting window. For instance say we have a task that
        is limited to 10 calls / 60 seconds. The 11th call in a given 60s
        period will be retried at the start of the next window (~1 to 60 seconds
        later, depending on timing).

        This is good for tasks that must not be lost. There is a risk if the
        volume of tasks continually exceeds the rate-limit that the automatic
        retries will grow continuously. To mitigate this you can specify the
        number of retries in the task decorator and disable automatic retries
        on the rate limiter. See examples below.

        Example of limiting to 10 calls per minute. Tasks that are limited will
        automatically be retried at the start of the next rate-limit window.

        .. code-block:: python

            @huey.task()
            @huey.rate_limit('data_sync', limit=10, per=60)
            def data_sync(data):
                service.apply_updates(data)

        In the above example, if a task fails due to being rate-limited, it
        will be rescheduled for the start of the next window. If it fails
        again due to rate-limiting, it will again be rescheduled, etc.

        Example of limiting to 10 calls per minute AND only allowing 2 retries.
        This mitigates unbounded growth for rate-limits that are continuously
        being hit:

        .. code-block:: python

            @huey.task(retries=2)
            @huey.rate_limit('data_sync', limit=10, per=60)
            def data_sync(data):
                service.apply_updates(data)

        In the above example, if a task fails due to being rate-limited, it
        will be rescheduled for the start of the next window up to 2 times.

        Equivalent example using a context-manager instead of a decorator:

        .. code-block:: python

            @huey.task(retries=2)
            def data_sync(data):
                with huey.rate_limit('data_sync', limit=10, per=60):
                    service.apply_updates(data)

        By default, rate-limited tasks are scheduled to be retried at the
        beginning of the next rate-limit window. If a task specifies an
        explicit ``retry_delay``, however, that value will be used instead:

        .. code-block:: python

            @huey.task(retries=2, retry_delay=120)
            @huey.rate_limit('data_sync', limit=10, per=60)
            def data_sync(data):
                service.apply_updates(data)

        In the above code, if the task fails due to being rate-limited, it will
        be retried up to 2 times after a delay of 120s between retries.

    .. py:method:: put(key, value)

        :param key: key for data
        :param value: arbitrary data to store in result store.

        Store a value in the result-store under the given key.

    .. py:method:: get(key, peek=False)

        :param key: key to read
        :param bool peek: non-destructive read

        Read a value from the result-store at the given key. By default reads
        are destructive. To preserve the value for additional reads, specify
        ``peek=True``.

    .. py:method:: delete(key)

        :param key: key to delete from the result store.
        :returns: boolean indicating whether the key existed and was deleted.

        Remove a value from the result-store at the given key. Useful for
        cleaning up manually-stored data created with :py:meth:`~Huey.put`.

    .. py:method:: put_if_empty(key, value)

        :param key: key to store data under.
        :param value: arbitrary data to store.
        :returns: boolean indicating whether the value was stored. Returns
            ``False`` if the key already exists.

        Atomically store a value only if the key does not already exist. This
        is the primitive used internally by :py:class:`TaskLock` to implement
        exclusive locking. It can also be used to build custom coordination
        patterns like task deduplication.

    .. py:method:: pending(limit=None)

        :param int limit: optionally limit the number of tasks returned.
        :returns: a list of :py:class:`Task` instances waiting to be run.

        .. note::
            This method must deserialize every task in the queue, which can be
            slow if the queue is large. Use :py:meth:`~Huey.pending_count` when
            you only need the count.

    .. py:method:: pending_count()

        :returns: the number of tasks currently in the queue, without
            deserializing them.

    .. py:method:: scheduled(limit=None)

        :param int limit: optionally limit the number of tasks returned.
        :returns: a list of :py:class:`Task` instances that are scheduled to
            execute at some time in the future.

        .. note::
            This method deserializes every task on the schedule. Use
            :py:meth:`~Huey.scheduled_count` when you only need the count.

    .. py:method:: scheduled_count()

        :returns: the number of tasks currently in the schedule, without
            deserializing them.

    .. py:method:: all_results()

        :returns: a dict of task-id to the serialized result data for all
            key/value pairs in the result store.

    .. py:method:: result_count()

        :returns: the number of key/value pairs in the result store.

    .. py:method:: flush()

        Remove all data from the queue, schedule, and result store. This is
        a destructive operation. Primarily useful for testing.

    .. py:method:: __len__()

        Return the number of items currently in the queue.


.. py:class:: TaskWrapper(huey, func, retries=None, retry_delay=None, context=False, name=None, task_base=None, **settings)

    :param Huey huey: A huey instance.
    :param func: User function.
    :param int retries: Upon failure, number of times to retry the task.
    :param int retry_delay: Number of seconds to wait before retrying after a
        failure/exception.
    :param bool context: when the task is executed, include the
        :py:class:`Task` instance as a parameter.
    :param str name: Name for task (will be determined based on task module and
        function name if not provided).
    :param task_base: Base-class for task, defaults to :py:class:`Task`.
    :param settings: Arbitrary settings to pass to the task class constructor.

    Wrapper around a user-defined function that converts function calls into
    tasks executed by the consumer. The wrapper, which decorates the function,
    replaces the function in the scope with a :py:class:`TaskWrapper` instance.

    The wrapper class, when called, will enqueue the requested function call
    for execution by the consumer.

    .. note::
        You should not need to create :py:class:`TaskWrapper` instances
        directly. The :py:meth:`Huey.task` and :py:meth:`Huey.periodic_task`
        decorators will create the appropriate TaskWrapper automatically.

    .. py:method:: schedule(args=None, kwargs=None, eta=None, delay=None, priority=None, retries=None, retry_delay=None, expires=None, timeout=None, id=None)

        :param tuple args: arguments for decorated function.
        :param dict kwargs: keyword arguments for decorated function.
        :param datetime eta: the time at which the function should be executed.
        :param int delay: number of seconds to wait before executing function.
        :param int priority: priority assigned to task, higher numbers are
            processed first by the consumer when there is a backlog.
        :param int retries: number of times to retry the function if an
            unhandled exception occurs when it is executed.
        :param int retry_delay: number of seconds to wait between retries.
        :param expires: set expiration time for task - if task is not run
            before ``expires``, it will be discarded. The ``expires`` parameter
            can be either an integer (seconds), a timedelta, or a datetime. For
            relative expiration values, the expire time will be resolved when
            the task is enqueued.
        :param int timeout: set execution timeout for task. Implementation
            used by the consumer is specific to the worker type and is NOT
            available for threads. Processes use SIGALRM, greenlet uses
            ``gevent.Timeout``. When using with threads it is necessary to use
            cooperative timeout checking. See :ref:`cooperative-timeout` for
            example.
        :param id: assign the given ``id`` to the Task being scheduled.
        :returns: a :py:class:`Result` handle for the task.

        Use the ``schedule`` method to schedule the execution of the queue task
        for a given time in the future:

        .. code-block:: python

            import datetime

            one_hour = datetime.datetime.now() + datetime.timedelta(hours=1)

            # Schedule the task to be run in an hour. It will be called with
            # three arguments.
            res = check_feeds.schedule(args=(url1, url2, url3), eta=one_hour)

            # Equivalent, but uses delay rather than eta.
            res = check_feeds.schedule(args=(url1, url2, url3), delay=3600)

    .. py:method:: revoke(revoke_until=None, revoke_once=False)

        :param datetime revoke_until: Automatically restore the task after the
            given datetime.
        :param bool revoke_once: Revoke the next execution of the task and then
            automatically restore.

        Revoking a task will prevent any instance of the given task from
        executing. When no parameters are provided the function will not
        execute again until :py:meth:`TaskWrapper.restore` is called.

        This function can be called multiple times, but each call will
        supercede any restrictions from the previous revocation.

        .. code-block:: python

            # Skip the next execution
            send_emails.revoke(revoke_once=True)

            # Prevent any invocation from executing.
            send_emails.revoke()

            # Prevent any invocation for 24 hours.
            tomorrow = datetime.datetime.now() + datetime.timedelta(days=1)
            send_emails.revoke(revoke_until=tomorrow)

    .. py:method:: is_revoked(timestamp=None)

        :param datetime timestamp: If provided, checks whether task is revoked
            with respect to the given timestamp.
        :returns: bool indicating whether task is revoked.

        Check whether the given task is revoked.

    .. py:method:: restore()

        :returns: bool indicating whether a previous revocation rule was found
            and removed successfully.

        Removes a previous task revocation, if one was configured.

    .. py:method:: call_local()

        Call the ``@task``-decorated function, bypassing all Huey-specific
        logic. In other words, ``call_local()`` provides access to the
        underlying user-defined function.

        .. code-block:: pycon

            >>> add.call_local(1, 2)
            3

    .. py:method:: s(*args, **kwargs)

        :param args: Arguments for task function.
        :param kwargs: Keyword arguments for task function.
        :param int priority: assign priority override to task, higher numbers
            are processed first by the consumer when there is a backlog.
        :param expires: set expiration time for task - if task is not run
            before ``expires``, it will be discarded. The ``expires`` parameter
            can be either an integer (seconds), a timedelta, or a datetime. For
            relative expiration values, the expire time will be resolved when
            the task is enqueued.
        :param int timeout: set execution timeout for task. Implementation
            used by the consumer is specific to the worker type and is NOT
            available for threads. Processes use SIGALRM, greenlet uses
            ``gevent.Timeout``. When using with threads it is necessary to use
            cooperative timeout checking. See :ref:`cooperative-timeout` for
            example.
        :returns: a :py:class:`Task` instance representing the execution of the
            task function with the given arguments.

        Create a :py:class:`Task` instance representing the invocation of the
        task function with the given arguments and keyword-arguments.

        .. note:: The returned task instance is **not** enqueued automatically.

        .. warning::
            The following keyword argument names are reserved and will be
            intercepted by Huey rather than passed to your task function:
            ``eta``, ``delay``, ``retries``, ``retry_delay``, ``priority``,
            ``expires``, and ``timeout``. If your task function has a parameter
            with one of these names, rename the parameter or pass the value
            positionally.

        To illustrate the distinction, when you call a ``task()``-decorated
        function, behind-the-scenes, Huey is doing something like this:

        .. code-block:: python

            @huey.task()
            def add(a, b):
                return a + b

            result = add(1, 2)

            # Is equivalent to:
            task = add.s(1, 2)
            result = huey.enqueue(task)

        Typically, one will only use the :py:meth:`TaskWrapper.s` helper when
        creating task execution pipelines.

        For example:

        .. code-block:: python

            add_task = add.s(1, 2)  # Represent task invocation.
            pipeline = (add_task
                        .then(add, 3)  # Call add() with previous result and 3.
                        .then(add, 4)  # etc...
                        .then(add, 5))

            results = huey.enqueue(pipeline)

            # Print results of above pipeline.
            print(results.get(blocking=True))

            # [3, 6, 10, 15]

    .. py:method:: map(it)

        :param it: a list, tuple or generic iterable that contains the
            arguments for a number of individual task executions.
        :returns: a :py:class:`ResultGroup` encapsulating the individual
            :py:class:`Result` handlers for the task executions.

        .. note::
            The iterable should be a list of argument tuples which will be
            passed to the task function.

        Example:

        .. code-block:: python

            @huey.task()
            def add(a, b):
                return a + b

            rg = add.map([(i, i * i) for i in range(10)])

            # Resolve all results.
            rg.get(blocking=True)

            # [0, 2, 6, 12, 20, 30, 42, 56, 72, 90]

    .. py:method:: unregister()

        :returns: boolean indicating whether the task was found and removed
            from the registry.

        Remove this task from Huey's internal task registry. After
        unregistering, the consumer will no longer be able to deserialize or
        execute instances of this task. If the task is a periodic task, it will
        also be removed from the periodic task schedule.

        This is primarily useful when working with dynamically-created periodic
        tasks that need to be removed at runtime.



.. py:class:: Task(args=None, kwargs=None, id=None, eta=None, retries=None, retry_delay=None, expires=None, timeout=None, on_complete=None, on_error=None)

    :param tuple args: arguments for the function call.
    :param dict kwargs: keyword arguments for the function call.
    :param str id: unique id, defaults to a UUID if not provided.
    :param datetime eta: time at which task should be executed.
    :param int retries: automatic retry attempts.
    :param int retry_delay: seconds to wait before retrying a failed task.
    :param int priority: priority assigned to task, higher numbers are
        processed first by the consumer when there is a backlog.
    :param expires: set expiration time for task - if task is not run
        before ``expires``, it will be discarded. The ``expires`` parameter
        can be either an integer (seconds), a timedelta, or a datetime. For
        relative expiration values, the expire time will be resolved when
        the task is enqueued.
    :param int timeout: set execution timeout for task. Implementation
        used by the consumer is specific to the worker type and is NOT
        available for threads. Processes use SIGALRM, greenlet uses
        ``gevent.Timeout``. When using with threads it is necessary to use
        cooperative timeout checking. See :ref:`cooperative-timeout` for
        example.
    :param Task on_complete: Task to execute upon completion of this task.
    :param Task on_error: Task to execute upon failure / error.

    The ``Task`` class represents the execution of a function. Instances of the
    task are serialized and enqueued for execution by the consumer, which
    deserializes and executes the task function.

    .. note::
        You should not need to create instances of :py:class:`Task` directly,
        but instead use either the :py:meth:`Huey.task` decorator or
        the :py:meth:`TaskWrapper.s` method.

    Here's a refresher on how tasks work:

    .. code-block:: python

        @huey.task()
        def add(a, b):
            return a + b

        ret = add(1, 2)
        print(ret.get(blocking=True))  # "3".

        # The above two lines are equivalent to:
        task_instance = add.s(1, 2)  # Create a Task instance.
        ret = huey.enqueue(task_instance)  # Enqueue the queue task.
        print(ret.get(blocking=True))  # "3".

    .. py:attribute:: is_timed_out

        If task was configured with a ``timeout``, returns True if the task has
        exceeded the timeout. The task timer starts when the task begins to
        execute (after any pre-execute hooks are fired).

        This is a property and the return value is calculated dynamically.

    .. py:attribute:: time_remaining

        If task was configured with a ``timeout``, returns the amount of time
        remaining. For tasks that do not specify a timeout, this property
        returns ``float('inf')`` so it is always safe to compare.

        This is a property and the return value is calculated dynamically.

    .. py:method:: check_timeout()

        If task was configured with a ``timeout``, this method provides a
        single hook for cooperatively checking whether the task has exceeded
        its available time, and if so, raises a :class:`TaskTimeout`. This
        exception ensures that the ``SIGNAL_TIMEOUT`` fires for the task.

        This method is the only mechanism for enforcing a timeout when using
        ``thread`` workers.

        See :ref:`cooperative-timeout` for discussion.

    .. py:method:: then(task, *args, **kwargs)

        :param TaskWrapper task: A ``task()``-decorated function.
        :param args: Arguments to pass to the task.
        :param kwargs: Keyword arguments to pass to the task.
        :returns: The parent task.

        The :py:meth:`~Task.then` method is used to create task pipelines. A
        pipeline is a lot like a unix pipe, such that the return value from the
        parent task is then passed (along with any parameters specified by
        ``args`` and ``kwargs``) to the child task.

        Here's an example of chaining some addition operations:

        .. code-block:: python

            add_task = add.s(1, 2)  # Represent task invocation.
            pipeline = (add_task
                        .then(add, 3)  # Call add() with previous result and 3.
                        .then(add, 4)  # etc...
                        .then(add, 5))

            result_group = huey.enqueue(pipeline)

            print(result_group.get(blocking=True))

            # [3, 6, 10, 15]

        If the value returned by the parent function is a ``tuple``, then the
        tuple will be used to update the ``*args`` for the child function.
        Likewise, if the parent function returns a ``dict``, then the dict will
        be used to update the ``**kwargs`` for the child function.

        Example of chaining fibonacci calculations:

        .. code-block:: python

            @huey.task()
            def fib(a, b=1):
                a, b = a + b, a
                return (a, b)  # returns tuple, which is passed as *args

            pipe = (fib.s(1)
                    .then(fib)
                    .then(fib))
            result_group = huey.enqueue(pipe)

            print(result_group.get(blocking=True))
            # [(2, 1), (3, 2), (5, 3)]

    .. py:method:: error(task, *args, **kwargs)

        :param TaskWrapper task: A ``task()``-decorated function.
        :param args: Arguments to pass to the task.
        :param kwargs: Keyword arguments to pass to the task.
        :returns: The parent task.

        The :py:meth:`~Task.error` method is similar to the
        :py:meth:`~Task.then` method, which is used to construct a task
        pipeline, except the ``error()`` task will only be called in the event
        of an unhandled exception in the parent task.


.. py:function:: crontab(minute='*', hour='*', day='*', month='*', day_of_week='*'[, strict=False])

    Convert a "crontab"-style set of parameters into a test function that will
    return ``True`` when a given ``datetime`` matches the parameters set forth in
    the crontab.

    The argument order matches the standard Linux crontab format: minute, hour,
    day, month, day-of-week.

    Day-of-week uses 0=Sunday and 6=Saturday.

    Acceptable inputs:

    - `*` = every distinct value
    - `*/n` = run every "n" times, i.e. hours=`*/4` == 0, 4, 8, 12, 16, 20
    - `m-n` = run every time m..n
    - `m,n` = run on m and n

    :param bool strict: cause crontab to raise a ``ValueError`` if an input
       does not match a supported input format.
    :rtype: a test function that takes a ``datetime`` and returns a boolean

    .. note::
        It is currently not possible to run periodic tasks with an interval
        less than once per minute. If you need to run tasks more frequently,
        you can create a periodic task that runs once per minute, and from that
        task, schedule any number of sub-tasks to run after the desired delays.

.. py:function:: crontab.hourly()

    Convenience function for a task that should run every hour, on the hour.

.. py:function:: crontab.daily()

    Convenience function for a task that should run daily, at midnight.


.. py:class:: TaskLock(huey, name)

    This class should not be instantiated directly, but is instead returned by
    :py:meth:`Huey.lock_task`. This object implements a context-manager or
    decorator which can be used to ensure only one instance of the wrapped task
    is executed at a given time.

    If the consumer executes a task and encounters the
    :py:class:`TaskLockedException`, then the task will not be executed, an
    error will be logged by the consumer, and a ``SIGNAL_LOCKED`` signal will
    be emitted. If the task is configured with retries, it will be retried
    normally (the lock is released, so the retry has a chance to acquire it).

    See :py:meth:`Huey.lock_task` for example usage.

    .. py:method:: clear()

        Helper method to manually clear the lock. This method is provided to
        allow the lock to be flushed in the event that the consumer process was
        killed while executing a task holding the lock.

        Alternatively, at start-up time you can execute the consumer with the
        ``-f`` method which will flush all locks before beginning to execute
        tasks.

    .. py:method:: acquire()

        Acquire the lock, raising a :py:class:`TaskLockedException` if the lock
        could not be acquired. Otherwise, returns ``True``.

    .. py:method:: release()

        Identical to :py:meth:`~TaskLock.clear`.

    .. py:method:: locked()

        :returns: boolean whether lock is currently being held.

.. py:class:: RateLimit(huey, name, limit, per, retry=True)

    This class should not be instantiated directly, but is instead returned by
    :py:meth:`Huey.rate_limit`. This object implements a context-manager or
    decorator which can be used to enforce a simple fixed-window rate-limit of
    the wrapped block.

    When a task fails due to being rate-limited, it will be automatically
    rescheduled to run at the start of the next window when ``retry=True`` or
    the task itself has one or more ``retries``.

    Interaction between task retries and the ``retry`` flag on the rate-limit:

    * ``retry=True``, task has no retries: task will be retried at the start of
      the next window (or ``task.retry_delay`` if specified).
    * ``retry=True``, task has 1 or more retries: same as above, except task's
      own retry count is *preserved*.
    * ``retry=False``, task has no retries: error is the final state, task is
      not rescheduled.
    * ``retry=False``, task has 1 or more retries: task retries decrement
      normally and the task's ``retry_delay`` is honored.

    Rate-limited tasks emit a ``SIGNAL_RATE_LIMITED``.

    :param str name: Name to use for the rate-limiter.
    :param int limit: Maximum invocations in the given window.
    :param int per: Size of rate-limiting window in seconds.
    :param bool retry: Automatically reschedule rate-limited tasks to run
        at beginning of next rate-limit window.
    :returns: :py:class:`RateLimit` instance, which can be used as a
        decorator or context-manager.

    .. py:method:: reset()

        Reset the rate-limiter, clearing the current window and counter.
        The next call to a rate-limited task will start a fresh window.

    .. py:method:: current_usage()

        :returns: the number of invocations in the current rate-limit window.
            Returns ``0`` if no invocations have occurred in this window.

    .. py:method:: acquire()

        Check whether the rate-limit has been exceeded. If so, raises
        :py:class:`RateLimitExceeded`. Otherwise, increments the counter and
        returns normally. This is called automatically when the rate-limiter
        is used as a decorator or context-manager.



.. py:class:: group(tasks)

    A ``group`` is a lightweight wrapper around any number or types of tasks
    that may be executed in parallel. When a group is enqueued, Huey returns a
    :py:class:`ResultGroup` for reading the results.

    :param list tasks: any number of :py:class:`Task` instances.

    Example:

    .. code-block:: python

        @huey.task()
        def health_check(service):
            return service.name, perform_health_check(service)

        g = group([
            health_check.s(api_service),
            health_check.s(cache_service),
            health_check.s(db_service),
            health_check.s(proxy_service),
        ])
        result_group = huey.enqueue(g)

        for name, is_healthy in result_group(blocking=True):
            print('%s healthy? %s' % (name, is_healthy))

    .. py:method:: then(task, *args, **kwargs)

        :param task: A ``task()``-decorated function (:py:class:`TaskWrapper`),
            or a :py:class:`Task` instance to run with the group results.
        :param args: Arguments to pass to the callback task.
        :param kwargs: Keyword arguments to pass to the callback task.
        :returns: A :py:class:`chord` instance.

        Convert a :py:class:`group` into a :py:class:`chord` by attaching a
        callback. When all members have finished executing, the callback will
        be enqueued with the member results (as a list, in order).

        .. code-block:: python

            result = huey.enqueue(
                group([fetch.s(u) for u in urls])
                .then(aggregate))

    .. py:method:: error(task, *args, **kwargs)

        :param task: A ``task()``-decorated function (:py:class:`TaskWrapper`),
            or a :py:class:`Task` instance to run with the group results.
        :param args: Arguments to pass to the error handler.
        :param kwargs: Keyword arguments to pass to the error handler.
        :returns: the group instance.

        Attach an error handler to every member of the group. If any member
        raises an exception, the error handler will be enqueued with the
        exception as an argument. Supports chaining:

        .. code-block:: python

            result = huey.enqueue(
                group([fetch.s(u) for u in urls])
                .error(on_fetch_error)
                .then(aggregate))

.. py:class:: chord(tasks, callback)

    A :py:class:`chord` consists of a group of tasks that execute in parallel
    and a callback task. When all sub-tasks have completed (or permanently
    failed), their results are passed in order as a list to the callback task.

    :param list tasks: a list of :py:class:`Task` instances (including
        pipelines built with :py:meth:`Task.then`), :py:class:`chord`
        instances (for nesting), in any combination.
    :param callback: a ``task()``-decorated function (:py:class:`TaskWrapper`),
        or a :py:class:`Task` instance. The callback receives the list of
        sub-task results as its first argument.

    .. code-block:: python

        @huey.task()
        def fetch(url):
            return requests.get(url).json()

        @huey.task()
        def aggregate(results):
            return {r['id']: r for r in results}

        c = chord(
            [fetch.s(u) for u in urls],
            aggregate.s())
        result = huey.enqueue(c)

        # result is a ChordResult.
        data = result(blocking=True)  # Blocks until callback finishes.

    Enqueueing a chord returns a :py:class:`ChordResult`.

    .. note::
        The callback always receives the member results as a list, even if
        there is only one member. Results are ordered by the position of the
        member in the original list, not by the order in which members
        finished executing.

    **Sub-task errors:**

    Chords are designed to always complete. If a sub-task fails and exhausts
    all its retries, the exception is used as the task result. Tasks with
    retries will retry normally, only after retries are exhausted is the
    exception used.

    The callback may therefore receive a mix of normal return values and
    ``Exception`` objects. See :ref:`groups-and-chords` in the guide for
    patterns on handling mixed results.

    .. note::
        Revoking a chord member prevents it from running and will stall the
        chord. If you need to cancel a chord, revoke the callback task instead.

    **Pipeline members:**

    When a chord member is a pipeline (e.g. ``fetch.s(u).then(parse)``), Huey
    walks the ``on_complete`` chain and uses the end of the pipeline for the
    sub-task. This ensures the chord callback is not triggered until all
    pipeline members have fully finished.

    Error callbacks placed on individual tasks within a pipeline member
    operate independently of the chord.

    .. code-block:: python

        c = chord(
            [download.s(u).then(parse).then(validate) for u in urls],
            aggregate.s())

    .. py:method:: then(task, *args, **kwargs)

        :param task: A ``task()``-decorated function (:py:class:`TaskWrapper`),
            or a :py:class:`Task` instance.
        :param args: Arguments to pass to the task.
        :param kwargs: Keyword arguments to pass to the task.
        :returns: the :py:class:`chord` instance.

        Chain an additional task after the chord's callback. The callback's
        return value is passed to the chained task, exactly like
        :py:meth:`Task.then`. Multiple calls to ``then()`` extend the chain.

        When tasks are chained to the chord callback, the :py:class:`ChordResult`
        returned by :py:meth:`Huey.enqueue` will have a non-``None``
        ``pipeline_results`` attribute containing a :py:class:`ResultGroup`
        for the full callback pipeline.

        .. code-block:: python

            result = huey.enqueue(
                chord([fetch.s(u) for u in urls], aggregate.s())
                .then(generate_report)
                .then(send_email))

            # result.pipeline_results is a ResultGroup with three entries:
            # [aggregate result, generate_report result, send_email result]

        Delegates to the callback's :py:meth:`Task.then`.

    .. py:method:: error(task, *args, **kwargs)

        :param task: A ``task()``-decorated function (:py:class:`TaskWrapper`),
            or a :py:class:`Task` instance.
        :param args: Arguments to pass to the error handler.
        :param kwargs: Keyword arguments to pass to the error handler.
        :returns: the :py:class:`chord` instance.

        Attach an error handler to the chord's callback. If the callback
        raises an exception, this task will be enqueued with the exception
        as an argument.

        .. code-block:: python

            result = huey.enqueue(
                chord([fetch.s(u) for u in urls], aggregate.s())
                .error(alert_admin))

        This handles errors in the **callback**, not in the sub-tasks. To handle
        errors in individual members, use :py:meth:`Task.error` on each member
        or :py:meth:`group.error` before constructing the chord.

        Delegates to the callback's :py:meth:`Task.error`.

    **Nested chords:**

    Chord members can themselves be chords. The inner chord's callback
    pipeline serves as the synchronization point for the outer chord.

    .. code-block:: python

        inner1 = chord([a.s(), b.s()], merge.s())
        inner2 = chord([c.s(), d.s()], merge.s())

        result = huey.enqueue(chord([inner1, inner2], final.s()))

    When the inner chords complete and their callbacks finish, the outer
    chord's callback (``final``) receives the two inner callback results as a
    list. See :ref:`groups-and-chords` in the guide for a detailed example.


.. py:class:: ChordResult(results, callback_result, pipeline=None)

    Returned by :py:meth:`Huey.enqueue` when enqueueing a :py:class:`chord`.
    Provides access to the individual member results, the callback result,
    and the results of any tasks chained after the callback.

    .. py:attribute:: results

        A :py:class:`ResultGroup` containing the :py:class:`Result` handles
        for each chord member.

    .. py:attribute:: callback

        A :py:class:`Result` handle for the callback task.

    .. py:attribute:: pipeline_results

        A :py:class:`ResultGroup` containing :py:class:`Result` handles for
        the callback and every task chained after it via
        :py:meth:`chord.then`. The first entry is the callback itself, followed
        by each chained task in order.

        ``None`` if no tasks were chained after the callback.

        .. code-block:: python

            result = huey.enqueue(
                chord([a.s(), b.s()], combine.s())
                .then(report)
                .then(archive))

            result.pipeline_results[0]()  # combine result
            result.pipeline_results[1]()  # report result
            result.pipeline_results[2]()  # archive result

    .. py:method:: get(*args, **kwargs)

        Shortcut for ``self.callback.get(*args, **kwargs)``. Blocks until the
        callback finishes and returns its result.

    .. py:method:: __call__(*args, **kwargs)

        Identical to :py:meth:`~ChordResult.get`.

    .. py:method:: reset()

        Reset the callback result and allow re-fetching a new result for the
        given task (i.e. after a task error and subsequent retry).

Result
------

.. py:class:: Result(huey, task)

    Although you will probably never instantiate an ``Result`` object yourself,
    they are returned whenever you execute a task-decorated function, or
    schedule a task for execution. The ``Result`` object talks to the result
    store and is responsible for fetching results from tasks.

    Once the consumer finishes executing a task, the return value is placed in
    the result store, allowing the original caller to retrieve it.

    Getting results from tasks is very simple:

    .. code-block:: python

        >>> @huey.task()
        ... def add(a, b):
        ...     return a + b
        ...

        >>> res = add(1, 2)
        >>> res  # what is "res" ?
        <Result: task 6b6f36fc-da0d-4069-b46c-c0d4ccff1df6>

        >>> res()  # Fetch the result of this task.
        3

    What happens when data isn't available yet? Let's assume the next call
    takes about a minute to calculate::

        >>> res = add(100, 200)  # Imagine this is very slow.
        >>> res.get()  # Data is not ready, so None is returned.

        >>> res() is None  # We can omit ".get", it works the same way.
        True

        >>> res(blocking=True, timeout=5)  # Block for up to 5 seconds
        Traceback (most recent call last):
          File "<stdin>", line 1, in <module>
          File "/home/charles/tmp/huey/src/huey/huey/queue.py", line 46, in get
            raise ResultTimeout
        huey.exceptions.ResultTimeout

        >>> res(blocking=True)  # No timeout, will block until it gets data.
        300

    If the task failed with an exception, then a :py:class:`TaskException` will
    be raised when reading the result value::

        >>> @huey.task()
        ... def fails():
        ...     raise Exception('I failed')

        >>> res = fails()
        >>> res()  # raises a TaskException!
        Traceback (most recent call last):
          File "<stdin>", line 1, in <module>
          File "/home/charles/tmp/huey/src/huey/huey/api.py", line 684, in get
            raise TaskException(result.metadata)
        huey.exceptions.TaskException: Exception('I failed',)

    .. py:attribute:: id

        Returns the unique id of the corresponding task.

    .. py:method:: is_ready()

        :returns: whether the task result value is available.
        :rtype: bool

    .. py:method:: get(blocking=False, timeout=None, backoff=1.15, max_delay=1.0, revoke_on_timeout=False, preserve=False)

        :param bool blocking: whether to block while waiting for task result
        :param timeout: number of seconds to block (if ``blocking=True``)
        :param backoff: amount to backoff delay each iteration of loop
        :param max_delay: maximum amount of time to wait between iterations when
            attempting to fetch result.
        :param bool revoke_on_timeout: if a timeout occurs, revoke the task,
            thereby preventing it from running if it is has not started yet.
        :param bool preserve: when set to ``True``, this parameter ensures that
            the task result will be preserved after having been successfully
            retrieved. Ordinarily, Huey will discard results after they have
            been read, to prevent the result store from growing without bounds.
        :raises: ResultTimeout if blocking and timeout specified without result
            becoming ready yet.

        Attempt to retrieve the return value of a task.  By default,
        :py:meth:`~Result.get` will simply check for the value, returning
        ``None`` if it is not ready yet. If you want to wait for a value, you
        can specify ``blocking=True``. This will loop, backing off up to the
        provided ``max_delay``, until the value is ready or the ``timeout`` is
        reached. If the ``timeout`` is reached before the result is ready, a
        :py:class:`ResultTimeout` exception will be raised.

        .. note:: Instead of calling ``.get()``, you can simply call the
            :py:class:`Result` object directly. Both methods accept the same
            arguments.

    .. py:method:: __call__(**kwargs)

        Identical to the :py:meth:`~Result.get` method, provided as a shortcut.

    .. py:method:: revoke(revoke_once=True)

        :param bool revoke_once: revoke only once.

        Revoke the given task. Unless it is in the process of executing, the
        task will be discarded without being executed.

        .. code-block:: python

            one_hour = datetime.datetime.now() + datetime.timedelta(hours=1)

            # Run this command in an hour
            res = add.schedule((1, 2), eta=one_hour)

            # I changed my mind, do not run it after all.
            res.revoke()

    .. py:method:: restore()

        Restore the given task instance. Unless the task instance has already
        been dequeued and discarded, it will be restored and run as scheduled.

        .. warning::
            If the task class itself has been revoked, via a call to
            :py:meth:`TaskWrapper.revoke`, then this method has no effect.

    .. py:method:: is_revoked()

        Return a boolean value indicating whether this particular task instance
        **or** the task class itself has been revoked.

        .. seealso:: :py:meth:`TaskWrapper.is_revoked`.

    .. py:method:: reschedule(eta=None, delay=None, expires=None, priority=None, preserve_pipeline=True)

        :param datetime eta: execute function at the given time.
        :param int delay: execute function after specified delay in seconds.
        :param expires: set expiration time for task. If not provided, then the
            task's original expire time (if any) will be used.
        :param priority: override the task's priority. If not provided, the
            original priority is preserved.
        :param bool preserve_pipeline: when ``True`` (default), the
            rescheduled task retains any ``on_complete`` and ``on_error``
            chains from the original task. Set to ``False`` to discard them.
        :returns: :py:class:`Result` handle for the new task.

        Reschedule the given task. The original task instance will be revoked,
        but **no checks are made** to verify that it hasn't already been
        executed.

        If neither an ``eta`` nor a ``delay`` is specified, the task will be
        run as soon as it is received by a worker.

    .. py:method:: reset()

        Reset the cached result and allow re-fetching a new result for the
        given task. This is essential when a task fails and is retried: the
        first call to :py:meth:`~Result.get` caches the error locally, and
        subsequent calls return the cached error even after the retry succeeds.
        Calling ``reset()`` clears the local cache so the next ``get()`` reads
        from the result store again.

        .. code-block:: python

            result = flaky_task()
            try:
                result.get(blocking=True, timeout=5)
            except TaskException:
                result.reset()  # Clear cached error.
                # Now we can read the result from the successful retry:
                value = result.get(blocking=True, timeout=30)


.. py:class:: ResultGroup

    A ``ResultGroup`` will be returned when you enqueue a task pipeline or if
    you use the :py:meth:`TaskWrapper.map` method. It is a simple wrapper
    around a number of individual :py:meth:`Result` instances, and provides a
    convenience API for fetching the results in bulk.

    .. py:method:: get(**kwargs)

        Call :py:meth:`~Result.get` on each individual :py:meth:`Result`
        instance in the group and returns a list of return values. Any keyword
        arguments are passed along.

    .. py:method:: as_completed(backoff=1.15, max_delay=1.0)

        :param float backoff: factor to increase delay between polls.
        :param float max_delay: maximum seconds between polls.
        :returns: a generator that yields individual result values as they
            become available.

        Iterate over results in the order they become ready, rather than the
        order they were enqueued. This is useful when you want to begin
        processing results as soon as possible without waiting for all tasks
        to finish.

        .. code-block:: python

            result_group = huey.enqueue(group([
                fetch.s(url) for url in urls]))

            for value in result_group.as_completed():
                process(value)

        The generator polls each result handle in a round-robin fashion with
        exponential backoff, yielding values as they appear.

    .. py:method:: __getitem__(idx)

        Resolves the result at the given index, blocking until it is ready.

    .. py:method:: __iter__()

        Iterate over the individual :py:class:`Result` instances in the group.

    .. py:method:: __len__()

        Return the number of results in the group.

Serializer
----------

.. py:class:: Serializer(compression=False, compression_level=6, use_zlib=False)

    :param bool compression: use gzip compression
    :param int compression_level: 0 for least, 9 for most.
    :param bool use_zlib: use zlib for compression instead of gzip.

    The Serializer class implements a simple interface that can be extended to
    provide your own serialization format. The default implementation uses
    ``pickle``.

    To override, the following methods should be implemented. Compression is
    handled transparently elsewhere in the API.

    .. py:method:: _serialize(data)

        :param data: arbitrary Python object to serialize.
        :rtype bytes:

    .. py:method:: _deserialize(data)

        :param bytes data: serialized data.
        :returns: the deserialized object.


.. py:class:: SignedSerializer(secret, salt='huey', **kwargs)

    :param str secret: secret key used to generate HMAC signatures.
    :param str salt: salt combined with the secret (default ``'huey'``).
    :param kwargs: additional keyword arguments passed to the base
        :py:class:`Serializer` (e.g. ``compression``, ``use_zlib``).

    A subclass of :py:class:`Serializer` that adds an HMAC-SHA1 signature to
    every serialized message. When deserializing, the signature is verified and
    a ``ValueError`` is raised if the message has been tampered with.

    This is useful when the storage backend (e.g. Redis) is shared or
    network-exposed and you want to prevent malicious injection of crafted
    pickle payloads.

    .. code-block:: python

        from huey import RedisHuey
        from huey.serializer import SignedSerializer

        huey = RedisHuey(
            'my-app',
            serializer=SignedSerializer(secret='my-secret-key'))

    .. note::
        The signed serializer detects tampering but does **not** encrypt the
        data. Task arguments remain visible in the storage backend.

    Both the application and the consumer must use the same ``secret`` and
    ``salt``.

.. _exceptions:

Exceptions
----------

.. py:class:: HueyException

    General exception class.

.. py:class:: ConfigurationError

    Raised when Huey encounters a configuration problem.

.. py:class:: TaskLockedException

    Raised by the consumer when a task lock cannot be acquired.

.. py:class:: ResultTimeout

    Raised when attempting to block on a call to :py:meth:`Result.get` (for
    instance) and the timeout is exceeded without the result being ready.

.. py:class:: TaskTimeout

    Raised when a task exceeds its specified execution time.

.. py:class:: RateLimitExceeded(key, delay, retry=True)

    Raised when a rate-limit has been exceeded.

.. py:class:: CancelExecution(retry=None)

    Cancel the execution of a task. Can be raised either within a
    :py:meth:`~Huey.pre_execute` hook, or within a
    :py:meth:`~Huey.task`-decorated function.

    When raised from within a :py:meth:`~Huey.pre_execute` hook, this exception
    signals to the consumer that the task shall be cancelled and not run.

    When raised in the body of a :py:meth:`~Huey.task`-decorated function, the
    ``retry`` parameter controls whether the task is retried:

    * ``retry=None`` (default): the task's normal retry policy applies. If the
      task has retries remaining, they are decremented and the task is
      re-enqueued. If no retries remain, the task is not retried.
    * ``retry=True``: the task will be retried regardless of whether it was
      declared with ``retries``. If the task has no retries, Huey sets the
      retry count to 1 so at least one retry occurs.
    * ``retry=False``: the task will **not** be retried, even if it has
      retries remaining.

.. py:class:: RetryTask(msg=None, eta=None, delay=None)

    Raised by user code from within a :py:meth:`~Huey.task` function to force a
    retry. When this exception is raised, the task will be retried irrespective
    of whether it is configured with automatic retries.

    If ``delay`` or ``eta`` is specified, then any ``retry_delay`` set on the
    task will be overridden and the value specified will be used to determine
    when the task will be retried next.

    .. code-block:: python

        @huey.task()
        def fetch_api_data(url):
            try:
                fh = urlopen(url)
            except HTTPError:
                # Try again in 60 seconds for an HTTP error (500, etc).
                raise RetryTask(delay=60)
            ...

.. py:class:: TaskException

    General exception raised by :py:class:`Result` handles when reading the
    result of a task that failed due to an error.

Storage
-------

Huey comes with several built-in storage implementations:

.. py:class:: RedisStorage(name='huey', blocking=True, read_timeout=1, connection_pool=None, url=None, client_name=None, notify_result=False, notify_result_ttl=86400, **connection_params)

    :param bool blocking: Use blocking-pop when reading from the queue (as
        opposed to polling). Default is true.
    :param read_timeout: Timeout to use when performing a blocking pop, default
        is 1 second.
    :param connection_pool: a redis-py ``ConnectionPool`` instance.
    :param url: url for Redis connection.
    :param client_name: name used to identify Redis clients used by Huey.
    :param bool notify_result: use a blocking-pop on a result-ready key to
        enable low-latency result reading.
    :param int notify_result_ttl: TTL for result-ready key to automatically
        expire un-awaited results.

    Additional keyword arguments will be passed directly to the Redis client
    constructor. See the `redis-py documentation <https://redis-py.readthedocs.io/en/latest/>`_
    for the complete list of arguments supported by the Redis client.


.. py:class:: RedisExpireStorage(name='huey', expire_time=86400, blocking=True, read_timeout=1, connection_pool=None, url=None, client_name=None, notify_result=False, notify_result_ttl=86400, **connection_params)

    :param int expire_time: TTL for results of individual tasks.

    Subclass of :py:class:`RedisStorage` that implements the result store APIs
    using normal Redis keys with a TTL, so that unread results will
    automatically be cleaned-up. :py:class:`RedisStorage` uses a *HASH* for the
    result store, which has the benefit of keeping the Redis keyspace orderly,
    but which comes with the downside that unread task results can build up
    over time. This storage implementation trades keyspace sprawl for automatic
    clean-up.


.. py:class:: PriorityRedisStorage(name='huey', blocking=True, read_timeout=1, connection_pool=None, url=None, client_name=None, notify_result=False, notify_result_ttl=86400, **connection_params)

    :param bool blocking: Use blocking-zpopmin when reading from the queue (as
        opposed to polling). Default is true.
    :param read_timeout: Timeout to use when performing a blocking pop, default
        is 1 second.
    :param connection_pool: a redis-py ``ConnectionPool`` instance.
    :param url: url for Redis connection.
    :param client_name: name used to identify Redis clients used by Huey.
    :param bool notify_result: use a blocking-pop on a result-ready key to
        enable low-latency result reading.
    :param int notify_result_ttl: TTL for result-ready key to automatically
        expire un-awaited results.

    Redis storage that uses a different data-structure for the task queue in
    order to support task priorities.

    Additional keyword arguments will be passed directly to the Redis client
    constructor. See the `redis-py documentation <https://redis-py.readthedocs.io/en/latest/>`_
    for the complete list of arguments supported by the Redis client.

    .. warning:: This storage engine requires Redis 5.0 or newer.


.. py:class:: PriorityRedisExpireStorage(name='huey', expire_time=86400, ...)

    :param int expire_time: TTL for results of individual tasks.

    Combination of :py:class:`PriorityRedisStorage`, which supports task
    priorities, and :py:class:`RedisExpireStorage`, which stores task results
    as top-level Redis keys in order set a TTL so that unread results are
    automatically cleaned-up.


.. py:class:: SqliteStorage(filename='huey.db', name='huey', cache_mb=8, fsync=False, timeout=5, strict_fifo=False, **kwargs)

    :param str filename: sqlite database filename.
    :param int cache_mb: sqlite page-cache size in megabytes.
    :param bool fsync: if enabled, all writes to the Sqlite database will be
        synchonized. This provides greater safety from database corruption in
        the event of sudden power-loss.
    :param str journal_mode: sqlite journaling mode to use. Defaults to using
        write-ahead logging, which enables readers to coexist with a single
        writer.
    :param int timeout: busy timeout (in seconds), amount of time to wait to
        acquire the write lock when another thread / connection holds it.
    :param bool strict_fifo: ensure that the task queue behaves as a strict
        FIFO. By default, Sqlite may reuse rowids for deleted tasks, which can
        cause tasks to be run in a different order than the order in which they
        were enqueued.
    :param kwargs: Additional keyword arguments passed to the ``sqlite3``
        connection constructor.


.. py:class:: FileStorage(name, path, levels=2, use_thread_lock=False)

    :param str name: (unused by the file storage API)
    :param str path: directory path used to store task results. Will be created
        if it does not exist.
    :param int levels: number of levels in cache-file directory structure to
        ensure a given directory does not contain an unmanageable number of
        files.
    :param bool use_thread_lock: use the standard lib ``threading.Lock``
        instead of a lockfile. Note: this should only be enabled when using the
        greenlet or thread consumer worker models.

    The :py:class:`FileStorage` implements a simple file-system storage layer.
    This storage class should not be used in high-throughput, highly-concurrent
    environments, as it utilizes exclusive locks around all file-system
    operations. This is done to prevent race-conditions when reading from the
    file-system.


.. py:class:: MemoryStorage()

    In-memory storage engine for use when testing or developing. Designed for
    use with :ref:`immediate mode <immediate>`.


.. py:class:: BlackHoleStorage()

    Storage class that discards all data written to it, and thus always appears
    to be empty. Intended for testing only.


.. autoclass:: huey.storage.BaseStorage
   :members:

