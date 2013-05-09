.. _consuming-tasks:

Consuming Tasks
===============

To run the consumer, simply point it at the "import path" to your application's
:py:class:`Huey` instance.  For example, here is how I run it on my blog:

.. code-block:: bash

    huey_consumer.py blog.main.huey --logfile=../logs/huey.log

The concept of the "import path" has been the source of a few questions, but its
actually quite simple.  It is simply the dotted-path you might use if you were
to try and import the "huey" object in the interactive interpreter:

.. code-block:: pycon

    >>> from blog.main import huey

You may run into trouble though when "blog" is not on your python-path. To
work around this:

1. Manually specify your pythonpath: ``PYTHONPATH=/some/dir/:$PYTHONPATH huey_consumer.py blog.main.huey``.
2. Run ``huey_consumer.py`` from the directory your config module is in.  I use
   supervisord to manage my huey process, so I set the ``directory`` to the root
   of my site.
3. Create a wrapper and hack ``sys.path``.

Options for the consumer
------------------------

The following table lists the options available for the consumer as well as
their default values.

``-l``, ``--logfile``
    Path to file used for logging.  When a file is specified, by default Huey
    will use a rotating file handler (1MB / chunk) with a maximum of 3 backups.
    You can attach your own handler (``huey.logger``) as well.  The default
    loglevel is ``INFO``.

``-v``, ``--verbose``
    Verbose logging (equates to ``DEBUG`` level).  If no logfile is specified
    and verbose is set, then the consumer will log to the console.  **This is
    very useful for testing/debugging.**

 ``-q``, ``--quiet``
    Only log errors. The default loglevel for the consumer is ``INFO``.

``-t``, ``--threads``
    Number of worker threads, the default is ``1`` thread but for applications
    that have many I/O bound tasks, increasing this number may lead to greater
    throughput.

``-p``, ``--periodic``
    Indicate that this consumer process should start a thread dedicated to
    enqueueing "periodic" tasks (crontab-like functionality).  This defaults
    to ``True``, so should not need to be specified in practice.

``-n``, ``--no-periodic``
    Indicate that this consumer process should *not* enqueue periodic tasks.

``-d``, ``--delay``
    When using a "polling"-type queue backend, the amount of time to wait
    between polling the backend.  Default is 0.1 seconds.

``-m``, ``--max-delay``
    The maximum amount of time to wait between polling, if using weighted
    backoff.  Default is 10 seconds.

``-b``, ``--backoff``
    The amount to back-off when polling for results.  Must be greater than
    one.  Default is 1.15.

``-u``, ``--utc``
    Indicates that the consumer should use UTC time for all tasks, crontabs
    and scheduling.  Default is True, so in practice you should not need to
    specify this option.

``--localtime``
    Indicates that the consumer should use localtime for all tasks, crontabs
    and scheduling.  Default is False.

Examples
^^^^^^^^

 Running the consumer with 8 threads, a logfile for errors only, and a very
 short polling interval:

 .. code-block:: bash

    huey_consumer.py my.app.huey -l /var/log/app.huey.log -t 8 -b 1.1 -m 1.0

Running single-threaded without a crontab and logging to stdout:

.. code-block:: bash

    huey_consumer.py my.app.huey -v -n


Consumer Internals
------------------

The consumer is composed of 4 main threads:

* Message receiver
* Executor
* Scheduler
* Periodic task scheduler (optional)

These threads coordinate the receipt, execution and scheduling of various
tasks.  What happens when you call a decorated function in your application?

1. You call a function -- huey has decorated it, which triggers a message being
   put into the queue.  At this point your application returns.  If you are using
   a "data store", then you will be return an :py:class:`AsyncData` object.
2. In a separate process, the consumer will be listening for new messages --
   this is the Message Receiver thread.  If your backend supports blocking, it
   will block until a new message is available, otherwise it will poll.  When
   it gets your message it waits until there is a free worker available and
   then sends the message to the Executor thread.
3. The executor thread looks at the message and checks to see if it can be
   run (i.e., was this message "revoked"?  Is it scheduled to actually run
   later?).  If it is revoked, the message is thrown out.  If it is scheduled
   to run later, it gets added to the schedule.  Otherwise, it is passed to
   a Worker thread.
4. The worker thread executes the task.  If the task finishes, any results are
   published to the result store (if one is configured).  If the task fails and
   can be retried, it is either enqueued or added to the schedule (which happens
   if a delay is specified between retries).

While all this is going on, the Scheduler thread is continually looking at
its schedule to see if any commands are ready to be executed.  If a command
is ready to run, it is enqueued and will be processed by the Message receiver
thread.

Similarly, the Periodic task thread will run every minute to see if there are
any regularly-scheduled tasks to run at that time.  Those tasks will be enqueued
and processed by the Message receiver thread.

When the consumer is shut-down (SIGTERM) it will save the schedule and finish
any jobs that are currently being worked on.
