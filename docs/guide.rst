.. _guide:

Guide
=====

The purpose of this document is to present Huey using simple examples that
cover the most common usage of the library. Detailed documentation can be found
in the :ref:`API documentation <api>`.

Example :py:meth:`~Huey.task` that adds two numbers:

.. code-block:: python

    # demo.py
    from huey import SqliteHuey

    huey = SqliteHuey(filename='/tmp/demo.db')

    @huey.task()
    def add(a, b):
        return a + b

To test, run the consumer, specifying the import path to the ``huey`` object:

.. code-block:: console

    $ huey_consumer.py demo.huey

In a Python shell, we can call our ``add`` task:

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

What happens when we call a task function?

1. When the ``add()`` function is called, a message representing the call is
   placed in a queue.
2. The function returns immediately without actually running, and returns a
   :py:class:`Result` handle, which can be used to retrieve the result once the
   task has been executed by the consumer.
3. The consumer process sees that a message has arrived, and a worker will call
   the ``add()`` function and place the return value into the result store.
4. We can use the :py:class:`Result` handle to read the return value from the
   result store.

For more information, see the :py:meth:`~Huey.task` decorator documentation.

Scheduling tasks
----------------

Tasks can be scheduled to execute at a certain time, or after a delay.

In the following example, we will schedule a call to ``add()`` to run in 10
seconds, and then will block until the result becomes available:

.. code-block:: pycon

    >>> r = add.schedule((3, 4), delay=10)
    >>> r(blocking=True)  # Will block for ~10 seconds before returning.
    7

If we wished to schedule the task to run at a particular time, we can use the
``eta`` parameter instead. The following example will run after a 10 second
delay:

.. code-block:: pycon

    >>> eta = datetime.datetime.now() + datetime.timedelta(seconds=10)
    >>> r = add.schedule((4, 5), eta=eta)
    >>> r(blocking=True)  # Will block for ~10 seconds.
    9

What happens when we schedule a task?

1. When we call :py:meth:`~TaskWrapper.schedule`, a message is placed on the
   queue instructing the consumer to call the ``add()`` function in 10 seconds.
2. The function returns immediately, and returns a :py:class:`Result` handle.
3. The consumer process sees that a message has arrived, and will notice that
   the message is not yet ready to be executed, but should be run in ~10s.
4. The consumer adds the message to a schedule.
5. In ~10 seconds, the scheduler will pick-up the message and place it back
   into the queue for execution.
6. A worker will dequeue the message, execute the ``add()`` function, and place
   the return value in the result store.
7. The :py:class:`Result` handle from step 2 will now be able to read the
   return value from the task.

For more details, see the :py:meth:`~TaskWrapper.schedule` API documentation.

Periodic tasks
--------------

Huey provides crontab-like functionality that enables functions to be executed
automatically on a given schedule.

In the following example, we will declare a :py:meth:`~Huey.periodic_task` that
executes every 3 minutes and prints a message on consumer process stdout:

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

Once a minute, the scheduler will check to see if any of the periodic tasks
should be called. If so, the task will be enqueued for execution.

.. note::
    Because periodic tasks are called independent of any user interaction, they
    do not accept any arguments.

    Similarly, the return-value for periodic tasks is discarded, rather than
    being put into the result store. This is because there is not an obvious
    way for an application to obtain a :py:class:`Result` handle to access the
    result of a given periodic task execution.

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

What happens when we call this task?

1. Message is placed on the queue and a :py:class:`Result` handle is returned
   to the caller.
2. Consumer picks up the message and attempts to run the task, but the call to
   ``random.randint()`` happens to return ``0``, raising an ``Exception``.
3. The consumer puts the error into the result store and the exception is
   logged. If the caller resolves the :py:class:`Result` now, a
   :py:class:`TaskException` will be raised which contains information about
   the exception that occurred in our task.
4. The consumer notices that the task can be retried 2 times, so it decrements
   the retry count and re-enqueues it for execution.
