.. _consuming-tasks:

Consuming Tasks
===============

To run the consumer, point it at the "import path" to your application's
:py:class:`Huey` instance. For example:

.. code-block:: shell

    huey_consumer blog.main.huey --logfile=../logs/huey.log

The "import path" is the dotted-path you would use to import the "huey" object
in the interactive interpreter:

.. code-block:: pycon

    >>> from blog.main import huey

You may run into trouble though when "blog" is not on your python-path. To
work around this:

1. Manually specify your pythonpath: ``PYTHONPATH=/some/dir/:$PYTHONPATH huey_consumer blog.main.huey``.
2. Run the consumer from the directory your config module is in. I use
   supervisord to manage my huey process, so I set the ``directory`` to the
   root of my site.
3. Create a wrapper and hack ``sys.path``.

.. warning::
    If you plan to use `supervisord <https://supervisord.org/>`_ to manage your
    consumer process, be sure that you are running the consumer directly and
    without any intermediary shell scripts. Shell script wrappers interfere
    with supervisor's ability to terminate and restart the consumer Python
    process. For discussion see `GitHub issue 88 <https://github.com/coleifer/huey/issues/88>`_.

.. _consumer-options:

Options for the consumer
------------------------

``-l``, ``--logfile``
    Path to file used for logging. Without it, the consumer logs to stderr.
    The logfile grows indefinitely, so you may wish to configure a tool like
    ``logrotate``.

    Alternatively, you can attach your own handler to the ``huey`` logger.

    The default loglevel is ``INFO``.

``-v``, ``--verbose``
    Verbose logging (loglevel=DEBUG).

    **Note:** due to conflicts, when using Django this option is renamed to
    use ``-V``, ``--huey-verbose``.

``-q``, ``--quiet``
    Minimal logging (loglevel=WARNING).

``-S``, ``--simple``
    Use a simple log format consisting only of the time H:M:S and log message.

``-w``, ``--workers``
    Number of worker threads/processes/greenlets. The default is ``1``, but
    most applications will want at least 2, so a slow task cannot tie up the
    only worker. For CPU-bound workloads, scale toward the number of CPU cores.
    With the ``greenlet`` worker type you can run hundreds of workers, but when
    using Redis, size the connection pool to match.

``-k``, ``--worker-type``
    Choose the worker type, ``thread``, ``process`` or ``greenlet``. The
    default is ``thread``.

    Depending on your workload, one worker type may perform better than the
    others:

    * CPU heavy loads: use "process". Python's global interpreter lock prevents
      multiple threads from running simultaneously, so to leverage multiple CPU
      cores (and reduce thread contention) run each worker as a separate
      process.
    * IO heavy loads: use "greenlet". For example, tasks that crawl websites or
      which spend a lot of time waiting to read/write to a socket, will get a
      huge boost from using the greenlet worker model. Because greenlets are so
      cheap in terms of memory, you can easily run a large number of workers.
      All code that does **not** consist in waiting for a socket will be
      blocking and cannot be pre-empted. Understand the tradeoffs before
      jumping to use greenlets. When using with Redis, ensure that your
      connection pool is large enough to provide connections for each greenlet.
    * Anything else: use "thread". You get the benefits of pre-emptive
      multi-tasking without the overhead of multiple processes. A safe choice
      and the default.

    See the :ref:`worker-types` section for additional information.

``-n``, ``--no-periodic``
    Indicate that this consumer process should *not* enqueue periodic tasks.
    When running multiple consumers against one queue, all but one should use
    this so periodic tasks are enqueued once rather than once per consumer.

``-d``, ``--delay``
    When using a "polling"-type queue backend, this is the number of seconds to
    wait when polling the backend. Default is 0.1 seconds. If no tasks are
    found in the queue, it will multiply the current delay by the backoff
    parameter. When a task is received, the polling interval will reset back to
    this value.

``-m``, ``--max-delay``
    The maximum amount of time to wait between polling, if using weighted
    backoff. Default is 10 seconds. If your huey consumer doesn't see a lot of
    action, you can increase this number to reduce CPU usage.

``-b``, ``--backoff``
    The amount to back-off when polling for tasks. Must be at least one.
    Default is 1.15. Here is how the defaults, 0.1 initial and 1.15
    backoff, look:

    .. image:: https://media.charlesleifer.com/blog/photos/p1472257818.22.png

``-c``, ``--health-check-interval``
    How often huey checks the status of the workers, restarting any that died.
    Default is 10 seconds.

``-C``, ``--disable-health-check``
    Disable the worker health checks. Leaving them enabled is cheap, so most
    deployments should keep the default.

