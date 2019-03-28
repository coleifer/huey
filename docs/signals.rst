.. _signals:

Signals
=======

The consumer will send various signals as it processes tasks. Callbacks can be
registered as signal handlers, and will be called synchronously by the consumer
process.

The following signals are implemented by Huey:

* ``SIGNAL_CANCELED``: task was canceled due to a pre-execute hook raising
  a :py:class:`CancelExecution` exception.
* ``SIGNAL_COMPLETE``: task has been executed successfully.
* ``SIGNAL_ERROR``: task failed due to an unhandled exception.
* ``SIGNAL_EXECUTING``: task is about to be executed.
* ``SIGNAL_LOCKED``: failed to acquire lock, aborting task.
* ``SIGNAL_RETRYING``: task failed, but will be retried.
* ``SIGNAL_REVOKED``: task is revoked and will not be executed.
* ``SIGNAL_SCHEDULED``: task is not yet ready to run and has been added to the
  schedule for future execution.

When a signal handler is called, it will be called with the following
arguments:

* ``signal``: the signal name, e.g. ``'executing'``.
* ``task``: the :py:class:`Task` instance.

The following signals will include additional arguments:

* ``SIGNAL_ERROR``: includes a third argument ``exc``, which is the
  ``Exception`` that was raised while executing the task.

To register a signal handler, use the :py:meth:`Huey.signal` method:

.. code-block:: python

    @huey.signal()
    def all_signal_handler(signal, task, exc=None):
        # This handler will be called for every signal.
        print('%s - %s' % (signal, task.id))

    @huey.signal(SIGNAL_ERROR, SIGNAL_LOCKED, SIGNAL_CANCELED, SIGNAL_REVOKED)
    def task_not_executed_handler(signal, task, exc=None):
        # This handler will be called for the 4 signals listed, which
        # correspond to error conditions.
        print('[%s] %s - not executed' % (signal, task.id))

    @huey.signal(SIGNAL_COMPLETE)
    def task_success(signal, task):
        # This handle will be called for each task that completes successfully.
        pass

Signal handlers can be unregistered using :py:meth:`Huey.disconnect_signal`.

.. code-block:: python

    # Disconnect the "task_success" signal handler.
    huey.disconnect_signal(task_success)

    # Disconnect the "task_not_executed_handler", but just from
    # handling SIGNAL_LOCKED.
    huey.disconnect_signal(task_not_executed_handler, SIGNAL_LOCKED)

Examples
^^^^^^^^

We'll use the following tasks to illustrate how signals may be sent:

.. code-block:: python

    @huey.task()
    def add(a, b):
        return a + b

    @huey.task(retries=2, retry_delay=10)
    def flaky_task():
        if random.randint(0, 1) == 0:
            raise ValueError('uh-oh')
        return 'OK'

Here is a simple example of a task execution we would expect to succeed:

.. code-block:: pycon

    >>> result = add(1, 2)
    >>> result.get(blocking=True)

The consumer would send the following signals:

* ``SIGNAL_EXECUTING`` - the task has been dequeued and will be executed.
* ``SIGNAL_COMPLETE`` - the task has finished successfully.

Here is an example of scheduling a task for execution after a short delay:

.. code-block:: pycon

    >>> result = add.schedule((2, 3), delay=10)
    >>> result(True)  # same as result.get(blocking=True)

The following signals would be sent:

* ``SIGNAL_SCHEDULED`` - the task is not yet ready to run, so it has been added
  to the schedule.
* After 10 seconds, the consumer will run the task and send
  the ``SIGNAL_EXECUTING`` signal.
* ``SIGNAL_COMPLETE``.

Here is an example that may fail, in which case it will be retried
automatically with a delay of 10 seconds.

.. code-block:: pycon

    >>> result = flaky_task()
    >>> try:
    ...     result.get(blocking=True)
    ... except TaskException:
    ...     result.reset()
    ...     result.get(blocking=True)  # Try again if first time fails.
    ...

Assuming the task failed the first time and succeeded the second time, we would
see the following signals being sent:

* ``SIGNAL_EXECUTING`` - the task is being executed.
* ``SIGNAL_ERROR`` - the task raised an unhandled exception.
* ``SIGNAL_RETRYING`` - the task will be retried.
* ``SIGNAL_SCHEDULED`` - the task has been added to the schedule for execution
  in ~10 seconds.
* ``SIGNAL_EXECUTING`` - second try running task.
* ``SIGNAL_COMPLETE`` - task succeeded.

What happens if we revoke the ``add()`` task and then attempt to execute it:

.. code-block:: pycon

    >>> add.revoke()
    >>> res = add(1, 2)

The following signal will be sent:

* ``SIGNAL_REVOKED`` - this is sent before the task enters the "executing"
  state. When a task is revoked, no other signals will be sent.

Performance considerations
--------------------------

Signal handlers are executed **synchronously** by the consumer as it processes
tasks. It is important to use care when implementing signal handlers, as one
slow signal handler can impact the overall responsiveness of the consumer.

For example, if you implement a signal handler that posts some data to REST
API, everything might work fine until the REST API goes down or stops being
responsive -- which will cause the signal handler to block, which then prevents
the consumer from moving on to the next task.

Another consideration is the :ref:`management of shared resources <shared_resources>`
that may be used by signal handlers, such as database connections or open file
handles. Signal handlers are called by the consumer workers, which (depending
on how you are running the consumer) may be separate processes, threads or
greenlets. As a result, care should be taken to ensure proper initialization
and cleanup of any resources you plan to use in signal handlers.
