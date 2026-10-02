.. _deployment:

Deploying to Production
=======================

The huey consumer is a normal, foreground Python process. It does not
daemonize, write pid-files, or manage its own lifecycle. That is the job of
a process supervisor like systemd, supervisord, Docker, or your PaaS. This
document provides correct, copy-paste configurations for the common
supervisors, along with a production checklist.

The configuration files shown below are also available in the `examples/deploy
<https://github.com/coleifer/huey/tree/master/examples/deploy>`_ directory of
the huey source tree.

.. _deployment-signals:

Shutdown Signals
----------------

The consumer responds to the following signals:

============  ==============================================================
Signal        Consumer behavior
============  ==============================================================
``SIGINT``    Graceful shutdown. Workers finish their current task, then the
              process exits.
``SIGTERM``   Immediate shutdown. Running tasks are interrupted, and
              ``SIGNAL_INTERRUPTED`` is emitted for each interrupted task.
``SIGHUP``    Graceful restart. Workers finish their current task, then the
              consumer re-executes itself in-place.
============  ==============================================================

Nearly every process supervisor stops processes with ``SIGTERM`` by default,
which huey treats as *stop immediately*. For historical reasons, Huey will
continue to use the above signals by default. Either configure your
supervisor to stop huey with ``SIGINT``, or flip the graceful/immediate
signals with ``--graceful-signal=TERM`` (``-g TERM``).

Additionally, to prevent a graceful shutdown from running indefinitely on a
stuck task, it is a good idea to specify ``--shutdown-timeout`` (``-t``). Any
tasks still running when the timeout elapses are interrupted, with
``SIGNAL_INTERRUPTED`` emitted for each. Set it a few seconds under the
supervisor's own kill deadline, so huey interrupts stragglers cleanly.

Two related points:

* A graceful shutdown protects *running* tasks. A task interrupted by ``SIGKILL``
  (or a power loss) is lost. Register a ``SIGNAL_INTERRUPTED`` handler to
  re-enqueue interrupted tasks (:ref:`recipe-interrupted-tasks`). As with any
  queue, design tasks to be idempotent wherever possible.
* Do not wrap the consumer in a shell script. The supervisor must signal the
  Python process directly, as an intermediate shell will interfere with
  signal delivery.

systemd
-------

.. literalinclude:: ../examples/deploy/huey.service
   :language: ini

Install the unit and start it:

.. code-block:: shell

    sudo cp huey.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now huey

Notes:

* journald captures stdout/stderr, so run the consumer *without* the ``-l``
  logfile option and read logs with ``journalctl -u huey``.
* ``systemctl reload huey`` triggers huey's graceful restart (``SIGHUP``):
  the consumer re-executes itself in-place, keeping the same PID. Avoid
  ``Type=forking``. The unit's ``Type=exec`` is correct, and also surfaces
  launch errors at startup.
* ``Restart=on-failure`` restarts the consumer after a crash, but leaves it
  stopped after a clean exit (e.g. a graceful ``kill -INT``). Use
  ``Restart=always`` to bring it back regardless. ``systemctl stop`` never
  triggers an automatic restart with either setting.

supervisord
-----------

.. literalinclude:: ../examples/deploy/supervisor.conf
   :language: ini

Notes:

* If your application module is not on the python-path, add e.g.
  ``environment=PYTHONPATH="/srv/my_app"`` or set ``directory`` to the
  project root (the consumer is run from ``directory``).
* After editing the config, ``supervisorctl reread && supervisorctl update``.

Docker
------

.. literalinclude:: ../examples/deploy/Dockerfile
   :language: docker

Notes:

* ``STOPSIGNAL SIGINT`` makes ``docker stop`` request a graceful shutdown.
  The default grace period is only 10 seconds, however, so stop with
  ``docker stop -t 60 <container>`` (or set ``stop_grace_period`` in
  compose) to match the consumer's ``-t 55``.
* Always use the exec form of ``CMD`` (the JSON-array form, with no shell),
  so the consumer runs as PID 1 and receives signals directly.
* Log to stdout (no ``-l``) and let the logging driver handle collection and
  rotation.
* The ``process`` worker type works fine in containers. For ``greenlet``
  workers, remember the monkey-patch must be applied at the top of your
  entry module. See :ref:`consuming-tasks`.

Docker Compose
--------------

.. literalinclude:: ../examples/deploy/compose.yaml
   :language: yaml

Notes:

* The web app and the worker share one image, so both processes import the
  same code and the same task registry (see :ref:`imports`).
* Scaling the worker service (``docker compose up --scale worker=3``) runs
  multiple consumers against one queue, and each will independently enqueue
  periodic tasks. Run a single dedicated consumer for periodic tasks and
  start the scaled workers with ``-n`` / ``--no-periodic``. See
  :ref:`multiple-consumers`.
* Multiple containers can only share a queue through a network-accessible
  storage backend like Redis or Postgres. ``SqliteHuey`` and ``FileHuey`` work
  across containers only if every container mounts the same local volume, and
  sqlite over a network filesystem is a bad idea. When in doubt, use Redis or
  Postgres.

