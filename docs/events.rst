.. _events:

Consumer Events
---------------

If you specify a :py:class:`RedisEventEmitter` when setting up your :py:class:`Huey` instance (or if you choose to use :py:class:`RedisHuey`), the consumer will publish real-time events about the status of various tasks.  You can subscribe to these events in your own application.

When an event is emitted, the following information is always provided:

* ``status``: a String indicating what type of event this is.
* ``id``: the UUID of the task.
* ``task``: a user-friendly name indicating what type of task this is.
* ``retries``: how many retries the task has remaining.
* ``retry_delay``: how long to sleep before retrying the task in event of failure.
* ``execute_time``: A unix timestamp indicating when the task is scheduled to
    execute (this may be ``None``).

If an error occurred, then the following data is also provided:

* ``error``: A boolean value indicating if there was an error.
* ``traceback``: A string traceback of the error, if one occurred.

When an event includes other keys, those will be noted below.

The following events are emitted by the consumer. I've listed the event name, and in parentheses the process that emits the event and any non-standard metadata it includes.

* ``EVENT_CHECKING_PERIODIC`` (Scheduler, ``timestamp``): emitted every minute when the scheduler checks for periodic tasks to execute.
* ``EVENT_FINISHED`` (Worker, ``duration``): emitted when a task executes successfully and cleanly returns.
* ``EVENT_RETRYING`` (Worker): emitted after a task failure, when the task will be retried.
* ``EVENT_REVOKED`` (Worker, ``timestamp``): emitted when a task is pulled from the queue but is not executed due to having been revoked.
* ``EVENT_SCHEDULED`` (Worker): emitted when a task specifies a delay or ETA and is not yet ready to run. This can also occur when a task is being retried and specifies a retry delay. The task is added to the schedule for later execution.
* ``EVENT_SCHEDULING_PERIODIC`` (Schedule, ``timestamp``): emitted when a periodic task is scheduled for execution.
* ``EVENT_STARTED`` (Worker, ``timestamp``): emitted when a worker begins executing a task.

Error events:

* ``EVENT_ERROR_DEQUEUEING`` (Worker): emitted if an error occurs reading from the backend queue.
* ``EVENT_ERROR_ENQUEUEING`` (Schedule, Worker): emitted if an error occurs enqueueing a task for execution. This can occur when the scheduler attempts to enqueue a task that had been delayed, or when a worker attempts to retry a task after an error.
* ``EVENT_ERROR_INTERNAL`` (Worker): emitted if an unspecified error occurs. An example might be the Redis server being offline.
* ``EVENT_ERROR_SCHEDULING`` (Worker): emitted when an exception occurs enqueueing a task.
* ``EVENT_ERROR_STORING_RESULT`` (Worker, ``duration``): emitted when an exception occurs attempting to store the result of a task. In this case the task ran to completion, but the result could not be stored.
* ``EVENT_ERROR_TASK`` (Worker, ``duration``): emitted when an unspecified error occurs in the user's task code.

Listening to events
^^^^^^^^^^^^^^^^^^^

The easiest way to listen for events is by iterating over the ``huey.storage`` object.

.. code-block:: python

    from huey.consumer import EVENT_FINISHED

    for event in huey.storage:
        # Do something with the result of the task.
        if event['status'] == EVENT_FINISHED:
            result = huey.result(event['id'])
            process_result(event, result)

You can also achieve the same result with a simple loop like this:

.. code-block:: python

    pubsub = huey.storage.listener()
    for message in pubsub.listen():
        event = message['data']  # Actual event data is stored in 'data' key.
        # Do something with `event` object.
        process_event(event)

Ordering of events
^^^^^^^^^^^^^^^^^^

For the execution of a simple task, the events emitted would be:

* ``EVENT_STARTED``
* ``EVENT_FINISHED``

If a task was scheduled to be executed in the future, the events would be:

* ``EVENT_SCHEDULED``
* ``EVENT_STARTED``
* ``EVENT_FINISHED``

If an error occurs and the task is configured to be retried, the events would be:

* ``EVENT_STARTED``
* ``EVENT_ERROR_TASK`` (includes traceback)
* ``EVENT_RETRYING``
* ``EVENT_SCHEDULED`` (if there is a retry delay, it will go onto the schedule)
* ``EVENT_STARTED``
* ``EVENT_FINISHED`` if task succeeds, otherwise go back to ``EVENT_ERROR_TASK``.
