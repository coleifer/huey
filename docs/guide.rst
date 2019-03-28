.. _guide:

Guide
=====

The purpose of this document is to present Huey using simple examples that
cover the most common usage of the library. Detailed documentation can be found
in the :ref:`API documentation <api>`.

Here is a simple example of a task that accepts two numbers and returns their
sum:

.. code-block:: python

    # demo.py
    from huey import SqliteHuey

    huey = SqliteHuey(filename='/tmp/demo.db')

    @huey.task()
    def add(a, b):
        return a + b

We can test out huey by running the consumer, specifying the import path to our
``huey`` instance:

.. code-block:: console

    $ huey_consumer.py demo.huey

In a separate terminal, we can use the Python shell to call our ``add`` task:

.. code-block:: pycon

    >>> from demo import add
    >>> r = add(1, 2)
    >>> r()
    3

.. note::
    If you try to resolve the result (``r``) before the task has been executed,
    then ``r()`` will return ``None``. You can avoid this by instructing the
    result to block until the task has finished and a result is ready:

    .. code-block:: pycon

        >>> r = add(1, 2)
        >>> r(blocking=True, timeout=5)  # Wait up to 5 seconds for result.
        3

Here is an explanation of what happened:

1. When the ``add()`` function was called, a message representing the function
   call is placed in a queue.
2. The function returns immediately without actually running, and returns a
   special :py:class:`Result` object, which we can use to retrieve the result
   once the task has been executed.
3. The consumer process sees that a message has arrived, and a worker will call
   the ``add()`` function and place the return value into the result store.
4. We use the :py:class:`Result` object to then read the return value from the
   result store.

For more information, see the :py:meth:`~Huey.task` decorator documentation.

Scheduling tasks
----------------

Tasks can be scheduled to execute at a certain time, or after a delay. In the
following example, we will schedule a call to ``add()`` to run in 10 seconds,
and then will block until the result becomes available:

.. code-block:: pycon

    >>> r = add.schedule((3, 4), delay=10)
    >>> r(blocking=True)  # Will block for ~10 seconds before returning.
    7

If we wished to schedule the task to run at a particular time, we can use the
``eta`` parameter instead. The following example will also be run after a 10
second delay:

.. code-block:: pycon

    >>> eta = datetime.datetime.now() + datetime.timedelta(seconds=10)
    >>> r = add.schedule((4, 5), eta=eta)
    >>> r(blocking=True)  # Will block for ~10 seconds.
    9

Here is an explanation of what happened:

1. When we call the :py:meth:`~TaskWrapper.schedule` method, a message
   representing the function call (including details about when the function
   should be scheduled) is placed in the queue.
2. The function returns immediately without actually running, and returns a
   special :py:class:`Result` object, which we can use to retrieve the result
   once the task has been executed.
3. The consumer process sees that a message has arrived, and will notice that
   the message is not yet ready to be executed, but should be run in ~10s.
4. The consumer adds the message to a schedule.
5. In ~10 seconds, the scheduler will pick-up the message and place it back
   into the queue for execution.
6. A worker will dequeue the message and this time it is ready to execute, so
   the function will be called and the result placed in the result store.
7. The :py:class:`Result` object from step 2 will now be able to read the
   return value from the task.

For more details, see the :py:meth:`~TaskWrapper.schedule` API documentation.

Periodic tasks
--------------

Huey provides crontab-like functionality that enables functions to be executed
automatically on a given schedule. In this example we will declare a periodic
task that executes every 3 minutes and prints a message in the consumer process
stdout:

.. code-block:: python

    from huey import SqliteHuey
    from huey import crontab

    huey = SqliteHuey(filename='/tmp/demo.db')

    @huey.task()
    def add(a, b):
        return a + b

    @huey.periodic_task(crontab(minute='*/3'))
    def every_three_minutes():
        print('This task runs every three minutes')

The same scheduler that handles enqueueing tasks which are scheduled to run in
the future also handles enqueueing periodic tasks. Once a minute, the scheduler
will check to see if any of the periodic tasks should be called, and if so will
place a message on the queue, instructing the next available worker to run the
function.

.. note::
    Because periodic tasks are called independent of any user interaction, they
    should not accept any parameters.

