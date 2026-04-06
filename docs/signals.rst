.. _signals:

Signals
=======

The consumer will send various signals as it processes tasks. Callbacks can be
registered as signal handlers, and will be called synchronously by the consumer
process.

Signal Reference
----------------

The following table lists all signals, when they are emitted, and any extra
arguments passed to the handler beyond the standard ``(signal, task)`` pair.

.. list-table::
   :header-rows: 1
   :widths: 25 50 25

   * - Signal
     - When emitted
     - Extra arguments
   * - ``SIGNAL_ENQUEUED``
     - Task has been placed on the queue. Emitted in both the **application
       process** (when your code calls a task) and the **consumer** (when
       re-enqueueing retries, periodic tasks, or scheduled tasks).
     - None
   * - ``SIGNAL_EXECUTING``
     - Task is about to be executed by a worker.
     - None
   * - ``SIGNAL_COMPLETE``
     - Task has finished executing successfully and the result has been stored
       in the result-store.
     - None
   * - ``SIGNAL_ERROR``
     - Task raised an unhandled exception during execution.
     - ``exc`` -- the exception instance.
   * - ``SIGNAL_CANCELED``
     - Task was canceled, either by a :py:meth:`~Huey.pre_execute` hook
       raising :py:class:`CancelExecution`, or by the task function itself
       raising ``CancelExecution``.
     - None
   * - ``SIGNAL_RETRYING``
     - Task failed but will be retried (retries remaining, or
       :py:class:`RetryTask` was raised).
     - None
   * - ``SIGNAL_SCHEDULED``
     - Task is not yet ready to run and has been added to the schedule for
       future execution (e.g., has an ``eta`` or ``retry_delay``).
     - None
   * - ``SIGNAL_REVOKED``
     - Task was revoked and will not be executed. No further signals are
       emitted for this task.
     - None
   * - ``SIGNAL_EXPIRED``
     - Task's expiration time has passed; it will not be executed.
     - None
   * - ``SIGNAL_LOCKED``
     - Task could not acquire its lock (:py:meth:`Huey.lock_task`). The
       task will not be executed.
     - None
   * - ``SIGNAL_TIMEOUT``
     - Task exceeded its execution timeout.
     - None
   * - ``SIGNAL_RATE_LIMITED``
     - Task was rate-limited by a :py:meth:`Huey.rate_limit`.
     - None
   * - ``SIGNAL_INTERRUPTED``
     - Consumer was shut down while the task was still executing (e.g., via
       ``SIGTERM``).
     - None

Signal Ordering
---------------

Signals are emitted in a deterministic order. Understanding this order is
important when writing signal handlers that depend on the state of the task or
the result store.

**Successful task execution:**

1. ``SIGNAL_ENQUEUED`` -- task placed on the queue (in the **application** process).
2. ``SIGNAL_EXECUTING`` -- worker picks up the task.
3. ``SIGNAL_COMPLETE`` -- task finished. The result is in the result store.
4. If the task has an ``on_complete`` pipeline, the next task is enqueued
   (emitting another ``SIGNAL_ENQUEUED``).

**Task failure with retry:**

1. ``SIGNAL_ENQUEUED``
2. ``SIGNAL_EXECUTING``
3. ``SIGNAL_ERROR`` -- exception is passed as ``exc``. The error result is
   stored at this point.
4. ``SIGNAL_RETRYING`` -- task will be retried.
5. If ``retry_delay`` is set: ``SIGNAL_SCHEDULED`` (task added to the schedule
   for later). Otherwise: ``SIGNAL_ENQUEUED`` (task re-added to the queue
   immediately).

**Task failure without retry (retries exhausted or not configured):**

1. ``SIGNAL_ENQUEUED``
2. ``SIGNAL_EXECUTING``
3. ``SIGNAL_ERROR``

**Scheduled task:**

1. ``SIGNAL_ENQUEUED`` -- task placed on the queue (application process).
2. ``SIGNAL_SCHEDULED`` -- worker sees the task is not ready to run, adds it
   to the schedule.
3. When the scheduler determines the task is ready: ``SIGNAL_ENQUEUED``
   (in the **consumer** process).
4. ``SIGNAL_EXECUTING``
5. ``SIGNAL_COMPLETE`` (or ``SIGNAL_ERROR``, etc.)

**Revoked task:**

1. ``SIGNAL_ENQUEUED``
2. ``SIGNAL_REVOKED`` -- no further signals are emitted.

**Rate-limited task (with automatic retry):**

1. ``SIGNAL_ENQUEUED``
2. ``SIGNAL_EXECUTING``
3. ``SIGNAL_RATE_LIMITED``
4. ``SIGNAL_RETRYING``
5. ``SIGNAL_SCHEDULED`` -- task is scheduled for the start of the next
   rate-limit window.

**Chord signals:**

