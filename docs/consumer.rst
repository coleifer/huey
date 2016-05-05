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

.. warning::
    If you plan to use `supervisord <http://supervisord.org/>`_ to manage your consumer process, be sure that you are running the consumer directly and without any intermediary shell scripts. Shell script wrappers interfere with supervisor's ability to terminate and restart the consumer Python process. For discussion see `GitHub issue 88 <https://github.com/coleifer/huey/issues/88>`_.

Options for the consumer
------------------------

The following table lists the options available for the consumer as well as
their default values.

``-l``, ``--logfile``
    Path to file used for logging.  When a file is specified, by default Huey
    the logfile will grow indefinitely, so you may wish to configure a tool
    like ``logrotate``.

    Alternatively, you can attach your own handler to ``huey.logger`` as well.

    The default loglevel is ``INFO``.

``-v``, ``--verbose``
    Verbose logging (loglevel=``DEBUG``). If no logfile is specified and
    verbose is set, then the consumer will log to the console.

``-q``, ``--quiet``
    Only log errors.

``-w``, ``--workers``
    Number of worker threads/processes/greenlets, the default is ``1`` but
    some applications may want to increase this number for greater throughput.

``-k``, ``--worker-type``
    Choose the worker type, ``thread``, ``process`` or ``greenlet``. The default
    is ``thread``.

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

``-s``, ``--scheduler-interval``
    The frequency with which the scheduler should run. By default this will run
    every second, but you can increase the interval to as much as 60 seconds.

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

  huey_consumer.py my.app.huey -l /var/log/app.huey.log -w 8 -b 1.1 -m 1.0

Running single-threaded without a crontab and logging to stdout:

.. code-block:: bash

    huey_consumer.py my.app.huey -v -n

Using multi-processing to run 4 worker processes:

.. code-block:: bash

    huey_consumer.py my.app.huey -w 4 -k process


Consumer Internals
------------------

The consumer is composed of a master process, the scheduler, and the worker(s).
Depending on the worker type chosen, the scheduler and workers will be run in
their threads, processes or greenlets.

These components coordinate the receipt, execution and scheduling of various
tasks.  What happens when you call a decorated function in your application?

1. You call a function -- huey has decorated it, which triggers a message being
   put into the queue.  At this point your application returns.  If you are using
   a "data store", then you will be return an :py:class:`TaskResultWrapper` object.
2. In a separate process, a worker will be listening for new messages --
   one of the workers will pull down the message.
3. The worker looks at the message and checks to see if it can be
   run (i.e., was this message "revoked"?  Is it scheduled to actually run
   later?).  If it is revoked, the message is thrown out.  If it is scheduled
   to run later, it gets added to the schedule.  Otherwise, it is executed.
4. The worker thread executes the task.  If the task finishes, any results are
   published to the result store (if one is configured).  If the task fails and
   can be retried, it is either enqueued or added to the schedule (which happens
   if a delay is specified between retries).

While all this is going on, the Scheduler is looking at its schedule to see
if any tasks are ready to be executed.  If a task is ready to run, it is
enqueued and will be processed by a worker.

If you are using the Periodic Task feature (cron), then every minute, the
scheduler will check through the various periodic tasks to see if any should
be run. If so, these tasks are enqueued.

When the consumer is shut-down cleanly (SIGTERM), any workers still involved in the execution of a task will complete their work.

Events
------

As the consumer processes tasks, it can be configured to emit events. For information on consumer-sent events, check out the :ref:`events` documentation.