``-f``, ``--flush-locks``
    Flush all locks when starting the consumer. This may be useful if the
    consumer was killed abruptly while executing a locked task.

``-L``, ``--extra-locks``
    Additional lock-names to flush when starting the consumer, separated by
    comma. This is useful if you have locks within context-managers that may
    not be discovered during consumer startup. Implies ``--flush-locks``.

``-M``, ``--max-tasks``
    Restart a worker after it has executed the given number of tasks. This
    option requires that the worker health check be enabled. If it is not, an
    error will be raised.

``-t``, ``--shutdown-timeout``
    Seconds to wait for workers to finish their current task during a graceful
    shutdown. When the timeout elapses, remaining tasks are interrupted as if
    the consumer had received the interrupt signal. By default the consumer
    waits indefinitely for in-flight tasks to finish.

``-g``, ``--graceful-signal``
    By default huey uses ``INT`` to trigger graceful shutdown, and ``TERM`` to
    interrupt running tasks and shutdown immediately. Most process
    supervisors send ``TERM``, so specify ``-g TERM`` in production, which will
    use ``TERM`` for graceful and ``INT`` to shutdown immediately. See
    :ref:`deployment-signals`.

``-s``, ``--scheduler-interval``
    The frequency with which the scheduler should run. By default this will run
    every second, but you can increase the interval to as much as 60 seconds.
    The value must divide evenly into 60.

Examples
^^^^^^^^

Running the consumer with 8 threads and a logfile for errors:

.. code-block:: shell

    huey_consumer my.app.huey -l /var/log/app.huey.log -w 8 -q

Using multi-processing to run 4 worker processes.

.. code-block:: shell

    huey_consumer my.app.huey -w 4 -k process

Running single-threaded with periodic task support disabled. Additionally,
verbose logging is written to stderr.

.. code-block:: shell

    huey_consumer my.app.huey -v -n

Using greenlets to run 50 workers, with no health checking and a scheduler
granularity of 60 seconds.

.. code-block:: shell

    huey_consumer my.app.huey -w 50 -k greenlet -C -s 60

.. _worker-types:

Worker types
------------

The consumer consists of a main process, a scheduler, and one or more workers.
These components run concurrently, and Huey supports three mechanisms to
achieve this concurrency.

* *thread*, the default, uses OS threads. Due to Python's global interpreter
  lock, only one thread can be running at a time. The Python runtime can switch
  the running thread when an I/O occurs or when a thread is idle. If the worker
  is CPU-bound, the runtime will pre-emptively switch threads after a short
  interval (5ms by default). Threads provide a good balance of performance and
  memory efficiency.
* *process* runs the scheduler and worker(s) in their own process. The main
  benefit over threads is the absence of the global interpreter lock, which
  allows CPU-bound workers to execute in parallel. Since each process maintains
  its own copy of the code in memory, it is likely that processes will require
  more memory than threads or greenlets. Processes are a good choice for tasks
  that perform CPU-intensive work.
* *greenlet* runs the scheduler and worker(s) in greenlets. Requires `gevent <https://gevent.org/>`_.
  When a task performs an operation that would be blocking (read or write on a
  socket), the file descriptor is added to an event loop managed by gevent,
  and the scheduler will switch tasks. Since gevent uses cooperative
  multi-tasking, a task that is CPU-bound will not yield control to the gevent
  scheduler, limiting concurrency. For this reason, gevent is a good choice for
  tasks that perform lots of socket I/O. When using Redis, ensure that your
  connection pool is large enough for each greenlet to have its own
  connection.

When in doubt, the default setting (``thread``) is a safe choice.

.. warning::
    Multiprocess support is not available for Windows. The only process start
    method available on Windows is "spawn", which has the downside of requiring
    the Huey state to be pickled. Huey uses (and creates) many objects which
    cannot be pickled. More information here: `multiprocessing documentation <https://docs.python.org/3/library/multiprocessing.html#the-spawn-and-forkserver-start-methods>`_.

Using gevent
^^^^^^^^^^^^

Gevent works by monkey-patching various Python modules, such as ``socket``,
``ssl``, ``time``, etc. In order for your application to be able to switch
tasks reliably, you should apply the monkey-patch at the very beginning of
your code, before anything else gets loaded:

.. code-block:: python

    # main.py
    from gevent import monkey; monkey.patch_all()

    from .app import wsgi_app  # Import our WSGI app.
    from .db import database  # Database connection.
    from .queue import huey  # Huey instance for our app.
    from .tasks import *  # Import all tasks, so they are discoverable.

