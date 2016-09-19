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

        1. Serialize the function call into a message suitable for storing in the queue
        2. Enqueue the message for execution by the consumer
        3. If a ``result_store`` has been configured, return an :py:class:`TaskResultWrapper`
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

        Now, whenever you call this function in your application, the actual processing
        will occur when the consumer dequeues the message and your application will
        continue along on its way.

        Without a result store:

        .. code-block:: pycon

            >>> res = count_some_beans(1000000)
            >>> res is None
            True

        With a result store:

        .. code-block:: pycon

            >>> res = count_some_beans(1000000)
            >>> res
            <huey.api.TaskResultWrapper object at 0xb7471a4c>
            >>> res()
            'Counted 1000000 beans'

        :param int retries: number of times to retry the task if an exception occurs
        :param int retry_delay: number of seconds to wait between retries
        :param boolean retries_as_argument: whether the number of retries should
            be passed in to the decorated function as an argument.
        :param boolean include_task: whether the task instance itself should be
            passed in to the decorated function as the ``task`` argument.
        :rtype: decorated function

        The return value of any calls to the decorated function depends on whether
        the :py:class:`Huey` instance is configured with a ``result_store``.  If a
        result store is configured, the decorated function will return
        an :py:class:`TaskResultWrapper` object which can fetch the result of the call from
        the result store -- otherwise it will simply return ``None``.

        The ``task`` decorator also does one other important thing -- it adds
        a special function **onto** the decorated function, which makes it possible
        to *schedule* the execution for a certain time in the future:

        .. py:function:: {decorated func}.schedule(args=None, kwargs=None, eta=None, delay=None, convert_utc=True)

            Use the special ``schedule`` function to schedule the execution of a
            queue task for a given time in the future:

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
            :param datetime eta: the time at which the function should be executed
            :param int delay: number of seconds to wait before executing function
            :param convert_utc: whether the ``eta`` or ``delay`` should be converted from local time to UTC, defaults to ``True``. If you are running your consumer in ``localtime`` mode, you should probably specify ``False`` here.
            :rtype: like calls to the decorated function, will return an :py:class:`TaskResultWrapper`
                    object if a result store is configured, otherwise returns ``None``

        .. py:function:: {decorated func}.call_local

            Call the ``@task``-decorated function without enqueueing the call. Or, in other words, ``call_local()`` provides access to the actual function.

            .. code-block:: pycon

                >>> count_some_beans.call_local(1337)
                'Counted 1337 beans'

        .. py:attribute:: {decorated func}.task_class

            Store a reference to the task class for the decorated function.

            .. code-block:: pycon

                >>> count_some_beans.task_class
                tasks.queuecmd_count_beans


    .. py:method:: periodic_task(validate_datetime)

        Function decorator that marks the decorated function for processing by the
        consumer *at a specific interval*.  Calls to functions decorated with ``periodic_task``
        will execute normally, unlike :py:meth:`~Huey.task`, which enqueues tasks
        for execution by the consumer.  Rather, the ``periodic_task`` decorator
        serves to **mark a function as needing to be executed periodically** by the
        consumer.

        .. note::
            By default, the consumer will execute ``periodic_task`` functions. To
            disable this, run the consumer with ``-n`` or ``--no-periodic``.

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
        :rtype: decorated function

        Like :py:meth:`~Huey.task`, the periodic task decorator adds several helpers
        to the decorated function.  These helpers allow you to "revoke" and "restore" the
        periodic task, effectively enabling you to pause it or prevent its execution.

        .. py:function:: {decorated_func}.revoke([revoke_until=None[, revoke_once=False]])

            Prevent the given periodic task from executing.  When no parameters are
            provided the function will not execute again.

            This function can be called multiple times, but each call will overwrite
            the limitations of the previous.

            :param datetime revoke_until: Prevent the execution of the task until the
                given datetime.  If ``None`` it will prevent execution indefinitely.
            :param bool revoke_once: If ``True`` will only prevent execution the next
                time it would normally execute.

            .. code-block:: python

                # skip the next execution
                every_five_minutes.revoke(revoke_once=True)

                # pause the command indefinitely
                every_five_minutes.revoke()

                # pause the command for 24 hours
                every_five_minutes.revoke(datetime.datetime.now() + datetime.timedelta(days=1))

        .. py:function:: {decorated_func}.is_revoked([dt=None])

            Check whether the given periodic task is revoked.  If ``dt`` is specified,
            it will check if the task is revoked for the given datetime.

            :param datetime dt: If provided, checks whether task is revoked at the
                given datetime

        .. py:function:: {decorated_func}.restore()

            Clears any revoked status and run the task normally

        If you want access to the underlying task class, it is stored as an attribute
        on the decorated function:

        .. py:attribute:: {decorated_func}.task_class

            Store a reference to the task class for the decorated function.

    .. py:method:: revoke(task[, revoke_until=None[, revoke_once=False]])

        Prevent the given task from being executed by the consumer after it has
        been enqueued. To understand this method, you need to know a bit about
        how the consumer works. When you call a function decorated by the
        :py:meth:`Huey.task` method, calls to that function will enqueue a
        message to the consumer indicating which task to execute, what the
        parameters are, etc. If the task is not scheduled to execute in the
        future, and there is a free worker available, the task starts executing
        immediately. Otherwise if workers are busy, it will wait in line for
        the next free worker.

        When you revoke a task, when the worker picks up the revoked task to
        start executing it, it will instead just throw it away and get the next
        available task. So, revoking a task only has affect between the time
        you call the task and the time the worker actually starts executing the
        task.

        .. note::
            When the revoked task is a periodic task, this affects the task as
            a whole. When the task is a normal task, the revocation action only
            applies to the given task instance.

        This function can be called multiple times, but each call will overwrite
        any previous revoke settings.

        :param datetime revoke_until: Prevent the execution of the task until the
            given datetime.  If ``None`` it will prevent execution indefinitely.
        :param bool revoke_once: If ``True`` will only prevent execution the
            next time it would normally execute.

    .. py:method:: restore(task)

        Takes a previously revoked task and un-revokes it.

    .. py:method:: revoke_by_id(task_id[, revoke_until=None[, revoke_once=False]])

        Exactly the same as :py:meth:`Huey.revoke`, except it accepts a task ID
        instead of the task instance itself.

    .. py:method:: restore_by_id(task_id)

        Exactly the same as :py:meth:`Huey.restore`, except it accepts a task ID
        instead of the task instance itself.

    .. py:method:: is_revoked(task[, dt=None])

        Returns a boolean indicating whether the given task is revoked. If the
        ``dt`` parameter is specified, then the result will indicate whether
        the task is revoked at that particular datetime.

    .. py:method:: result(task_id[, blocking=False[, timeout=None[, backoff=1.15[, max_delay=1.0[, revoke_on_timeout=False[, preserve=False]]]]]])

        Attempt to retrieve the return value of a task.  By default, :py:meth:`~Huey.result`
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

    .. py:method:: pending([limit=None])

        Return all unexecuted tasks currently in the queue.

    .. py:method:: scheduled([limit=None])

        Return all unexecuted tasks currently in the schedule.

    .. py:method:: all_results()

        Return a mapping of task-id to pickled result data for all executed tasks whose return values have not been automatically removed.


.. py:function:: crontab(month='*', day='*', day_of_week='*', hour='*', minute='*')

    Convert a "crontab"-style set of parameters into a test function that will
    return ``True`` when a given ``datetime`` matches the parameters set forth in
    the crontab.

    Acceptable inputs:

    - "*" = every distinct value
    - "\*/n" = run every "n" times, i.e. hours='\*/4' == 0, 4, 8, 12, 16, 20
    - "m-n" = run every time m..n
    - "m,n" = run on m and n

    :rtype: a test function that takes a ``datetime`` and returns a boolean

TaskResultWrapper
---------

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
    about a minute to calculate:

    .. code-block:: python

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

        Restore the given task.  Unless it has already been skipped over, it
        will be restored and run as scheduled.
