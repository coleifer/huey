.. _api:

Huey's API
==========

Most end-users will interact with the API using the two decorators:

* :py:meth:`Huey.task`
* :py:meth:`Huey.periodic_task`

The API documentation will follow the structure of the huey ``api.py`` module.

Huey object
-----------

.. py:class:: Huey(name='huey', results=True, store_none=False, utc=True, immediate=False, serializer=None, compression=False, immediate_use_memory=True, storage_kwargs)

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

    .. py:method:: task(retries=0, retry_delay=0, context=False, name=None, **kwargs)

        :param int retries: number of times to retry the function if an
            unhandled exception occurs when it is executed.
        :param int retry_delay: number of seconds to wait in-between retries.
        :param bool context: when the task is executed, include the
            :py:class:`Task` instance as a parameter.
        :param str name: name for this task. If not provided, Huey will default
            to using the module name plus function name.
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

        .. note::
            Huey can be configured to execute the function immediately by
            instantiating Huey with ``immediate=True`` -- this is useful for
            running in debug mode or when you do not wish to run the consumer.

            For more information, see the :ref:`immediate mode <immediate>`
            section of the guide.

        The ``task()`` decorator returns a :py:class:`TaskWrapper`, which
        implements special methods for enqueueing the decorated function. These
        methods are used to :py:meth:`~TaskWrapper.schedule` the task to run in
        the future, chain tasks to form a pipeline, and more.

        Example:

        .. code-block:: python
            from huey import RedisHuey

            huey = RedisHuey()

            @huey.task()
            def add(a, b):
                return a + b

        Whenever the ``add()`` function is called, the actual execution will
        occur when the consumer dequeues the message.

        .. code-block:: pycon

            >>> res = add(1, 2)
            >>> res
            <Result: task 6b6f36fc-da0d-4069-b46c-c0d4ccff1df6>
            >>> res()
            3

        To further illustrate this point:

        .. code-block:: python
            @huey.task()
            def slow(n):
                time.sleep(n)
                return n

        Calling the ``slow()`` task will return immediately. We can, however,
        block until the task finishes by waiting for the result:

        .. code-block:: pycon

            >>> res = slow(10)  # Returns immediately.
            >>> res(blocking=True)  # Block until task finishes, ~10s.
            10

        .. note::
            The return value of any calls to the decorated function depends on
            whether the :py:class:`Huey` instance is configured to store the
            results of tasks (``results=True`` is the default). When the result
            store is disabled, calling a task-decorated function will return
            ``None`` instead of a result handle.

        In some cases, it may be useful to receive the :py:class:`Task`
        instance itself as an argument.

        .. code-block:: python
            @huey.task(context=True)  # Include task as an argument.
            def print_a_task_id(message, task=None):
                print('%s: %s' % (message, task.id))


            print_a_task_id('hello')
            print_a_task_id('goodbye')

        This would cause the consumer would print something like::

            hello: e724a743-e63e-4400-ac07-78a2fa242b41
            goodbye: 606f36fc-da0d-4069-b46c-c0d4ccff1df6

        For more information, see :py:class:`TaskWrapper`, :py:class:`Task`,
        and :py:class:`Result`.

    .. py:method:: periodic_task(validate_datetime, retries=0, retry_delay=0, context=False, name=None, **kwargs)

        :param function validate_datetime: function which accepts a
            ``datetime`` instance and returns whether the task should be
            executed at the given time.
        :param int retries: number of times to retry the function if an
            unhandled exception occurs when it is executed.
        :param int retry_delay: number of seconds to wait in-between retries.
        :param bool context: when the task is executed, include the
            :py:class:`Task` instance as a parameter.
        :param str name: name for this task. If not provided, Huey will default
            to using the module name plus function name.
        :param kwargs: arbitrary key/value arguments that are passed to the
            :py:class:`TaskWrapper` instance.
        :returns: a :py:class:`TaskWrapper` that wraps the decorated function
            and exposes a number of APIs for enqueueing the task.

        The ``periodic_task()`` decorator marks a function for automatic
        execution by the consumer *at a specific interval*, like ``cron``.

        The ``validate_datetime`` parameter is a function which accepts a
        ``datetime`` object and returns a boolean value whether or not the
        decorated function should execute at that time or not. The consumer
        will send a datetime to the function once per minute, giving it the
        same granularity as the ``cron``.

        For simplicity, there is a special function :py:func:`crontab`, which
        can be used to quickly specify intervals at which a function should
        execute. It is described below.

        Here is an example of how you might use the ``periodic_task`` decorator
        and the :py:func:`crontab`` helper. The following task will be executed
        every three hours, on the hour:

        .. code-block:: python

            from huey import crontab
            from huey import RedisHuey

            huey = RedisHuey()

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

    .. py:method:: context_task(obj, retries=0, retry_delay=0, context=False, name=None, **kwargs)

        :param obj: object that implements the context-manager APIs.
        :param bool as_argument: pass the context-manager object into the
            decorated task as the first argument.
        :param int retries: number of times to retry the function if an
            unhandled exception occurs when it is executed.
        :param int retry_delay: number of seconds to wait in-between retries.
        :param bool context: when the task is executed, include the
            :py:class:`Task` instance as a parameter.
        :param str name: name for this task. If not provided, Huey will default
            to using the module name plus function name.
        :param kwargs: arbitrary key/value arguments that are passed to the
            :py:class:`TaskWrapper` instance.
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
                # Do something in response to the "ERROR" or "LOCEKD" signals.
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

    .. py:method:: enqueue(task)

        :param Task task: task instance to enqueue.
        :returns: :py:class:`Result` handle for the given task.

        Enqueue the given task. When the result store is enabled (default), the
        return value will be a :py:class:`Result` handle which provides access
        to the result of the task execution (as well as other things).

        If the task specifies another task to run on completion (see
        :py:meth:`Task.then`), the return value will be a
        :py:class:`ResultGroup`, which encapsulates a list of individual
        :py:class:`Result` instances for the given pipeline.

        .. note::
            Unless you are executing a pipeline of tasks, it should not
            be necessary to use the :py:meth:`~Huey.enqueue` method directly.
            Calling (or scheduling) a ``task``-decorated function will
            automatically enqueue a task for execution.

            When you create a task pipeline, however, it is necessary to
            enqueue the pipeline once it has been set up.

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

        .. seealso::
            For task instances, use :py:meth:`Result.is_revoked`.

            For task functions, use :py:meth:`TaskWrapper.is_revoked`.

    .. py:method:: result(task_id, blocking=False, timeout=None, backoff=1.15, max_delay=1.0, revoke_on_timeout=False, preserve=False)

        Attempt to retrieve the return value of a task. By default, :py:meth:`~Huey.result`
        will simply check for the value, returning ``None`` if it is not ready
        yet. If you want to wait for a value, specify ``blocking=True``. This
        will loop, backing off up to the provided ``max_delay``, until the
        value is ready or the ``timeout`` is reached. If the ``timeout`` is
        reached before the result is ready, a :py:class:`HueyException` will be
        raised.

        .. note:: If the task failed with an exception, then a
            :py:class:`TaskException` that wraps the original exception will be
            raised.

        .. warning:: By default the result store will delete a task's return
            value after the value has been successfully read (by a successful
            call to the :py:meth:`~Huey.result` or :py:meth:`Result.get`
            methods). If you need to use the task result multiple times, you
            must specify ``preserve=True`` when calling these methods.

        :param task_id: the task's unique identifier.
        :param bool blocking: whether to block while waiting for task result
        :param timeout: number of seconds to block (if ``blocking=True``)
        :param backoff: amount to backoff delay each iteration of loop
        :param max_delay: maximum amount of time to wait between iterations when
            attempting to fetch result.
        :param bool revoke_on_timeout: if a timeout occurs, revoke the task,
            thereby preventing it from running if it is has not started yet.
        :param bool preserve: see the above warning. When set to ``True``, this
            parameter ensures that the task result should be preserved after
            having been successfully retrieved.

    .. py:method:: lock_task(lock_name)

        Utilize the Storage key/value APIs to implement simple locking.

        This lock is designed to be used to prevent multiple invocations of a
        task from running concurrently. Can be used as either a context-manager
        or as a task decorator. If using as a decorator, place it directly
        above the function declaration.

        If a second invocation occurs and the lock cannot be acquired, then a
        special exception is raised, which is handled by the consumer. The task
        will not be executed and an ``EVENT_LOCKED`` will be emitted. If the
        task is configured to be retried, then it will be retried normally, but
        the failure to acquire the lock is not considered an error.

        Examples:

        .. code-block:: python

            @huey.periodic_task(crontab(minute='*/5'))
            @huey.lock_task('reports-lock')
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

        :param str lock_name: Name to use for the lock.
        :return: Decorator or context-manager.

    .. py:method:: put(key, value)

        :param key: key for data
        :param value: arbitrary data to store in result store.

        Store a value in the result-store under the given key.

    .. py:method:: get(key, peek=False)

        :param key: key to read
        :param bool peek: non-destructive read

        Read a value from the result-store at the given key. By default reads
        are destructive, but to preserve the value you can specify
        ``peek=True``.

    .. py:method:: pending(limit=None)

        Return all unexecuted tasks currently in the queue.

    .. py:method:: scheduled(limit=None)

        Return all unexecuted tasks currently in the schedule.

    .. py:method:: all_results()

        Return a mapping of task-id to pickled result data for all executed tasks whose return values have not been automatically removed.


.. py:class:: TaskWrapper(huey, func, retries=0, retry_delay=0, retries_as_argument=False, include_task=False, name=None, task_base=None, **task_settings)

    :param Huey huey: A huey instance.
    :param func: User function.
    :param int retries: Upon failure, number of times to retry the task.
    :param int retry_delay: Number of seconds to wait before retrying after a
        failure/exception.
    :param bool retries_as_argument: Pass the number of remaining retries as an
        argument to the user function.
    :param bool include_task: Pass the task object itself as an argument to the
        user function.
    :param str name: Name for task (will be determined based on task module and
        function name if not provided).
    :param task_base: Base-class for task, defaults to :py:class:`QueueTask`.
    :param task_settings: Arbitrary settings to pass to the task class
        constructor.

    Wrapper around a user-defined function that converts function calls into
    tasks executed by the consumer. The wrapper, which decorates the function,
    replaces the function in the scope with a :py:class:`TaskWrapper` instance.

    The wrapper class, when called, will enqueue the requested function call
    for execution by the consumer.

    .. note::
        You should not need to create :py:class:`TaskWrapper` instances
        directly. Instead, use the :py:meth:`Huey.task` and
        :py:meth:`Huey.periodic_task` decorators.

    The wrapper class also has several helper methods for managing and
    enqueueing tasks, which are described below.

    .. py:method:: schedule(args=None, kwargs=None, eta=None, delay=None, convert_utc=True)

        Use the ``schedule`` method to schedule the execution of the queue task
        for a given time in the future:

        .. code-block:: python

            import datetime

            # get a datetime object representing one hour in the future
            in_an_hour = datetime.datetime.now() + datetime.timedelta(seconds=3600)

            # schedule "count_some_beans" to run in an hour
            count_some_beans.schedule(args=(100000,), eta=in_an_hour)

            # another way of doing the same thing...
            count_some_beans.schedule(args=(100000,), delay=(60 * 60))

        :param args: arguments to call the decorated function with
        :param kwargs: keyword arguments to call the decorated function with
        :param datetime eta: the time at which the function should be
            executed. See note below on how to correctly specify the
            ``eta`` whether the consumer is running in UTC- or
            localtime-mode.
        :param int delay: number of seconds to wait before executing function
        :param convert_utc: whether the ``eta`` or ``delay`` should be converted from local time to UTC.
            Defaults to ``True``. See note below.
        :rtype: like calls to the decorated function, will return an :py:class:`TaskResultWrapper`
                object if a result store is configured, otherwise returns ``None``

        .. note::
            It can easily become confusing when/how to use the ``convert_utc``
            parameter when scheduling tasks. Similarly, if you are using naive
            datetimes, whether the ETA should be based around
            ``datetime.utcnow()`` or ``datetime.now()``.

            If you are running the consumer in UTC-mode (the default):

            * When specifying a ``delay``, ``convert_utc=True``.
            * When specifying an ``eta`` with respect to
              ``datetime.now()``, ``convert_utc=True``.
            * When specifying an ``eta`` with respect to
              ``datetime.utcnow()``, ``convert_utc=False``.

            If you are running the consumer in localtime-mode (``-o``):

            * When specifying a ``delay``, ``convert_utc=False``.
            * When specifying an ``eta``, it should always be with respect
              to ``datetime.now()`` with ``convert_utc=False``.

            In other words, for consumers running in UTC-mode, the only time
            ``convert_utc=False`` is when you are passing an ``eta`` that is
            already a naive datetime with respect to ``utcnow()``.

            Similarly for localtime-mode consumers, ``convert_utc`` should
            always be ``False`` and when specifying an ``eta`` it should be
            with respect to ``datetime.now()``.

    .. py:method:: call_local()

        Call the ``@task``-decorated function without enqueueing the call. Or,
        in other words, ``call_local()`` provides access to the underlying user
        function.

        .. code-block:: pycon

            >>> count_some_beans.call_local(1337)
            'Counted 1337 beans'

    .. py:method:: revoke(revoke_until=None, revoke_once=False)

        Prevent any instance of the given task from executing.  When no
        parameters are provided the function will not execute again until
        explicitly restored.

        This function can be called multiple times, but each call will
        supercede any limitations placed on the previous revocation.

        :param datetime revoke_until: Prevent the execution of the task until the
            given datetime.  If ``None`` it will prevent execution indefinitely.
        :param bool revoke_once: If ``True`` will only prevent execution of the next
            invocation of the task.

        .. code-block:: python

            # skip the next execution
            count_some_beans.revoke(revoke_once=True)

            # prevent any invocation from executing.
            count_some_beans.revoke()

            # prevent any invocation for 24 hours.
            count_some_beans.revoke(datetime.datetime.now() + datetime.timedelta(days=1))

    .. py:method:: is_revoked(dt=None)

        Check whether the given task is revoked.  If ``dt`` is specified, it
        will check if the task is revoked with respect to the given datetime.

        :param datetime dt: If provided, checks whether task is revoked at the
            given datetime

    .. py:method:: restore()

        Clears any revoked status and allows the task to run normally.

    .. py:method:: s(*args, **kwargs)

        Create a task instance representing the invocation of the user function
        with the given arguments and keyword-arguments. The resulting task
        instance is **not** enqueued automatically.

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

        :param args: Arguments for user-defined function.
        :param kwargs: Keyword arguments for user-defined function.
        :returns: a :py:class:`QueueTask` instance representing the execution
            of the user-defined function with the given arguments.

        Typically, one will use the :py:meth:`TaskWrapper.s` helper when
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
            print([result.get(blocking=True) for result in results])

            # [3, 6, 10, 15]

    .. py:attribute:: task_class

        Store a reference to the task class for the decorated function.

        .. code-block:: pycon

            >>> count_some_beans.task_class
            tasks.queuecmd_count_beans


.. py:class:: QueueTask(data=None, task_id=None, execute_time=None, retries=None, retry_delay=None, on_complete=None)

    The ``QueueTask`` class represents the execution of a function. Instances
    of the class are serialized and enqueued for execution by the consumer,
    which deserializes them and executes the function.

    .. note::
        You should not need to create instances of :py:class:`QueueTask`
        directly, but instead use either the :py:meth:`Huey.task` decorator or
        the :py:meth:`TaskWrapper.s` method.

    :param data: Data specific to this execution of the task. For
        ``task()``-decorated functions, this will be a tuple of the
        ``(args, kwargs)`` the function was invoked with.
    :param str task_id: The task's ID, defaults to a UUID if not provided.
    :param datetime execute_time: Time at which task should be executed.
    :param int retries: Number of times to retry task upon failure/exception.
    :param int retry_delay: Number of seconds to wait before retrying a failed
        task.
    :param QueueTask on_complete: Task to execute upon completion of this task.

    Here's a refresher on how tasks work:

    .. code-block:: python

        @huey.task()
        def add(a, b):
            return a + b

        ret = add(1, 2)
        print(ret.get(blocking=True))  # "3".

        # The above two lines are equivalent to:
        task_instance = add.s(1, 2)  # Create a QueueTask instance.
        ret = huey.enqueue(task_instance)  # Enqueue the queue task.
        print(ret.get(blocking=True))  # "3".

    .. py:method:: then(task, *args, **kwargs)

        :param TaskWrapper task: A ``task()``-decorated function.
        :param args: Arguments to pass to the task.
        :param kwargs: Keyword arguments to pass to the task.
        :returns: The parent task.

        The :py:meth:`~QueueTask.then` method is used to create task pipelines.
        A pipeline is a lot like a unix pipe, such that the return value from
        the parent task is then passed (along with any parameters specified by
        ``args`` and ``kwargs``) to the child task.

        Here's an example of chaining some addition operations:

        .. code-block:: python

            add_task = add.s(1, 2)  # Represent task invocation.
            pipeline = (add_task
                        .then(add, 3)  # Call add() with previous result and 3.
                        .then(add, 4)  # etc...
                        .then(add, 5))

            results = huey.enqueue(pipeline)

            # Print results of above pipeline.
            print([result.get(blocking=True) for result in results])

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
            results = huey.enqueue(pipe)

            print([result.get(blocking=True) for result in results])
            # [(2, 1), (3, 2), (5, 3)]


.. py:function:: crontab(month='*', day='*', day_of_week='*', hour='*', minute='*')

    Convert a "crontab"-style set of parameters into a test function that will
    return ``True`` when a given ``datetime`` matches the parameters set forth in
    the crontab.

    Day-of-week uses 0=Sunday and 6=Saturday.

    Acceptable inputs:

    - "*" = every distinct value
    - "\*/n" = run every "n" times, i.e. hours='\*/4' == 0, 4, 8, 12, 16, 20
    - "m-n" = run every time m..n
    - "m,n" = run on m and n

    :rtype: a test function that takes a ``datetime`` and returns a boolean

    .. note::
        It is currently not possible to run periodic tasks with an interval
        less than once per minute. If you need to run tasks more frequently,
        you can create a periodic task that runs once per minute, and from that
        task, schedule any number of sub-tasks to run after the desired delays.

TaskResultWrapper
-----------------

.. py:class:: TaskResultWrapper(huey, task)

    Although you will probably never instantiate an ``TaskResultWrapper`` object yourself,
    they are returned by any calls to :py:meth:`~Huey.task` decorated functions
    (provided that *huey* is configured with a result store).  The ``TaskResultWrapper``
    talks to the result store and is responsible for fetching results from tasks.

    Once the consumer finishes executing a task, the return value is placed in the
    result store, allowing the producer to retrieve it.

    .. note:: By default, the data is removed from the result store after
        being read, but this behavior can be disabled.

    Getting results from tasks is very simple:

    .. code-block:: python

        >>> from main import count_some_beans
        >>> res = count_some_beans(100)
        >>> res  # what is "res" ?
        <huey.queue.TaskResultWrapper object at 0xb7471a4c>

        >>> res()  # Fetch the result of this task.
        'Counted 100 beans'

    What happens when data isn't available yet?  Let's assume the next call takes
    about a minute to calculate::

        >>> res = count_some_beans(10000000) # let's pretend this is slow
        >>> res.get()  # Data is not ready, so None is returned.

        >>> res() is None  # We can omit ".get", it works the same way.
        True

        >>> res(blocking=True, timeout=5)  # Block for up to 5 seconds
        Traceback (most recent call last):
          File "<stdin>", line 1, in <module>
          File "/home/charles/tmp/huey/src/huey/huey/queue.py", line 46, in get
            raise DataStoreTimeout
        huey.exceptions.DataStoreTimeout

        >>> res(blocking=True)  # No timeout, will block until it gets data.
        'Counted 10000000 beans'

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

    .. py:attr:: task_id

        Returns the ID of the corresponding task.

    .. py:method:: get(blocking=False, timeout=None, backoff=1.15, max_delay=1.0, revoke_on_timeout=False, preserve=False)

        Attempt to retrieve the return value of a task.  By default, :py:meth:`~TaskResultWrapper.get`
        will simply check for the value, returning ``None`` if it is not ready yet.
        If you want to wait for a value, you can specify ``blocking=True``.
        This will loop, backing off up to the provided ``max_delay``, until the
        value is ready or the ``timeout`` is reached. If the ``timeout``
        is reached before the result is ready, a :py:class:`DataStoreTimeout`
        exception will be raised.

        .. warning:: By default the result store will delete a task's return
            value after the value has been successfully read (by a successful
            call to the :py:meth:`~Huey.result` or :py:meth:`TaskResultWrapper.get`
            methods). If you need to use the task result multiple times, you
            must specify ``preserve=True`` when calling these methods.

        .. note:: Instead of calling ``.get()``, you can simply call the
            :py:class:`TaskResultWrapper` object directly. Both methods accept the
            same parameters.

        :param bool blocking: whether to block while waiting for task result
        :param timeout: number of seconds to block (if ``blocking=True``)
        :param backoff: amount to backoff delay each iteration of loop
        :param max_delay: maximum amount of time to wait between iterations when
            attempting to fetch result.
        :param bool revoke_on_timeout: if a timeout occurs, revoke the task,
            thereby preventing it from running if it is has not started yet.
        :param bool preserve: see the above warning. When set to ``True``, this
            parameter ensures that the task result should be preserved after
            having been successfully retrieved.

    .. py:method:: __call__(**kwargs)

        Identical to the :py:meth:`~TaskResultWrapper.get` method, provided as a
        shortcut.

    .. py:method:: revoke()

        Revoke the given task.  Unless it is in the process of executing, it will
        be revoked and the task will not run.

        .. code-block:: python

            in_an_hour = datetime.datetime.now() + datetime.timedelta(seconds=3600)

            # run this command in an hour
            res = count_some_beans.schedule(args=(100000,), eta=in_an_hour)

            # oh shoot, I changed my mind, do not run it after all
            res.revoke()

    .. py:method:: restore()

        Restore the given task instance. Unless the task instance has already
        been dequeued and discarded, it will be restored and run as scheduled.

        .. warning::
            If the task class itself has been revoked, then this method has no
            effect.

    .. py:method:: is_revoked()

        Return a boolean value indicating whether this particular task instance
        **or** the task class itself has been revoked.

        See also: :py:meth:`Huey.is_revoked`.

    .. py:method:: reschedule(eta=None, delay=None, convert+utc=True)

        Reschedule the given task. The original task instance will be revoked,
        but **no checks are made** to verify that it hasn't already been
        executed.

        If neither an ``eta`` nor a ``delay`` is specified, the task will be
        run as soon as it is received by a worker.

        :param datetime eta: the time at which the function should be
            executed. See note below on how to correctly specify the
            ``eta`` whether the consumer is running in UTC- or
        :param int delay: number of seconds to wait before executing function
        :param convert_utc: whether the ``eta`` or ``delay`` should be
            converted from local time to UTC. Defaults to ``True``. See the
            note in the ``schedule()`` method of :py:meth:`Huey.task` for more
            information.
        :rtype: :py:class:`TaskResultWrapper` object for the new task.

    .. py:method:: reset()

        Reset the cached result and allow re-fetching a new result for the
        given task (i.e. after a task error and subsequent retry).

Storage
-------

Huey

.. py:class:: BaseStorage(name='huey', **storage_kwargs)

    .. py:meth:: enqueue(data)

    .. py:meth:: dequeue(data)

    .. py:meth:: unqueue(data)

    .. py:meth:: queue_size()

    .. py:meth:: enqueued_items(limit=None)

    .. py:meth:: flush_queue()

    .. py:meth:: add_to_schedule(data, timestamp)

    .. py:meth:: read_schedule(timestamp)

    .. py:meth:: schedule_size()

    .. py:meth:: scheduled_items(limit=None)

    .. py:meth:: flush_schedule()

    .. py:meth:: put_data(key, value)

    .. py:meth:: peek_data(key)

    .. py:meth:: pop_data(key)

    .. py:meth:: has_data_for_key(key)

    .. py:meth:: result_store_size()

    .. py:meth:: result_items()

    .. py:meth:: flush_results()

    .. py:meth:: put_error(metadata)

    .. py:meth:: get_errors(limit=None, offset=0)

    .. py:meth:: flush_errors()

    .. py:meth:: emit(message)

    .. py:meth:: __iter__()