Similarly, the return-value for a periodic task is discarded, rather than being
put into the result store. The reason for this is because there would not be an
obvious way for an application to obtain a :py:class:`Result` handle to access
the result of a given periodic task execution.

The :py:func:`crontab` function accepts the following arguments:

* minute
* hour
* day
* month
* day_of_week (0=Sunday, 6=Saturday)

Acceptable inputs:

* ``*`` - always true, e.g. if ``hour='*'``, then the rule matches any hour.
* ``*/n`` - every *n* interval, e.g. ``minute='*/15'`` means every 15 minutes.
* ``m-n`` - run every time ``m..n`` inclusive.
* ``m,n`` - run on *m* and *n*.

Multiple rules can be expressed by separating the individual rules with a
comma, for example:

.. code-block:: python

    # Runs every 10 minutes between 9a and 11a, and 4p-6p.
    crontab(minute='*/10', hour='9-11,16-18')

For more information see the following API documentation:

* :py:meth:`~Huey.periodic_task`
* :py:func:`crontab`

Retrying tasks that fail
------------------------

Sometimes we may have a task that we anticipate might fail from time to time,
in which case we should retry it. Huey supports automatically retrying tasks a
given number of times, optionally with a delay between attempts.

Here we'll declare a task that fails approximately half of the time. To
configure this task to be automatically retried, use the ``retries`` parameter
of the :py:meth:`~Huey.task` decorator:

.. code-block:: python

    import random

    @huey.task(retries=2)  # Retry the task up to 2 times.
    def flaky_task():
        if random.randint(0, 1) == 0:
            raise Exception('failing!')
        return 'OK'

Here is what might happen behind-the-scenes if we call this task:

1. Message is placed on the queue indicating that our task should be called,
   just like usual, and a :py:class:`Result` handle is returned to the caller.
2. Consumer picks up the message and attempts to run the task, but the call to
   ``random.randint()`` happened to return ``0``, so an exception is raised.
3. The consumer puts the error into the result store and the exception is
   logged. If the caller resolves the :py:class:`Result` now, a
   :py:class:`TaskException` will be raised which contains information about
   the exception that occurred in our task.
4. The consumer notices that the task can be retried 2 times, so it decrements
   the retry count and re-enqueues it for execution.
5. The consumer picks up the message again and runs the task. This time, the
   task succeeds! The new return value is placed into the result store ("OK").
6. We can reset our :py:class:`Result` wrapper by calling
   :py:meth:`~Result.reset` and then re-resolve it. The result object will now
   give us the new value, "OK".

Should the task fail on the first invocation, it will be retried up-to two
times. Note that it will be retried *immediately* after it returns.

To specify a delay between retry attempts, we can add a ``retry_delay``
argument. The task will be retried up-to two times, with a delay of 10 seconds
between attempts:

.. code-block:: python

    @huey.task(retries=2, retry_delay=10)
    def flaky_task():
        # ...

.. note::
    Retries and retry delay arguments can also be specified for periodic tasks.

It is also possible to explicitly retry a task from within the task, by raising
a :py:class:`RetryTask` exception. When this exception is used, the task will
be retried regardless of whether it was declared with ``retries``. Similarly,
the task's remaining retries (if they were declared) will not be affected by
raising :py:class:`RetryTask`.

For more information, see the following API documentation:

* :py:meth:`~Huey.task` and :py:meth:`~Huey.periodic_task`
* :py:class:`Result`

Canceling or pausing tasks
--------------------------

Huey can dynamically cancel tasks from executing at runtime. This applies to
regular tasks, tasks scheduled to execute in the future, and periodic tasks.

Any task can be canceled ("revoked"), provided the task is not being executed
by the consumer. Similarly, a revoked task can be restored, provided it has not
already been processed and discarded by the consumer. To do this we will use
the :py:meth:`Result.revoke` and :py:meth:`Result.restore` methods:

.. code-block:: python

    # Schedule a task to execute in 60 seconds.
    res = add.schedule((1, 2), delay=60)

    # Provided the 60s has not elapsed, the task can be canceled
    # by calling the `revoke()` method on the result object.
    res.revoke()

    # We can check to see if the task is revoked.
    res.is_revoked()  # -> True

    # Similarly, we can restore the task, provided the 60s has
    # not elapsed (at which point it would have been read and
    # discarded by the consumer).
    res.restore()

