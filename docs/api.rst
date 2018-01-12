.. _api:

Huey's API
==========

Most end-users will interact with the API using the two decorators:

* :py:meth:`Huey.task`
* :py:meth:`Huey.periodic_task`

The API documentation will follow the structure of the huey API, starting with
the highest-level interfaces (the decorators) and eventually discussing the
lowest-level interfaces, the :py:class:`BaseQueue` and :py:class:`BaseDataStore` objects.

.. _function-decorators:

Function decorators and helpers
-------------------------------

.. py:class:: Huey(name[, result_store=True[, events=True[, store_none=False[, always_eager=False[, store_errors=True[, blocking=False[, **storage_kwargs]]]]]]])

    Huey executes tasks by exposing function decorators that cause the function
    call to be enqueued for execution by the consumer.

    Typically your application will only need one Huey instance, but you can
    have as many as you like -- the only caveat is that one consumer process
    must be executed for each Huey instance.

    :param name: the name of the huey instance or application.
    :param bool result_store: whether the results of tasks should be stored.
    :param bool events: whether events should be emitted by the consumer.
    :param bool store_none: Flag to indicate whether tasks that return ``None``
        should store their results in the result store.
    :param bool always_eager: Useful for testing, this will execute all tasks
        immediately, without enqueueing them.
    :param bool store_errors: whether task errors should be stored.
    :param bool blocking: whether the queue will block (if False, then the queue will poll).
    :param storage_kwargs: arbitrary kwargs to pass to the storage implementation.

    Example usage:

    .. code-block:: python

        from huey import RedisHuey, crontab

        huey = RedisHuey('my-app')

        @huey.task()
        def slow_function(some_arg):
            # ... do something ...
            return some_arg

        @huey.periodic_task(crontab(minute='0', hour='3'))
        def backup():
            # do a backup every day at 3am
            return

    .. py:method:: task([retries=0[, retry_delay=0[, retries_as_argument=False[, include_task=False]]]])

        Function decorator that marks the decorated function for processing by the
        consumer. Calls to the decorated function will do the following:

        1. Serialize the function call into a message suitable for storing in the queue.
        2. Enqueue the message for execution by the consumer.
        3. If a ``result_store`` has been configured, return a :py:class:`TaskResultWrapper`
           instance which can retrieve the result of the function, or ``None`` if not
           using a result store.

        .. note::
            Huey can be configured to execute the function immediately by
            instantiating it with ``always_eager = True`` -- this is useful for
            running in debug mode or when you do not wish to run the consumer.

        Here is how you might use the ``task`` decorator:

        .. code-block:: python

            # assume that we've created a huey object
            from huey import RedisHuey

            huey = RedisHuey()

            @huey.task()
            def count_some_beans(num):
                # do some counting!
                return 'Counted %s beans' % num

        Now, whenever you call this function in your application, the actual
        processing will occur when the consumer dequeues the message and your
        application will continue along on its way.

        With a result store:

        .. code-block:: pycon

            >>> res = count_some_beans(1000000)
            >>> res
            <huey.api.TaskResultWrapper object at 0xb7471a4c>
            >>> res()
            'Counted 1000000 beans'

        Without a result store:

        .. code-block:: pycon

            >>> res = count_some_beans(1000000)
            >>> res is None
            True

        :param int retries: number of times to retry the task if an exception occurs
        :param int retry_delay: number of seconds to wait between retries
        :param boolean retries_as_argument: whether the number of retries should
            be passed in to the decorated function as an argument.
        :param boolean include_task: whether the task instance itself should be
            passed in to the decorated function as the ``task`` argument.
        :returns: A callable :py:class:`TaskWrapper` instance.
        :rtype: TaskWrapper

        The return value of any calls to the decorated function depends on whether
        the :py:class:`Huey` instance is configured with a ``result_store``.  If a
        result store is configured, the decorated function will return
        an :py:class:`TaskResultWrapper` object which can fetch the result of the call from
        the result store -- otherwise it will simply return ``None``.

        The ``task`` decorator also does one other important thing -- it adds
        a special methods **onto** the decorated function, which makes it possible
        to *schedule* the execution for a certain time in the future, create
        task pipelines, etc. For more information, see:

        * :py:meth:`TaskWrapper.schedule`
        * :py:meth:`TaskWrapper.s`
        * :py:meth:`TaskWrapper.revoke`
        * :py:meth:`TaskWrapper.is_revoked`
        * :py:meth:`TaskWrapper.restore`

    .. py:method:: periodic_task(validate_datetime)

        Function decorator that marks the decorated function for processing by
        the consumer *at a specific interval*. The ``periodic_task`` decorator
        serves to **mark a function as needing to be executed periodically** by
        the consumer.

        .. note::
            By default, the consumer will schedule and enqueue periodic task
            functions.  To disable the enqueueing of periodic tasks, run the
            consumer with ``-n`` or ``--no-periodic``.

        The ``validate_datetime`` parameter is a function which accepts a datetime
        object and returns a boolean value whether or not the decorated function
        should execute at that time or not.  The consumer will send a datetime to
        the function every minute, giving it the same granularity as the linux
        crontab, which it was designed to mimic.

        For simplicity, there is a special function :py:func:`crontab`, which can
        be used to quickly specify intervals at which a function should execute.  It
        is described below.

        Here is an example of how you might use the ``periodic_task`` decorator
        and the ``crontab`` helper:

        .. code-block:: python

            from huey import crontab
            from huey import RedisHuey

            huey = RedisHuey()

            @huey.periodic_task(crontab(minute='*/5'))
            def every_five_minutes():
                # this function gets executed every 5 minutes by the consumer
                print("It's been five minutes")

        .. note::
            Because functions decorated with ``periodic_task`` are meant to be
            executed at intervals in isolation, they should not take any required
            parameters nor should they be expected to return a meaningful value.
            This is the same regardless of whether or not you are using a result store.

        :param validate_datetime: a callable which takes a ``datetime`` and returns
            a boolean whether the decorated function should execute at that time or not
        :returns: A callable :py:class:`TaskWrapper` instance.
        :rtype: :py:class:`PeriodicQueueTask`

        Like :py:meth:`~Huey.task`, the periodic task decorator adds helpers
        to the decorated function. These helpers allow you to "revoke" and "restore" the
        periodic task, effectively enabling you to pause it or prevent its execution.
        For more information, see :py:class:`TaskWrapper`.

    .. py:method:: enqueue(task)

        Enqueue the given task. When the result store is enabled (on by
        default), the return value will be a :py:class:`TaskResultWrapper`
        which provides access to the result (among other things).

        If the task specifies another task to run on completion (see
        :py:meth:`QueueTask.then`), then the return value will be a ``list`` of
        :py:class:`TaskResultWrapper` objects, one for each task in the
        pipeline.

        .. note::
            Unless you are executing a pipeline of tasks, it should not
            typically be necessary to use the :py:meth:`Huey.enqueue` method.
            Calling (or scheduling) a ``task``-decorated function will
            automatically enqueue a task for execution.

            When you create a task pipeline, however, it is necessary to
            enqueue the pipeline once it has been set up.

        :param QueueTask task: a :py:class:`QueueTask` instance.
        :returns: A :py:class:`TaskResultWrapper` object (if result store
            enabled).

    .. py:method:: register_pre_execute(name, fn)

        Register a pre-execute hook. The callback will be executed before the
        execution of all tasks. Execution of the task can be cancelled by
        raising a :py:class:`CancelExecution` exception. Uncaught exceptions
        will be logged but will not cause the task itself to be cancelled.

        The callback function should accept a single task instance, the return
        value is ignored.

        Hooks are executed in the order in which they are registered (which may
        be implicit if registered using the decorator).

        :param name: Name for the hook.
        :param fn: Callback function that accepts task to be executed.

    .. py:method:: unregister_pre_execute(name)

        Unregister the specified pre-execute hook.

    .. py:method:: pre_execute([name=None])

        Decorator for registering a pre-execute hook.

        Usage:

        .. code-block:: python

            @huey.pre_execute()
            def my_pre_execute_hook(task):
                do_something()

    .. py:method:: register_post_execute(name, fn)

        Register a post-execute hook. The callback will be executed after the
        execution of all tasks. Uncaught exceptions will be logged but will
        have no other effect on the overall operation of the consumer.

        The callback function should accept:

        * a task instance
        * the return value from the execution of the task (which may be None)
        * any exception that was raised during the execution of the task (which
          will be None for tasks that executed normally).

        The return value of the callback itself is ignored.

        Hooks are executed in the order in which they are registered (which may
        be implicit if registered using the decorator).

        :param name: Name for the hook.
        :param fn: Callback function that accepts task that was executed and
                   the tasks return value (or None).

    .. py:method:: unregister_post_execute(name)

        Unregister the specified post-execute hook.

    .. py:method:: post_execute([name=None])

        Decorator for registering a post-execute hook.

        Usage:

        .. code-block:: python

            @huey.post_execute()
            def my_post_execute_hook(task, task_value, exc):
                do_something()

    .. py:method:: revoke(task[, revoke_until=None[, revoke_once=False]])

        Prevent the given task **instance** from being executed by the consumer
        after it has been enqueued. To understand this method, you need to know
        a bit about how the consumer works. When you call a function decorated
        by the :py:meth:`Huey.task` method, calls to that function will enqueue
        a message to the consumer indicating which task to execute, what the
        parameters are, etc. If the task is not scheduled to execute in the
        future, and there is a free worker available, the task starts executing
        immediately. Otherwise if workers are busy, it will wait in line for
        the next free worker.

        When you revoke a task, when the worker picks up the revoked task to
        start executing it, it will instead just throw it away and get the next
        available task. So, revoking a task only has affect between the time
        you call the task and the time the worker actually starts executing the
        task.

        .. warning::
            This method only revokes a given **instance** of a task. Therefore,
            this method cannot be used with periodic tasks. To revoke **all**
            instances of a given task (including periodic tasks), see the
            :py:meth:`~Huey.revoke_all` method.

        This function can be called multiple times, but each call will
        supercede any previous revoke settings.

        :param datetime revoke_until: Prevent the execution of the task until the
            given datetime.  If ``None`` it will prevent execution indefinitely.
        :param bool revoke_once: If ``True`` will only prevent execution the
            next time it would normally execute.

    .. py:method:: restore(task)

        Takes a previously revoked task **instance** and restores it, allowing
        normal execution. If the revoked task was already consumed and
        discarded by a worker, then restoring will have no effect.

        .. note::
            If the task class itself has been revoked, restoring a given
            instance will not have any effect.

    .. py:method:: revoke_by_id(task_id[, revoke_until=None[, revoke_once=False]])

        Exactly the same as :py:meth:`~Huey.revoke`, except it accepts a task
        instance ID instead of the task instance itself.

    .. py:method:: restore_by_id(task_id)

        Exactly the same as :py:meth:`~Huey.restore`, except it accepts a task
        instance ID instead of the task instance itself.

    .. py:method:: revoke_all(task_class[, revoke_until=None[, revoke_once=False]])

        Prevent any instance of the given task from being executed by the
        consumer.

        .. warning::
            This method affects all instances of a given task.

        This function can be called multiple times, but each call will
        supercede any previous revoke settings.

        :param datetime revoke_until: Prevent execution of the task until the
            given datetime.  If ``None`` it will prevent execution indefinitely.
        :param bool revoke_once: If ``True`` will only prevent execution the
            next time it would normally execute.

    .. py:method:: restore_all(task_class)

        Takes a previously revoked task class and restores it, allowing
        normal execution. Restoring a revoked task class does not have any
        effect on individually revoked instances of the given task.

        .. note::
            Restoring a revoked task class does not have any effect on
            individually revoked instances of the given task.

    .. py:method:: is_revoked(task[, dt=None])

        Returns a boolean indicating whether the given task instance/class is
        revoked. If the ``dt`` parameter is specified, then the result will
        indicate whether the task is revoked at that particular datetime.

        .. note::
            If a task class is specified, the return value will indicate only
            whether all instances of that task are revoked.

            If a task instance/ID is specified, the return value will indicate
            whether the given instance **or** the task class itself has been
            revoked.

        :param task: Either a task class, task instance or task ID.
        :return: Boolean indicating whether the aforementioned task is revoked.

    .. py:method:: result(task_id[, blocking=False[, timeout=None[, backoff=1.15[, max_delay=1.0[, revoke_on_timeout=False[, preserve=False]]]]]])

        Attempt to retrieve the return value of a task.  By default, :py:meth:`~Huey.result`
        will simply check for the value, returning ``None`` if it is not ready yet.
        If you want to wait for a value, you can specify ``blocking=True``.
        This will loop, backing off up to the provided ``max_delay``, until the
        value is ready or the ``timeout`` is reached. If the ``timeout``
        is reached before the result is ready, a :py:class:`DataStoreTimeout`
        exception will be raised.

        .. note:: If the task failed with an exception, then a
            :py:class:`TaskException` that wraps the original exception will be
            raised.

        .. warning:: By default the result store will delete a task's return
            value after the value has been successfully read (by a successful
            call to the :py:meth:`~Huey.result` or :py:meth:`TaskResultWrapper.get`
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

    .. py:method:: pending([limit=None])

        Return all unexecuted tasks currently in the queue.

    .. py:method:: scheduled([limit=None])

        Return all unexecuted tasks currently in the schedule.

    .. py:method:: all_results()

        Return a mapping of task-id to pickled result data for all executed tasks whose return values have not been automatically removed.


.. py:class:: TaskWrapper(huey, func[, retries=0[, retry_delay=0[, retries_as_argument=False[, include_task=False[, name=None[, task_base=None[, **task_settings]]]]]]])

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

    .. py:method:: schedule([args=None[, kwargs=None[, eta=None[, delay=None[, convert_utc=True]]]]])

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

    .. py:method:: revoke([revoke_until=None[, revoke_once=False]])

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

    .. py:method:: is_revoked([dt=None])

        Check whether the given task is revoked.  If ``dt`` is specified, it
        will check if the task is revoked with respect to the given datetime.

        :param datetime dt: If provided, checks whether task is revoked at the
            given datetime

    .. py:method:: restore()

        Clears any revoked status and allows the task to run normally.

    .. py:method:: s([*args[, **kwargs]])

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


.. py:class:: QueueTask([data=None[, task_id=None[, execute_time=None[, retries=None[, retry_delay=None[, on_complete=None]]]]]])

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

    .. py:method:: then(task[, *args[, **kwargs]])

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

    .. py:method:: get([blocking=False[, timeout=None[, backoff=1.15[, max_delay=1.0[, revoke_on_timeout=False[, preserve=False]]]]]])

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

    .. py:method:: reschedule([eta=None[, delay=None[, convert+utc=True]]])

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

Storage
-------

Huey

.. py:class:: BaseStorage([name='huey'[, **storage_kwargs]])

    .. py:meth:: enqueue(data)

    .. py:meth:: dequeue(data)

    .. py:meth:: unqueue(data)

    .. py:meth:: queue_size()

    .. py:meth:: enqueued_items([limit=None])

    .. py:meth:: flush_queue()

    .. py:meth:: add_to_schedule(data, timestamp)

    .. py:meth:: read_schedule(timestamp)

    .. py:meth:: schedule_size()

    .. py:meth:: scheduled_items([limit=None])

    .. py:meth:: flush_schedule()

    .. py:meth:: put_data(key, value)

    .. py:meth:: peek_data(key)

    .. py:meth:: pop_data(key)

    .. py:meth:: has_data_for_key(key)

    .. py:meth:: result_store_size()

    .. py:meth:: result_items()

    .. py:meth:: flush_results()

    .. py:meth:: put_error(metadata)

    .. py:meth:: get_errors([limit=None[, offset=0]])

    .. py:meth:: flush_errors()

    .. py:meth:: emit(message)

    .. py:meth:: __iter__()
