.. _monitoring:

Monitoring
==========

Huey emits :ref:`signals` as it operates, and also can return counts for key
metrics.

Measurements
------------

* :py:meth:`Huey.pending_count`, tasks ready to run and waiting for a worker.
* :py:meth:`Huey.scheduled_count`, tasks scheduled with a future ``eta``.
* :py:meth:`Huey.result_count`, key/value pairs in the result store (results,
  plus revoke flags and locks).

From signals, recorded in the consumer:

* Per-task counts of ``SIGNAL_COMPLETE``, ``SIGNAL_ERROR`` and
  ``SIGNAL_RETRYING``.
* Execution duration, from ``SIGNAL_EXECUTING`` to ``SIGNAL_COMPLETE`` or
  ``SIGNAL_ERROR``, keyed on ``task.id``.

The full list of signals and their ordering is in :ref:`signals`. Signals
fire in the process that runs the task, so the recording handlers must be
registered in a module the consumer imports.

Counters from signals
---------------------

Task stats can be aggregated by ``task.name``:

.. code-block:: python

    from huey.signals import SIGNAL_COMPLETE, SIGNAL_ERROR, SIGNAL_RETRYING

    @huey.signal(SIGNAL_COMPLETE, SIGNAL_ERROR, SIGNAL_RETRYING)
    def count(signal, task, exc=None):
        statsd.incr('huey.%s' % signal, tags={'task': task.name})

See :ref:`recipe-task-metrics` for the complete example on measuring timing.
Queue depth as a health endpoint is in :ref:`recipe-monitoring`.

Handlers run synchronously in the worker, so a metrics client that blocks on
the network stalls the worker with it. Use a UDP client (statsd) or an
in-process registry scraped separately (prometheus).

What to alert on
----------------

* ``pending_count`` growing across several samples. Workers are not keeping
  up, or the consumer is down.
* ``SIGNAL_ERROR`` rate, per task. A retrying task emits ``SIGNAL_ERROR``
  on each attempt, so count ``SIGNAL_RETRYING`` separately to tell transient
  from terminal failures.
* No ``SIGNAL_COMPLETE`` for N minutes on a queue that normally has traffic.
  Catches a consumer that is up but stuck.
* Any ``SIGNAL_INTERRUPTED``. Tasks were interrupted due to a hard shutdown
  (:ref:`deployment-signals`).

Logging
-------

The ``-l`` / ``--logfile``, ``-v`` / ``--verbose``, ``-q`` / ``--quiet`` and
``-S`` / ``--simple`` options and attaching your own handler are described in
:ref:`logging`.

The default format is ``[time] LEVEL:logger:worker:message``. For structured
output, attach a JSON formatter to the ``huey`` logger before the consumer
starts:

.. code-block:: python

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger('huey')
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

``run_huey`` then skips its default handler. ``huey_consumer`` always adds
its own, so every record prints twice. Start the consumer from your own script
with ``huey.create_consumer(...).run()`` instead.

Sentry
------

Report unhandled task exceptions from ``SIGNAL_ERROR``:

.. code-block:: python

    import sentry_sdk
    from huey.signals import SIGNAL_ERROR

    @huey.signal(SIGNAL_ERROR)
    def report(signal, task, exc):
        sentry_sdk.capture_exception(exc)

Tracing
-------

Pass trace contexts as an ordinary task argument, and open a span in the
:py:meth:`~Huey.pre_execute` hook:

.. code-block:: python

    @huey.task()
    def process(order_id, traceparent=None):
        ...

    with tracer.start_as_current_span('enqueue') as span:
        process(order_id, traceparent=format_traceparent(span))

    @huey.pre_execute()
    def start_span(task):
        ctx = extract({'traceparent': task.kwargs.get('traceparent')})
        task.span = tracer.start_span(task.name, context=ctx)

    @huey.post_execute()
    def end_span(task, task_value, exc):
        task.span.end()

Dashboards
----------

:py:func:`enable_stats` records signals to a database and answers questions
like throughput and per-task error rate without a metrics system
(:ref:`task-stats`). The :ref:`Django admin <django-admin-stats>` and
:ref:`Flask-Peewee admin <flask-admin>` render it.