To revoke *all* instances of a given task, use the
:py:meth:`~TaskWrapper.revoke` and :py:meth:`~TaskWrapper.restore` methods on
the task function itself:

.. code-block:: python

    # Prevent all instances of the add() task from running.
    add.revoke()

    # We can check to see that all instances of the add() task
    # are revoked:
    add.is_revoked()  # -> True

    # We can enqueue an instance of the add task, and then check
    # to verify that it is revoked:
    res = add(1, 2)
    res.is_revoked()  # -> True

    # To re-enable a task, we'll use the restore() method on
    # the task function:
    add.restore()

    # Is the add() task enabled again?
    add.is_revoked()  # -> False

So as you can see, Huey provides APIs to control revoke / restore on both
individual instances of a task, as well as all instances of the task. For more
information, see the following API docs:

* :py:meth:`Result.revoke` and :py:meth:`Result.restore` for revoking
  individual instances of a task.
* :py:meth:`Result.is_revoked` for checking the status of a task instance.
* :py:meth:`TaskWrapper.revoke` and :py:meth:`TaskWrapper.restore` for revoking
  all instances of a task.
* :py:meth:`TaskWrapper.is_revoked` for checking the status of the task
  function itself.

Canceling or pausing periodic tasks
-----------------------------------

The ``revoke()`` and ``restore()`` methods support some additional options
which may be especially useful when used with :py:meth:`~Huey.periodic_task`.

The :py:meth:`~TaskWrapper.revoke` method accepts two optional parameters:

* ``revoke_once`` - boolean flag, if set then only the next occurrence of the
  task will be revoked, after which it will be restored automatically.
* ``revoke_until`` - datetime, which specifies the time at which the task
  should be automatically restored.

For example, suppose we have a task that sends email notifications, but our
mail server goes down and won't be fixed for a while. We can revoke the task
for a couple of hours, after which time it will start executing again:

.. code-block:: python

    @huey.periodic_task(crontab(minute='0', hour='*'))
    def send_notification_emails():
        # ... code to send emails ...

Here is how we might revoke the task for the next 3 hours:

.. code-block:: pycon

    >>> now = datetime.datetime.now()
    >>> eta = now + datetime.timedelta(hours=3)
    >>> send_notification_emails.revoke(revoke_until=eta)

Alternatively, we could use ``revoke_once=True`` to just skip the next
execution of the task:

.. code-block:: pycon

    >>> send_notification_emails.revoke(revoke_once=True)

At any time, the task can be restored using the usual
:py:meth:`~TaskWrapper.restore` method, and it's status can be checked using
the :py:meth:`~TaskWrapper.is_revoked` method.

Task pipelines
--------------

Huey supports pipelines (or chains) of one or more tasks that should be
executed sequentially.

To get started, I'll just review the usual method of running a task:

.. code-block:: python

    @huey.task()
    def add(a, b):
        return a + b

    result = add(1, 2)

A slightly more verbose way of writing that would be to use the
:py:meth:`~TaskWrapper.s` method to create a :py:class:`Task` instance and then
enqueue it explicitly:

.. code-block:: python

    # Create a task representing the execution of add(1, 2).
    task = add.s(1, 2)

    # Enqueue the task instance, which returns a Result handle.
    result = huey.enqueue(task)

So the following are equivalent:

.. code-block:: python

    result = add(1, 2)

    # And:
    result = huey.enqueue(add.s(1, 2))

The :py:meth:`TaskWrapper.s` method is used to create a :py:class:`Task`
instance, which represents the execution of the given function. The
``Task`` is what gets serialized and enqueued, then dequeued, deserialized and
executed by the consumer.

To create a pipeline, we will use the :py:meth:`TaskWrapper.s` method to create
a :py:class:`Task` instance. We can then chain additional tasks using the
:py:meth:`Task.then` method:

.. code-block:: python

    add_task = add.s(1, 2)  # Create Task to represent add(1, 2) invocation.

    # Add additional tasks to pipeline by calling add_task.then().
    pipeline = (add_task
                .then(add, 3)  # Call add() with previous result (1+2) and 3.
                .then(add, 4)  # Previous result ((1+2)+3) and 4.
                .then(add, 5)) # Etc.

    # When a pipeline is enqueued, a ResultGroup is returned (which is
    # comprised of individual Result instances).
    result_group = huey.enqueue(pipeline)

    # Print results of above pipeline.
    print(result_group.get(blocking=True))
    # [3, 6, 10, 15]

    # Alternatively, we could have iterated over the result group:
    for result in result_group:
        print(result.get(blocking=True))
    # 3
    # 6
    # 10
    # 15