5. The consumer picks up the message again and runs the task. This time, the
   task succeeds! The new return value is placed into the result store ("OK").
6. We can reset our :py:class:`Result` handle by calling
   :py:meth:`~Result.reset` and then re-resolve it. The result handle will now
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
raising :py:class:`RetryTask`. Example:

.. code-block:: python

    @huey.task()
    def fetch_api_data(url):
        try:
            fh = urlopen(url)
        except HTTPError:
            # Try again in 60 seconds for an HTTP error (500, etc).
            raise RetryTask(delay=60)
        ...

For more information, see the following API documentation:

* :py:meth:`~Huey.task` and :py:meth:`~Huey.periodic_task`
* :py:class:`Result`
* :py:class:`RetryTask`

.. _priority:

Task priority
-------------

.. note::
    Priority support for Redis requires Redis 5.0 or newer. To use task
    priorities with Redis, use the :py:class:`PriorityRedisHuey` instead of
    :py:class:`RedisHuey`.

    Task prioritization is fully supported by :py:class:`SqliteHuey` and the
    file-based :py:class:`FileHuey`. The in-memory storage layer (used when
    :ref:`immediate` is enabled) also supports task priorities.

Huey tasks can be given a priority, allowing you to ensure that your most
important tasks do not get delayed when the workers are busy.

Priorities can be assigned to a task function, in which case all invocations of
the task will default to the given priority. Additionally, individual task
invocations can be assigned a priority on a one-off basis.

.. note::
    When no priority is given, the task will default to a priority of ``0``.

To see how this works, lets define a task that has a priority (``10``):

.. code-block:: python

    @huey.task(priority=10)
    def send_email(to, subj, body):
        return mailer.send(to, 'webmaster@myapp.com', subj, body)

When we invoke this task, it will be processed *before* any other pending tasks
whose priority is less than 10. So we could imagine our queue looking something
like this:

* ``process_payment`` - priority = 50
* ``check_spam`` - priority = 1
* ``make_thumbnail`` - priority = 0 (default)

Invoke the ``send_email()`` task:

.. code-block:: python

    send_email('new_user@foo.com', 'Welcome', 'blah blah')

Now the queue of pending tasks would be:

* ``process_payment`` - priority = 50
* ``send_email`` - priority = 10
* ``check_spam`` - priority = 1
* ``make_thumbnail`` - priority = 0

We can override the default priority by passing ``priority=`` as a keyword
argument to the task function:

.. code-block:: python

    send_email('boss@mycompany.com', 'Important!', 'etc', priority=90)

Now the queue of pending tasks would be:

* ``send_email`` (to boss) - priority = 90
* ``process_payment`` - priority = 50
* ``send_email`` - priority = 10
* ``check_spam`` - priority = 1
* ``make_thumbnail`` - priority = 0

Task priority only affects the ordering of tasks as they are pulled from the
queue of pending tasks. If there are periods of time where your workers are not
able to keep up with the influx of tasks, Huey's ``priority`` feature can
ensure that your most important tasks do not get delayed.

Task-specific priority overrides can also be specified when scheduling a task
to run in the future:

.. code-block:: python

    # Uses priority=10, since that was the default we used when
    # declaring the send_email task:
    send_email.schedule(('foo@bar.com', 'subj', 'msg'), delay=60)

    # Override, specifying priority=50 for this task.
    send_email.schedule(('bar@foo.com', 'subj', 'msg'), delay=60, priority=50)

Lastly, we can specify priority on :py:class:`~Huey.periodic_task`:

.. code-block:: python

    @huey.periodic_task(crontab(minute='0', hour='*/3'), priority=10)
    def some_periodic_task():
        # ...

For more information:

* :py:class:`PriorityRedisHuey` - Huey implementation that adds support for
  task priorities with the Redis storage layer. *Requires Redis 5.0 or newer*.
* :py:class:`SqliteHuey` and the in-memory storage used when immediate-mode is
  enabled have full support for task priorities.
