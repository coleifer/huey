.. _signals:

Signals
=======

The consumer will send signals as it processes tasks. Callbacks can be
registered as signal handlers.

Signal Reference
----------------

The following table lists all signals and any extra arguments passed to the
handler beyond the standard ``(signal, task)`` pair.

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
     - ``exc``: the exception instance.
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
     - Task is not yet ready to run and has been added to the schedule
       (e.g., has an ``eta`` or ``retry_delay``).
     - None
   * - ``SIGNAL_REVOKED``
     - Task was revoked and will not be executed. No further signals are
       emitted for this task.
     - None
   * - ``SIGNAL_EXPIRED``
     - Task's expiration time has passed, so it will not be executed.
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

Signals are emitted in a deterministic order.

**Successful task execution:**

1. ``SIGNAL_ENQUEUED`` (in the **application** process).
2. ``SIGNAL_EXECUTING``
3. ``SIGNAL_COMPLETE``
4. If the task has an ``on_complete`` pipeline, the next task is enqueued
   (emitting another ``SIGNAL_ENQUEUED``).

**Task failure with retry:**

1. ``SIGNAL_ENQUEUED``
2. ``SIGNAL_EXECUTING``
3. ``SIGNAL_ERROR``: exception is passed as ``exc``. The error result is
   stored after this signal, unless ``store_intermediate_errors`` is false.
4. ``SIGNAL_RETRYING``
5. If ``retry_delay`` is set: ``SIGNAL_SCHEDULED``. Otherwise:
   ``SIGNAL_ENQUEUED``.

**Task failure without retry (retries exhausted or not configured):**

1. ``SIGNAL_ENQUEUED``
2. ``SIGNAL_EXECUTING``
3. ``SIGNAL_ERROR``

**Scheduled task:**

1. ``SIGNAL_ENQUEUED`` (application process).
2. ``SIGNAL_SCHEDULED``: worker sees the task is not ready to run, adds it
   to the schedule.
3. When the scheduler determines the task is ready: ``SIGNAL_ENQUEUED``
   (in the **consumer** process).
4. ``SIGNAL_EXECUTING``
5. ``SIGNAL_COMPLETE`` (or ``SIGNAL_ERROR``, etc.)

**Revoked task:**

1. ``SIGNAL_ENQUEUED``
2. ``SIGNAL_REVOKED``

**Rate-limited task (with automatic retry):**

1. ``SIGNAL_ENQUEUED``
2. ``SIGNAL_EXECUTING``
3. ``SIGNAL_RATE_LIMITED``
4. ``SIGNAL_RETRYING``
5. ``SIGNAL_SCHEDULED``: task is scheduled for the start of the next
   rate-limit window, or after ``retry_delay`` if the task sets one.

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

.. code-block:: python

    @huey.task()
    def add(a, b):
        return a + b

    @huey.task(retries=2, retry_delay=10)
    def flaky_task():
        if random.randint(0, 1) == 0:
            raise ValueError('uh-oh')
        return 'OK'

Here is an example of a task execution we would expect to succeed:

.. code-block:: pycon

    >>> result = add(1, 2)
    >>> result.get(blocking=True)

The following signals would be fired:

* ``SIGNAL_ENQUEUED``
* ``SIGNAL_EXECUTING``
* ``SIGNAL_COMPLETE``

Here is an example of scheduling a task for execution after a short delay:

.. code-block:: pycon

    >>> result = add.schedule((2, 3), delay=10)
    >>> result(True)  # same as result.get(blocking=True)

The following signals would be sent:

* ``SIGNAL_ENQUEUED`` (in the **application** process).
* ``SIGNAL_SCHEDULED``
* After 10 seconds, the consumer will re-enqueue the task, sending
  ``SIGNAL_ENQUEUED``.
* ``SIGNAL_EXECUTING``
* ``SIGNAL_COMPLETE``

Here is an example that may fail:

.. code-block:: pycon

    >>> result = flaky_task()
    >>> try:
    ...     result.get(blocking=True)
    ... except TaskException:
    ...     result.reset()
    ...     result.get(blocking=True)  # Try again if first time fails.
    ...

Assuming the task failed the first time and succeeded the second time, we would
see the following signals:

* ``SIGNAL_ENQUEUED``
* ``SIGNAL_EXECUTING``
* ``SIGNAL_ERROR``
* ``SIGNAL_RETRYING``
* ``SIGNAL_SCHEDULED``
* ``SIGNAL_ENQUEUED``
* ``SIGNAL_EXECUTING``
* ``SIGNAL_COMPLETE``

What happens if we revoke the ``add()`` task and then attempt to execute it:

.. code-block:: pycon

    >>> add.revoke()
    >>> res = add(1, 2)

The following signal will be sent:

* ``SIGNAL_ENQUEUED``
* ``SIGNAL_REVOKED``

Using SIGNAL_INTERRUPTED
^^^^^^^^^^^^^^^^^^^^^^^^

Shutting the consumer down using ``SIGTERM`` stops it immediately (unless the
consumer runs with ``--graceful-signal=TERM``). Any tasks that are currently
being executed are then "lost" and will not be retried by default (see
:ref:`consumer-shutdown`).

To avoid losing these tasks, you can use a ``SIGNAL_INTERRUPTED`` handler to
re-enqueue them:

.. code-block:: python

    @huey.signal(SIGNAL_INTERRUPTED)
    def on_interrupted(signal, task, *args, **kwargs):
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

    result = add(1, 2)
    assert len(state) == 1
    assert state[0] == result.id


Performance considerations
--------------------------

Signal handlers are executed **synchronously** by the consumer as it processes
tasks (with the exception of ``SIGNAL_ENQUEUED``, which also runs in your
application process). Take care when implementing them, as one slow handler
can impact the overall responsiveness of the consumer.

For example, if you implement a signal handler that posts data to a REST
API, everything might work fine until the REST API goes down or stops being
responsive, which will cause the signal handler to block, which then prevents
the consumer from moving on to the next task.

Another consideration is the :ref:`management of shared resources <shared_resources>`
that may be used by signal handlers, such as database connections or open file
handles. Signal handlers are called by the consumer workers, which (depending
on how you are running the consumer) may be separate processes, threads or
greenlets.