When a chord is enqueued, each sub-task emits its own ``SIGNAL_ENQUEUED``.
As sub-tasks complete, they emit ``SIGNAL_COMPLETE`` (or ``SIGNAL_ERROR``).
When the last sub-task finishes, the callback is enqueued
(``SIGNAL_ENQUEUED``), then executed (``SIGNAL_EXECUTING``, etc.).

Registering Signal Handlers
----------------------------

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
        # This handler will be called for each task that completes successfully.
        pass

When no signals are specified (as in ``all_signal_handler``), the handler is
registered for **all** signals via an internal ``"any"`` channel.

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

The following signals would be fired:

* ``SIGNAL_ENQUEUED`` - the task has been enqueued (happens in the application
  process).
* ``SIGNAL_EXECUTING`` - the task has been dequeued and will be executed.
* ``SIGNAL_COMPLETE`` - the task has finished successfully.

Here is an example of scheduling a task for execution after a short delay:

.. code-block:: pycon

    >>> result = add.schedule((2, 3), delay=10)
    >>> result(True)  # same as result.get(blocking=True)

The following signals would be sent:

* ``SIGNAL_ENQUEUED`` - the task has been enqueued (happens in the **application**
  process).
* ``SIGNAL_SCHEDULED`` - the task is not yet ready to run, so it has been added
  to the schedule.
* After 10 seconds, the consumer will re-enqueue the task as it is now ready to
  run, sending the ``SIGNAL_ENQUEUED`` (in the **consumer** process!).
* Then the consumer will run the task and send the ``SIGNAL_EXECUTING`` signal.
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

* ``SIGNAL_ENQUEUED`` - task has been enqueued.
* ``SIGNAL_EXECUTING`` - the task is being executed.
* ``SIGNAL_ERROR`` - the task raised an unhandled exception.
* ``SIGNAL_RETRYING`` - the task will be retried.
* ``SIGNAL_SCHEDULED`` - the task has been added to the schedule for execution
  in ~10 seconds.
* ``SIGNAL_ENQUEUED`` - 10s have elapsed and the task is ready to run and has
  been re-enqueued.
* ``SIGNAL_EXECUTING`` - second try running task.
* ``SIGNAL_COMPLETE`` - task succeeded.

What happens if we revoke the ``add()`` task and then attempt to execute it:

.. code-block:: pycon

    >>> add.revoke()
    >>> res = add(1, 2)

The following signal will be sent:

* ``SIGNAL_ENQUEUED`` - the task has been enqueued for execution.
* ``SIGNAL_REVOKED`` - this is sent before the task enters the "executing"
  state. When a task is revoked, no other signals will be sent.

Using SIGNAL_INTERRUPTED
^^^^^^^^^^^^^^^^^^^^^^^^

The correct way to shut-down the Huey consumer is to send a ``SIGINT`` signal
to the worker process (e.g. Ctrl+C) - this initiates a graceful shutdown.
Sometimes, however, you may need to shutdown the consumer using ``SIGTERM`` -
this immediately stops the consumer. Any tasks that are currently being
executed are then "lost" and will not be retried by default (see also:
:ref:`consumer-shutdown`).

To avoid losing these tasks, you can use a ``SIGNAL_INTERRUPTED`` handler to
re-enqueue them:

.. code-block:: python

    @huey.signal(SIGNAL_INTERRUPTED)
    def on_interrupted(signal, task, *args, **kwargs):
        # The consumer was shutdown before `task` finished executing.
        # Re-enqueue it.
        huey.enqueue(task)

Signal Handler Error Resilience
-------------------------------

If a signal handler raises an exception, Huey **logs the exception** but
continues processing. A broken signal handler will not prevent other signal
handlers from running, nor will it prevent the task from being executed or
its result from being stored.

.. code-block:: python

    @huey.signal(SIGNAL_COMPLETE)
    def broken_handler(signal, task):
        raise ValueError('oops')

    @huey.signal(SIGNAL_COMPLETE)
    def working_handler(signal, task):
        # This will still be called, even if broken_handler raised.
        record_completion(task.id)

Signals and Immediate Mode
--------------------------

Signals fire in :ref:`immediate mode <immediate>` as well as when running the
consumer. This makes it easy to test signal handlers:

.. code-block:: python

    huey.immediate = True

    state = []

    @huey.signal(SIGNAL_COMPLETE)
    def on_complete(signal, task):
        state.append(task.id)

    result = add(1, 2)  # Executes immediately, fires signals.
    assert len(state) == 1
    assert state[0] == result.id


Performance considerations
--------------------------

Signal handlers are executed **synchronously** by the consumer as it processes
tasks (with the exception of ``SIGNAL_ENQUEUED``, which also runs in your
application process). It is important to use care when implementing signal
handlers, as one slow signal handler can impact the overall responsiveness of
the consumer.

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

Lastly, take care when implementing ``SIGNAL_ENQUEUED`` handlers, as these may
run in your application-code (e.g. whenever your application enqueues a task),
**or** by the consumer process (e.g. when re-enqueueing a task for retry, or
when enqueueing periodic tasks, when moving a task from the schedule to the
queue, etc).