* :py:meth:`~Huey.task` and :py:meth:`~Huey.periodic_task`

Canceling or pausing tasks
--------------------------

Huey tasks can be cancelled dynamically at runtime. This applies to regular
tasks, tasks scheduled to execute in the future, and periodic tasks.

Any task can be canceled ("revoked"), provided the task has not started
executing yet. Similarly, a revoked task can be restored, provided it has not
already been processed and discarded by the consumer.

Using the :py:meth:`Result.revoke` and :py:meth:`Result.restore` methods:

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

Huey provides APIs to revoke / restore on both individual instances of a task,
as well as all instances of the task. For more information, see the following
API docs:

* :py:meth:`Result.revoke` and :py:meth:`Result.restore` for revoking
  individual instances of a task.
* :py:meth:`Result.is_revoked` for checking the status of a task instance.
* :py:meth:`TaskWrapper.revoke` and :py:meth:`TaskWrapper.restore` for revoking
  all instances of a task.
* :py:meth:`TaskWrapper.is_revoked` for checking the status of the task
  function itself.

Canceling from within a Task
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Huey provides a special :py:class:`CancelExecution` exception which can be
raised, either within a :py:meth:`~Huey.pre_execute` hook or within the body of
a :py:meth:`~Huey.task`-decorated function, to cancel the execution of the
task. Additionally, when raised from within a task, the ``CancelExecution``
exception can override the task's default retry policy, by specifying either
``retry=True/False``.

Example:

.. code:: python

    @huey.task(retries=2)
    def load_data():
        if something_temporary_is_wrong():
            # Task will be retried, even if it has run out of retries or is a
            # task that does not specify any automatic retries.
            raise CancelExecution(retry=True)
        elif something_fatal_is_wrong():
            # Task will NOT be retried, even if it has more than one retry
            # remaining.
            raise CancelExecution(retry=False)
        elif cancel_and_maybe_retry():
            # Task will only be retried if it has one or more retries
            # remaining (this is the default).
            raise CancelExecution()

        ...

For more information, see: :py:class:`CancelExecution`.

Canceling or pausing periodic tasks
-----------------------------------

The ``revoke()`` and ``restore()`` methods support some additional options
which may be especially useful for :py:meth:`~Huey.periodic_task`.

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

Task expiration
---------------

Huey tasks can be configured with an expiration time. Setting an expiration
time on tasks will prevent them being run after the given time has elapsed.
Expiration times may be useful if your queue is busy and there may be a
significant lag between the time a task is enqueued and the time the consumer
starts executing it.

Expiration times can be specified as:

* ``datetime()`` instances, which are treated as absolute times.
* ``timedelta()`` or ``int``, which are relative to the time *at which the task
  is enqueued*.

A default expire time can be provided when declaring a task:

.. code-block:: python

    # Task must be executed by consumer within 60s of being enqueued.
    @huey.task(expires=60)
    def time_sensitive_task(...):

Expiration times can be specified per-invocation, as well:

.. code-block:: python

    # Task must be executed by consumer within 5 minutes of being enqueued.
    time_sensitive_task(report_file, expires=timedelta(seconds=300))

Expiration times can also be specified when scheduling tasks:

.. code-block:: python

    # Task scheduled to run in 1 hour, and once enqueued for execution, must be
    # run within 60 seconds.
    time_sensitive_task.schedule(
        args=(report_file,),
        delay=timedelta(seconds=3600),
        expires=timedelta(seconds=60))

    # Example using absolute datetimes instead of relative deltas:
    one_hr = datetime.now() + timedelta(seconds=3600)
    time_sensitive_task.schedule(
        args=(report_file,),
        eta=one_hr,
        expires=one_hr + timedelta(seconds=60))

Task pipelines
--------------

Huey supports pipelines (or chains) of one or more tasks that should be
executed sequentially.

To get started, let's review the usual way we execute tasks:

.. code-block:: python

    @huey.task()
    def add(a, b):
        return a + b

    result = add(1, 2)

An equivalent, but more verbose, way is to use the :py:meth:`~TaskWrapper.s`
method to create a :py:class:`Task` instance and then enqueue it explicitly:

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
instance (which represents the execution of the given function). The
``Task`` is what gets serialized and sent to the consumer.

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
the individual tasks. :py:class:`ResultGroup` can be iterated over or you can
use the :py:meth:`ResultGroup.get` method to get all the task return values as
a list.

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
which can be used as a context-manager or decorator.

This lock prevents multiple invocations of a task from running concurrently.

If a second invocation occurs and the lock cannot be acquired, then a special
:py:class:`TaskLockedException` is raised and the task will not be executed.
If the task is configured to be retried, then it will be retried normally.

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

See :py:meth:`Huey.lock_task` for API documentation.

Signals
-------

The :py:class:`Consumer` sends :ref:`signals <signals>` as it processes tasks.
The :py:meth:`Huey.signal` method can be used to attach a callback to one or
more signals, which will be invoked synchronously by the consumer when the
signal is sent.

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

.. _logging:

Logging
-------

Huey uses the standard library ``logging`` module to log information about task
execution and consumer activity. Messages are logged to the ``huey`` namespace,
with consumer-specific messages being logged to ``huey.consumer``.

When the consumer is run, it binds a default ``StreamHandler()`` to the huey
namespace so that all messages are logged to the console. The consumer logging
can be configured using the following consumer options:

* ``-l FILE, --logfile=FILE`` - log to a file.
* ``-v, --verbose`` - verbose logging (includes DEBUG level)
* ``-q, --quiet`` - minimal logging
* ``-S, --simple`` - simple logging format ("time message")

If you would like to get email alerts when an error occurs, you can attach a
``logging.handlers.SMTPHandler`` to the ``huey`` namespace at level ``ERROR``:

.. code:: python

    from logging.handlers import SMTPHandler
    import logging

    mail_handler = SMTPHandler(
        mailhost=('smtp.gmail.com', 587),
        fromaddr='errors@myapp.com',
        toaddrs=['developers@myapp.com'],
        subject='Huey error log',
        credentials=('errors@myapp.com', 'secret_password'),
        secure=())
    mail_handler.setLevel(logging.ERROR)
    logging.getLogger('huey').addHandler(mail_handler)

.. _storage_options:

Storage Options
---------------

Huey provides a number of different storage layers suitable to different types
of workloads. Below I will try to sketch the differences, strengths, and
weaknesses of each storage layer.

:py:class:`RedisHuey`
    Huey's capabilities are, to a large extent, informed by the functionality
    available in Redis. This is the most robust option available and can handle
    very busy workloads. Because Redis runs as a separate server process, it is
    even possible to run Huey consumers on multiple machines to facilitate
    "scale-out" operation.

    Operations are guaranteed to be atomic, following the guarantees provided
    by Redis. The queue is stored in a Redis list, scheduled tasks use a sorted
    set, and the task result-store is kept in a hash.

    Tasks that return a meaningful value must be sure that the caller
    "resolves" those return values at some point, to ensure that the result
    store does not become filled with unused data (to mitigate this, you can
    just modify your tasks to return ``None`` if you never intend to use the
    result).

    By default Huey performs a "blocking" pop on the queue, which reduces
    latency, although polling can be used instead by passing ``blocking=False``
    when instantiating ``RedisHuey``.

    Task priorities are not supported by :py:class:`RedisHuey`.

:py:class:`PriorityRedisHuey`
    Redis storage layer that supports task priorities. In order to make this
    possible and efficient, ``PriorityRedisHuey`` stores the queue in a sorted
    set. Since sorted sets require the key to be unique, Huey will use the
    timestamp in microseconds to differentiate tasks enqueued with the same
    priority.