When enqueueing a task pipeline, the return value will be a
:py:class:`ResultGroup`, which encapsulates the :py:class:`Result` objects for
the individual task invocations. :py:class:`ResultGroup` can be iterated over
to yield individual :py:class:`Result` items, or you can use the
:py:meth:`ResultGroup.get` method to get all the task return values as a list.

Note that the return value from the parent task is passed to the next task in
the pipeline, and so on.

If the value returned by the parent function is a ``tuple``, then the tuple
will be used to extend the ``*args`` for the next task.  Likewise, if the
parent function returns a ``dict``, then the dict will be used to update the
``**kwargs`` for the next task.

Example of chaining fibonacci calculations:

.. code-block:: python

    @huey.task()
    def fib(a, b=1):
        a, b = a + b, a
        return (a, b)  # returns tuple, which is passed as *args

    pipe = (fib.s(1)
            .then(fib)
            .then(fib)
            .then(fib))
    results = huey.enqueue(pipe)

    print(results(True))  # Resolve results, blocking until all are finished.
    # [(2, 1), (3, 2), (5, 3), (8, 5)]

For more information, see the following API docs:

* :py:meth:`TaskWrapper.s`
* :py:meth:`Task.then`
* :py:class:`ResultGroup` and :py:class:`Result`

Locking tasks
-------------

Task locking can be accomplished using the :py:meth:`Huey.lock_task` method,
which acts can be used as a context-manager or decorator.

This lock is designed to be used to prevent multiple invocations of a task from
running concurrently. If using the lock as a decorator, place it directly above
the function declaration.

If a second invocation occurs and the lock cannot be acquired, then a special
:py:class:`TaskLockedException` is raised and the task will not be executed.
If the task is configured to be retried, then it will be retried normally, but
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

Signals
-------

The :py:class:`Consumer` will send :ref:`signals <signals>` as it moves through
various stages of its operations. The :py:meth:`Huey.signal` method can be used
to attach a callback to one or more signals, which will be invoked
synchronously by the consumer when the signal is sent.

For a simple example, we can add a signal handler that simply prints the signal
name and the ID of the related task.

.. code-block:: python

    @huey.signal()
    def print_signal_args(signal, task, exc=None):
        if signal == SIGNAL_ERROR:
            print('%s - %s - exception: %s' % (signal, task.id, exc))
        else:
            print('%s - %s' % (signal, task.id))

The :py:meth:`~Huey.signal` method is used to decorate the signal-handling
function. It accepts an optional list of signals. If none are provided, as in
our example, then the handler will be called for any signal.

The callback function (``print_signal_args``) accepts two required arguments,
which are present on every signal: ``signal`` and ``task``. Additionally, our
handler accepts an optional third argument ``exc`` which is only included with
``SIGNAL_ERROR``. ``SIGNAL_ERROR`` is only sent when a task raises an uncaught
exception during execution.

.. warning::
    Signal handlers are executed *synchronously* by the consumer, so it is
    typically a bad idea to introduce any slow operations into a signal
    handler.

For a complete list of Huey's signals and their meaning, see the :ref:`signals`
document, and the :py:meth:`Huey.signal` API documentation.

.. _immediate:

Immediate mode
--------------

.. note::
    Immediate mode replaces the *always eager* mode available prior to the
    release of Huey 2. It offers many improvements over always eager mode,
    which are described in the :ref:`changes` document.

Huey can be run in a special mode called *immediate* mode, which is very useful
during testing and development. In immediate mode, Huey will execute task
functions immediately rather than enqueueing them, while still preserving the
APIs and behaviors one would expect when running a dedicated consumer process.

Immediate mode can be enabled in two ways:

.. code-block:: python

    huey = RedisHuey('my-app', immediate=True)

    # Or at any time, via the "immediate" attribute:
    huey = RedisHuey('my-app')
    huey.immediate = True

To disable immediate mode:

.. code-block:: python

    huey.immediate = False

