.. _events:

Consumer Events
---------------

If you specify a :py:class:`RedisEventEmitter` when setting up your :py:class:`Huey` instance (or if you choose to use :py:class:`RedisHuey`), the consumer will publish real-time events about the status of various tasks.  You can subscribe to these events in your own application.

When an event is emitted, the following information is provided (serialized as JSON):

* ``status``: a String indicating what type of event this is.
* ``id``: the UUID of the task.
* ``task``: a user-friendly name indicating what type of task this is.
* ``retries``: how many retries the task has remaining.
* ``retry_delay``: how long to sleep before retrying the task in event of failure.
* ``execute_time``: A unix timestamp indicating when the task is scheduled to
    execute (this may be ``None``).
* ``error``: A boolean value indicating if there was an error.
* ``traceback``: A string traceback of the error, if one occurred.

The following events are emitted by the consumer:

* ``scheduled``: sent when a task is added to the schedule for execution in the future. For instance the worker pops off a task, sees that it should be run in an hour, and therefore schedules it.
* ``enqueued``: sent when a task is enqueued, i.e., it is pulled off the schedule.
* ``revoked``: sent when a task is not executed because it has been revoked.
* ``started``: sent when a worker begins executing a task.
* ``finished``: sent when a worker finishes executing a task and has stored the result.
* ``error``: sent when an exception occurs while executing a task.
* ``retrying``: sent when task that failed will be retried.

Listening to events
-------------------

The easiest way to listen for events is by iterating over the ``huey.events`` object.

.. code-block:: python

    for event in huey.events:
        # Do something with the event object.
        process_event(event)

You can also achieve the same result with a simple loop like this:

.. code-block:: python

    pubsub = huey.events.listener()
    for message in pubsub.listen():
        event = message['data']  # Actual event data is stored in 'data' key.
        # Do something with `event` object.
        process_event(event)

Ordering of events
------------------

So, for the execution of a simple task, the events emitted would be:

* ``started``
* ``finished``

If a task was scheduled to be executed in the future, the events would be:

* ``scheduled``
* ``enqueued``
* ``started``
* ``finished``

If an error occurs and the task is configured to be retried, the events would be:

* ``started``
* ``error`` (includes traceback)
* ``retrying``
* ``scheduled`` (if there is a retry delay, it will go onto the schedule)
* ``enqueued`` (pulled off schedule and sent to a worker)
* ``started``
* ``finished`` (or error if the task fails again)