:py:class:`RedisExpireHuey`
    Redis storage layer that stores task results in top-level keys, in order to
    add an expiration time to them. Putting an expiration on task result keys
    can ensure that the result-store does not fill up with unresolved result
    values. The default expire time is 86400 seconds, although this can be
    controlled by setting the ``expire_time`` parameter during instantiation.

:py:class:`PriorityRedisExpireHuey`
    Combines the behaviors of :py:class:`PriorityRedisHuey` to support task
    priorities, with the result-store expiration behavior of
    :py:class:`RedisExpireHuey`.

:py:class:`SqliteHuey`
    Sqlite works well for many workloads (see `Appropriate uses for Sqlite <https://www.sqlite.org/whentouse.html>`_),
    and Huey's Sqlite storage layer works well regardless of the worker-type
    chosen. Sqlite locks the database during writes, ensuring only a single
    writer can write to the database at any given time. Writes generally happen
    very quickly, however, so in practice this is rarely an issue. Because the
    database is stored in a single file, taking backups is quite simple.

    ``SqliteHuey`` may be a good choice for moderate workloads where the
    operational complexity of running a separate server process like Redis is
    undesirable.

:py:class:`FileHuey`
    Stores the queue, schedule and task results in files on the filesystem.
    This implementation is provided mostly for testing and development. An
    exclusive lock is used around all file-system operations, since multiple
    operations (list directory, read file, unlink file, e.g.) are typically
    required for each storage primitive (enqueue, dequeue, store result, etc).

:py:class:`MemoryHuey`
    In-memory implementation of the storage layer used for :ref:`immediate`.

:py:class:`BlackHoleHuey`
    All storage methods are no-ops.

Testing Guidelines
------------------

When testing Huey task-decorated functions, a couple guidelines will make your
life easier.

1. Set your :py:class:`Huey` instance to :ref:`immediate`. Any code that calls
   a task will run it synchronously, so it is safe to block on results as well.
2. Unit test individual tasks by using the ``.call_local()`` to call the
   underlying function.

Examples:

.. code-block:: python

    # Consider the following Huey instance and tasks:
    huey = RedisHuey(...)

    # Fake database to check side-effects.
    database = []

    @huey.task()
    def add(a, b):
        return a + b

    @huey.periodic_task(crontab(...))
    def run_reports():
        global database
        database.append(True)  # Simulate a side-effect.

        # The return values for periodic tasks are discarded when run by the
        # Huey consumer. A return value may be helpful for testing, however, so
        # in this example we will return something to demonstrate how to test
        # our periodic task.
        return 42

    class TestMyTasks(unittest.TestCase):
        def setUp(self):
            # Make tasks run synchronously.
            huey.immediate = True

        def tearDown(self):
            huey.immediate = False

        def test_task(self):
            result_handle = add(3, 4)
            self.assertEqual(result_handle.get(), 7)

            # Alternatively, you can also:
            self.assertEqual(add.call_local(3, 4), 7)

        def test_task_exceptions(self):
            # We can also test exceptions.
            result_handle = add(3, None)  # Exception logged, but not raised.

            with self.assertRaises(TaskException):
                result_handle.get()

            with self.assertRaises(TypeError):
                # Exception raised directly when using call_local().
                add.call_local(3, None)

        def test_periodic_task(self):
            # We cannot use the result-handle from a periodic task, because the
            # results are always discarded by the consumer. In this case it is
            # necessary to use `.call_local()` if we want to check the return
            # value.
            self.assertEqual(run_reports.call_local(), 42)
            self.assertTrue(len(database), 1)

            # If our periodic task has a side-effect, however, we can call it
            # normally and check the side-effect happened. For example, if the
            # run_reports() periodic task wrote a row to a database, we could
            # do something like:
            run_reports()
            self.assertTrue(len(database), 2)

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

Exponential Backoff Retries
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Huey tasks support specifying a number of ``retries`` and a ``retry_delay``,
but does not support exponential backoff out-of-the-box. That's not a problem,
as we can use a couple decorators to implement it ourselves quite easily:

.. code-block:: python

    import functools

    def exp_backoff_task(retries=10, retry_backoff=1.15):
        def deco(fn):
            @functools.wraps(fn)
            def inner(*args, **kwargs):
                # We will register this task with `context=True`, which causes
                # Huey to pass the task instance as a keyword argument to the
                # decorated task function. This enables us to modify its retry
                # delay, multiplying it by our backoff factor, in the event of
                # an exception.
                task = kwargs.pop('task')
                try:
                    return fn(*args, **kwargs)
                except Exception as exc:
                    task.retry_delay *= retry_backoff
                    raise exc

            # Register our wrapped task (inner()), which handles delegating to
            # our function, and in the event of an unhandled exception,
            # increases the retry delay by the given factor.
            return huey.task(retries=retries, retry_delay=1, context=True)(inner)
        return deco

Example usage:

.. code-block:: python

    @exp_backoff_task(retries=5, retry_backoff=2)
    def test_backoff(message):
        print('test_backoff called:', message)
        raise ValueError('forcing retry')

If the consumer started executing our task at 12:00:00, then it would be
retried at the following times:

* 12:00:00 (first call)
* 12:00:02 (retry 1)
* 12:00:06 (retry 2)
* 12:00:14 (retry 3)
* 12:00:30 (retry 4)
* 12:01:02 (retry 5)

Dynamic periodic tasks
^^^^^^^^^^^^^^^^^^^^^^

To create periodic tasks dynamically we need to register them so that they are
added to the in-memory schedule managed by the consumer's scheduler thread.
Since this registry is in-memory, any dynamically defined tasks must be
registered within the process that will ultimately schedule them: the consumer.

.. warning::
    The following example will not work with the **process** worker-type
    option, since there is currently no way to interact with the scheduler
    process. When threads or greenlets are used, the worker threads share the
    same in-memory schedule as the scheduler thread, allowing modification to
    take place.

Example:

.. code-block:: python

    def dynamic_ptask(message):
        print('dynamically-created periodic task: "%s"' % message)

    @huey.task()
    def schedule_message(message, cron_minutes, cron_hours='*'):
        # Create a new function that represents the application
        # of the "dynamic_ptask" with the provided message.
        def wrapper():
            dynamic_ptask(message)

        # The schedule that was specified for this task.
        schedule = crontab(cron_minutes, cron_hours)

        # Need to provide a unique name for the task. There are any number of
        # ways you can do this -- based on the arguments, etc. -- but for our
        # example we'll just use the time at which it was declared.
        task_name = 'dynamic_ptask_%s' % int(time.time())

        huey.periodic_task(schedule, name=task_name)(wrapper)

Assuming the consumer is running, we can now set up as many instances as we
like of the "dynamic ptask" function:

.. code-block:: pycon

    >>> from demo import schedule_message
    >>> schedule_message('I run every 5 minutes', '*/5')
    <Result: task ...>
    >>> schedule_message('I run between 0-15 and 30-45', '0-15,30-45')
    <Result: task ...>

When the consumer executes the "schedule_message" tasks, our new periodic task
will be registered and added to the schedule.

Run Arbitrary Functions as Tasks
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Instead of explicitly needing to declare all of your tasks up-front, you can
write a special task that accepts a dotted-path to a callable and run anything
inside of huey (provided it is available wherever the consumer is running):

.. code-block:: python

    from importlib import import_module

    @huey.task()
    def path_task(path, *args, **kwargs):
        path, name = path.rsplit('.', 1)  # e.g. path.to.module.function
        mod = import_module(path)  # Dynamically import the module.
        return getattr(mod, name)(*args, **kwargs)  # Call the function.

    # Example usage might be:
    # foo.py
    def add_these(a, b):
        return a + b

    # Somewhere else, we can tell the consumer to use the "path_task" to import
    # the foo module and call "add_these(1, 2)", storing the result in the
    # result-store like any other task.
    path_task('foo.add_these', 1, 2)

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