To run the consumer:

.. code-block:: shell

    huey_consumer main.huey -k greenlet -w 16

.. _consumer-shutdown:

Consumer shutdown
-----------------

The huey consumer supports graceful shutdown via ``SIGINT``. Workers are
allowed to finish up whatever task they are currently executing before the
process exits.

Alternatively, you can shutdown the consumer using ``SIGTERM`` and any running
tasks will be interrupted.

To swap the two signals, run the consumer with ``--graceful-signal=TERM``. To
put an upper bound on a graceful shutdown, use ``--shutdown-timeout``.

Huey does not guarantee at-least-once delivery of messages, and does not do
acknowledgement of completed tasks. This means that if you terminate the
consumer **without** letting it finish any currently-executing tasks, those
tasks will be lost. To be alerted when this occurs, you can use Huey's
:ref:`signals` (specifically ``signals.SIGNAL_INTERRUPTED``).

.. _consumer-deployments:

Deployments
^^^^^^^^^^^

When deploying new code, your best bet is to gracefully shutdown the Huey
consumer, letting all running tasks finish, before starting a new consumer
process using the new code.

If you have long-running tasks, an alternative option is to configure your new
code to use a separate storage namespace. On Redis this is as simple as
specifying a new ``name`` for your ``RedisHuey()`` instance. Then you can start
the new code and new consumer, and they will operate independently of the
previously-running consumer. When all tasks are done, you can gracefully
shutdown the old consumer.

.. _consumer-restart:

Consumer restart
----------------

To cleanly restart the consumer, including all workers, send the ``SIGHUP``
signal. Any tasks being executed will be allowed to finish before the restart
occurs.

.. _process-supervisors:

supervisord and systemd
-----------------------

Huey works with `supervisord <https://supervisord.org/>`_,
`systemd <https://systemd.io/>`_ and presumably any other process supervisor.
For complete deployment examples (Docker, Docker Compose, PaaS
configurations) and a production checklist, see :ref:`deployment`.

.. note::
    Django users may replace ``huey_consumer`` with the appropriate path to
    ``manage.py run_huey``.

.. _multiple-consumers:

Multiple Consumers
------------------

Huey is typically run on a single server, with the number of workers scaled-up
according to your applications workload. However, it is also possible to run
multiple Huey consumers across multiple servers. When running multiple
consumers, it is crucial that **only one consumer** be configured to enqueue
periodic tasks.

By default the consumer will enqueue periodic tasks for execution whenever they
are ready to be run. When multiple consumers are used, it is therefore
necessary to specify the ``-n`` or ``--no-periodic`` option for all consumers
except one.

For example:

* Server A (main): ``huey_consumer myapp.huey -w 8 -k process``
* Server B: ``huey_consumer myapp.huey -w 8 -k process --no-periodic``
* Server C: ``huey_consumer myapp.huey -w 8 -k process --no-periodic``

Since each Huey consumer must be able to communicate with the queue and
result-store, Redis or another network-accessible storage backend must be used.

.. note::
    This section covers running multiple consumers against a *single* queue.
    To run multiple *queues*, see :ref:`recipe-multiple-queues`.

.. _consumer-internals:

Consumer Internals
------------------

The `code for the consumer <https://github.com/coleifer/huey/blob/master/huey/consumer.py>`_
is worth reading alongside this section.

1. You call a function that huey has decorated, which triggers a message being
   put into the queue (e.g a Redis list). At this point your application
   returns immediately, returning a :py:class:`Result` object.
2. In the consumer process, the worker(s) will be listening for new messages
   and one of the workers will receive your message indicating which task to
   run, when to run it, and with what parameters.
3. The worker looks at the message and checks to see if it can be run. If it
   is scheduled to run later, it gets added to the schedule. If it is revoked
   or has expired, the message is thrown out. Otherwise, it is executed.
4. The worker executes the task. If the task finishes, any results are stored
   in the result store. If the task fails, the consumer checks to see if the
   task can be retried. Depending on the task's ``retry_delay``, huey will
   either re-enqueue the task for execution, or tell the scheduler when to
   re-enqueue it.

While all the above is going on with the Worker(s), the Scheduler is looking at
its schedule to see if any tasks are ready to be executed. If a task is ready
to run, it is enqueued and will be processed by the next available worker.

If you are using the Periodic Task feature (cron), then every minute, the
scheduler will check through the periodic tasks to see if any should be run.
If so, these tasks are enqueued.

Signals
-------

The consumer will emit certain :ref:`signals` as it executes tasks.