By default, enabling immediate mode will switch your Huey instance to using
in-memory storage. This is to prevent accidentally reading or writing to live
storage while doing development or testing. If you prefer to use immediate mode
with live storage, you can specify ``immediate_use_memory=False`` when creating
your :py:class:`Huey` instance:

.. code-block:: python

    huey = RedisHuey('my-app', immediate_use_memory=False)

You can try out immediate mode quite easily in the Python shell. In the
following example, everything happens within the interpreter -- no separate
consumer process is needed. In fact, because immediate mode switches to an
in-memory storage when enabled, we don't even have to be running a Redis
server:

.. code-block:: pycon

    >>> from huey import RedisHuey
    >>> huey = RedisHuey()
    >>> huey.immediate = True

    >>> @huey.task()
    ... def add(a, b):
    ...     return a + b
    ...

    >>> result = add(1, 2)
    >>> result()
    3

    >>> add.revoke(revoke_once=True)  # We can revoke tasks.
    >>> result = add(2, 3)
    >>> result() is None
    True

    >>> add(3, 4)()  # No longer revoked, was restored automatically.
    7

What happens if we try to schedule a task for execution in the future, while
using immediate mode?

.. code-block:: pycon

    >>> result = add.schedule((4, 5), delay=60)
    >>> result() is None  # No result.
    True

As you can see, the task was not executed. So what happened to it? The answer
is that the task was added to the in-memory storage layer's schedule. We can
check this by calling :py:meth:`Huey.scheduled`:

.. code-block:: pycon

    >>> huey.scheduled()
    [__main__.add: 8873...bcbd @2019-03-27 02:50:06]

Since immediate mode is fully synchronous, there is not a separate thread
monitoring the schedule. The schedule can still be read or written to, but
scheduled tasks will not automatically be executed.

Tips and tricks
---------------

To call a task-decorated function in its original form, you can use
:py:meth:`~TaskWrapper.call_local`:

.. code-block:: python

    @huey.task()
    def add(a, b):
        return a + b

    # Call the add() function in "un-decorated" form, skipping all
    # the huey stuff:
    add.call_local(3, 4)  # Returns 7.

It's also worth mentioning that python decorators are just syntactical sugar
for wrapping a function with another function. Thus, the following two examples
are equivalent:

.. code-block:: python

    @huey.task()
    def add(a, b):
        return a + b

    # Equivalent to:
    def _add(a, b):
        return a + b

    add = huey.task()(_add)

Task functions can be applied multiple times to a list (or iterable) of
parameters using the :py:meth:`~TaskWrapper.map` method:

.. code-block:: pycon

    >>> @huey.task()
    ... def add(a, b):
    ...     return a + b
    ...

    >>> params = [(i, i ** 2) for i in range(10)]
    >>> result_group = add.map(params)
    >>> result_group.get(blocking=True)
    [0, 2, 6, 12, 20, 30, 42, 56, 72, 90]

The Huey result-store can be used directly if you need a convenient way to
cache arbitrary key/value data:

.. code-block:: python

    @huey.task()
    def calculate_something():
        # By default, the result store treats get() like a pop(), so in
        # order to preserve the data so it can be read again, we specify
        # the second argument, peek=True.
        prev_results = huey.get('calculate-something.result', peek=True)
        if prev_results is None:
            # No previous results found, start from the beginning.
            data = start_from_beginning()
        else:
            # Only calculate what has changed since last time.
            data = just_what_changed(prev_results)

        # We can store the updated data back in the result store.
        huey.put('calculate-something.result', data)
        return data

See :py:meth:`Huey.get` and :py:meth:`Huey.put` for additional details.

Reading more
------------

That sums up the basic usage patterns of huey. Below are links for details on
other aspects of the APIs:

* :py:class:`Huey` - responsible for coordinating executable tasks and queue
  backends
* :py:meth:`Huey.task` - decorator to indicate an executable task.
* :py:class:`Result` - handle for interacting with a task.
* :py:meth:`Huey.periodic_task` - decorator to indicate a task that executes at
  periodic intervals.
* :py:func:`crontab` - define what intervals to execute a periodic command.
* For information about managing shared resources like database connections,
  refer to the :ref:`shared resources <shared_resources>` document.

Also check out the :ref:`notes on running the consumer <consuming-tasks>`.