Kubernetes
----------

A minimal worker ``Deployment`` fragment:

.. code-block:: yaml

    spec:
      containers:
      - name: huey-worker
        image: my-app:latest
        command: ["huey_consumer", "my_app.huey", "-w", "4", "-n",
                  "-t", "55"]
      terminationGracePeriodSeconds: 60

The things that matter:

* Kubernetes honors the image's ``STOPSIGNAL``, so the Dockerfile above gets
  graceful shutdown for free. Without it, the kubelet sends ``SIGTERM`` and
  running tasks are interrupted. Adding ``-g TERM`` to the command works with
  any image and needs no custom Dockerfile.
* ``terminationGracePeriodSeconds`` is the SIGKILL deadline: keep it above
  ``--shutdown-timeout`` so lagging tasks are interrupted cleanly first.
* With ``replicas > 1``, periodic tasks must only be enqueued by one
  consumer. The simple pattern: a scalable worker Deployment started with
  ``-n`` / ``--no-periodic`` (as above), plus a single-replica "scheduler"
  Deployment running without ``-n``.

PaaS (Heroku-style)
-------------------

.. code-block:: text

    # Procfile
    web: gunicorn my_app.wsgi
    worker: huey_consumer my_app.huey -w 4 -k thread -g TERM -t 25

Dyno-style process managers send ``SIGTERM`` with a short grace period
(typically ~30 seconds) and offer no way to customize the signal. Run the
consumer with ``--graceful-signal=TERM`` so the deploy signal triggers a
graceful shutdown, and set ``--shutdown-timeout`` a few seconds under the
grace period so tasks that cannot finish in time are interrupted (and
``SIGNAL_INTERRUPTED`` emitted) before the platform sends ``SIGKILL``.
Registering the ``SIGNAL_INTERRUPTED`` re-enqueue handler
(:ref:`recipe-interrupted-tasks`) is essential on these platforms. Read the
storage location from the environment:

.. code-block:: python

    import os
    from huey import RedisHuey

    huey = RedisHuey('my-app', url=os.environ['REDIS_URL'])

Logging
-------

Under systemd, Docker, or a PaaS, log to stdout (the default when no ``-l``
option is given) and let the platform capture it.

When supervising the consumer some other way, use ``-l /var/log/huey.log``
and configure rotation. The consumer holds its logfile open and has no
reopen-on-signal mechanism, so use ``copytruncate``:

.. code-block:: text

    # /etc/logrotate.d/huey
    /var/log/huey.log {
        weekly
        rotate 8
        compress
        copytruncate
        missingok
    }

Health checks
-------------

The consumer monitors its own workers and restarts any that die (see the
``-c`` / ``--health-check-interval`` option), so an external liveness check
mainly needs to verify the process is up and the storage backend reachable.
A trivial exec-style probe:

.. code-block:: python

    # huey_health.py - exits non-zero if the storage backend is down.
    from my_app import huey
    huey.pending_count()

For queue-depth monitoring and a web-based health endpoint, see
:ref:`recipe-monitoring`.

Deploying new code
------------------

The consumer caches your task code in memory, so deploys must restart (or
gracefully re-exec) the consumer:

* ``systemctl reload huey`` / ``kill -HUP <pid>`` performs a graceful
  in-place restart. Workers finish their current task, then the consumer
  re-executes itself, picking up the new code.
* Or stop gracefully (``SIGINT``) and start a new consumer. This is what
  the supervisor configs above do on ``restart``.
* For very long-running tasks, you can run old and new code side-by-side by
  giving the new release a fresh storage ``name``. See
  :ref:`consumer-deployments`.

Production checklist
--------------------

* The supervisor stops huey with its graceful signal. For historical reasons,
  Huey uses ``SIGINT`` for graceful shutdown by default. To use ``SIGTERM`` for
  graceful shutdown instead, specify ``-g TERM``.
* Set ``--shutdown-timeout`` to a few seconds shorter than the process
  supervisor's kill timeout (:ref:`deployment-signals`).
* A ``SIGNAL_INTERRUPTED`` handler re-enqueues tasks interrupted mid-flight,
  see :ref:`recipe-interrupted-tasks`.
* Exactly one consumer enqueues periodic tasks and all others run with ``-n``.
* The consumer is run directly, with no shell-script wrappers.
* Result data is read (or expired) so the result store does not grow without
  bound. Read results, set ``expires=``, or use ``RedisExpireHuey``. See
  :ref:`troubleshooting`.
* If you use :py:meth:`~Huey.lock_task`, start the consumer with
  ``-f`` / ``--flush-locks`` so locks orphaned by a crash are cleared.
* Worker count and worker type match the workload (:ref:`worker-types`).
* ``immediate`` mode is disabled in production (it is the default, but
  Django users should double-check, since djhuey enables it when
  ``DEBUG=True``).
* If the storage backend is shared or network-exposed, messages are signed
  with :py:class:`SignedSerializer` (:ref:`recipe-signed-serializer`).
* Logs go to stdout under systemd/Docker/PaaS, or are rotated with
  ``copytruncate`` when using ``-l``.
