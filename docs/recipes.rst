.. _recipes:

Recipes
=======

This document contains practical patterns and solutions for common problems
encountered when building applications with Huey. Each recipe includes a
working example and discussion of the tradeoffs involved.

Key/Value Data Storage
----------------------

The Huey result-store can be used directly if you need a convenient way to
cache arbitrary key/value data:

.. code-block:: python

    @huey.task()
    def calculate_something():
        # By default, the result store treats get() like a pop(), so in
        # order to preserve the data so it can be read again, we specify
        # the second argument, peek=True.
        prev_results = huey.get('calculate-something.result', peek=True)
        if prev_results is None:
            # No previous results found, start from the beginning.
            data = start_from_beginning()
        else:
            # Only calculate what has changed since last time.
            data = just_what_changed(prev_results)

        # We can store the updated data back in the result store.
        huey.put('calculate-something.result', data)
        return data

See :py:meth:`Huey.get` and :py:meth:`Huey.put` for additional details.

.. _recipe-exponential-backoff:

Exponential Backoff Retries
---------------------------

Huey supports ``retries`` and ``retry_delay``, but does not support exponential
backoff out-of-the-box. Exponential backoff is important when calling external
services -- without it, a fleet of workers retrying at the same interval can
create a "thundering herd" that overwhelms a recovering service.

We can implement exponential backoff with a small decorator that leverages
the ``context=True`` parameter to access and modify the task instance:

.. code-block:: python

    import functools

    def exp_backoff_task(retries=10, retry_backoff=1.15):
        def deco(fn):
            @functools.wraps(fn)
            def inner(*args, **kwargs):
                task = kwargs.pop('task')
                try:
                    return fn(*args, **kwargs)
                except Exception:
                    task.retry_delay *= retry_backoff
                    raise
            return huey.task(retries=retries, retry_delay=1, context=True)(inner)
        return deco

    @exp_backoff_task(retries=5, retry_backoff=2)
    def call_external_api(endpoint, payload):
        resp = requests.post(endpoint, json=payload)
        resp.raise_for_status()
        return resp.json()

If the consumer starts executing the task at ``12:00:00``, the retry schedule
would look like:

* ``12:00:00`` first call
* ``12:00:02`` retry 1 (delay=1*2=2s)
* ``12:00:06`` retry 2 (delay=2*2=4s)
* ``12:00:14`` retry 3 (delay=4*2=8s)
* ``12:00:30`` retry 4 (delay=8*2=16s)
* ``12:01:02`` retry 5 (delay=16*2=32s)

.. note::
    The ``retry_delay`` is modified on the task instance itself, so the change
    persists across retries. The initial ``retry_delay=1`` is set when the task
    is registered, and gets multiplied by ``retry_backoff`` on each failure.

.. _recipe-idempotent-tasks:

Idempotent Tasks Using Deterministic IDs
-----------------------------------------

By default, every task invocation gets a random UUID. If the same logical task
is enqueued multiple times (e.g., from a webhook handler that might be called
more than once), you may end up with duplicate work. You can prevent this by
assigning a deterministic task ID.

The :py:meth:`~TaskWrapper.schedule` method accepts an ``id`` parameter:

.. code-block:: python

    @huey.task()
    def sync_user(user_id):
        user = User.get(user_id)
        external_service.sync(user.to_dict())

    # Only one sync per user will be enqueued at a time.  If the task is
    # already in the queue, enqueuing a second one with the same ID will
    # simply overwrite the result-store entry for that ID.
    sync_user.schedule(
        args=(user_id,),
        delay=5,
        id='sync-user-%s' % user_id)

.. warning::
    Huey does not de-duplicate by ID at the queue level -- both messages will
    exist in the queue. However, the result store will only track one result per
    ID. If true at-most-once delivery matters, combine a deterministic ID with
    the task deduplication recipe below.

.. _recipe-progress-tracking:

Progress Tracking via Key/Value Storage
---------------------------------------

Long-running tasks often need to report progress to the calling application.
Huey's key/value storage (:py:meth:`Huey.put` / :py:meth:`Huey.get`) is an
easy way to accomplish this:

.. code-block:: python

    @huey.task(context=True)
    def process_large_file(filepath, task=None):
        lines = open(filepath).readlines()
        total = len(lines)
        results = []

        for i, line in enumerate(lines):
            results.append(transform(line))
            if i % 100 == 0:
                huey.put('progress:%s' % task.id, {
                    'current': i,
                    'total': total,
                    'pct': int(100 * i / total),
                })

        huey.put('progress:%s' % task.id, {
            'current': total,
            'total': total,
            'pct': 100,
        })
        return results

On the application side, you can poll for progress:

.. code-block:: python

    result = process_large_file('/data/big.csv')

    # Poll for progress.  Use peek=True to read without deleting.
    progress = huey.get('progress:%s' % result.id, peek=True)
    if progress:
        print('%d%% complete' % progress['pct'])

.. note::
    By default :py:meth:`Huey.get` is destructive (it deletes the value after
    reading). Pass ``peek=True`` to read the value without removing it. Remember
    to clean up the progress key when you are finished:
    ``huey.delete('progress:%s' % task_id)``.

.. _recipe-custom-error-metadata:

Custom Error Metadata
---------------------

When a task fails, Huey stores an error result containing the exception
representation, traceback, retry count, and task ID. You can enrich this by
subclassing your Huey instance and overriding :py:meth:`~Huey.build_error_result`:

.. code-block:: python

    from huey import RedisHuey

    class MyHuey(RedisHuey):
        def build_error_result(self, task, exception):
            err = super().build_error_result(task, exception)
            # Add the task name and arguments for easier debugging.
            err['task_name'] = task.name
            err['task_args'] = task.args
            err['task_kwargs'] = task.kwargs
            return err

    huey = MyHuey('my-app')

Now when you catch a :py:class:`TaskException`, the metadata dict contains
your custom fields:

.. code-block:: python

    result = failing_task('some-arg')
    try:
        result.get(blocking=True, timeout=10)
    except TaskException as exc:
        print(exc.metadata['task_name'])    # 'failing_task'
        print(exc.metadata['task_args'])    # ('some-arg',)
        print(exc.metadata['traceback'])    # Full traceback string.

.. _recipe-task-deduplication:

Task Deduplication
------------------

You can use the key/value storage and a :py:meth:`~Huey.pre_execute` hook to
skip a task if an identical one is already running:

.. code-block:: python

    @huey.pre_execute()
    def deduplicate(task):
        # Build a dedup key from the task name and arguments.
        dedup_key = 'dedup:%s:%s' % (task.name, hash(task.data))
        if not huey.put_if_empty(dedup_key, '1'):
            raise CancelExecution('Duplicate task, skipping')

    @huey.post_execute()
    def clear_dedup(task, task_value, exc):
        dedup_key = 'dedup:%s:%s' % (task.name, hash(task.data))
        huey.delete(dedup_key)

:py:meth:`Huey.put_if_empty` is atomic -- it stores the value only if the key
does not already exist, and returns ``False`` if the key was already present.
The post-execute hook clears the key so that the same arguments can be
processed again in the future.

.. warning::
    ``hash()`` is randomized across Python processes by default (due to hash
    randomization). For cross-process deduplication, use a deterministic hash
    such as ``hashlib.md5``.

.. _recipe-interrupted-tasks:

Graceful Shutdown and Re-enqueueing Interrupted Tasks
-----------------------------------------------------

When the consumer is shut down with ``SIGTERM``, any tasks that are mid-
execution are interrupted. By default, these tasks are lost. You can use the
``SIGNAL_INTERRUPTED`` signal to re-enqueue them:

.. code-block:: python

    from huey.signals import SIGNAL_INTERRUPTED

    @huey.signal(SIGNAL_INTERRUPTED)
    def on_interrupted(signal, task, *args, **kwargs):
        # The consumer was killed before this task finished.
        # Re-enqueue it so it will be picked up again.
        huey.enqueue(task)

This is especially important in production deployments. When using
``supervisord``, set ``stopwaitsecs`` to give the consumer time for a graceful
shutdown (``SIGINT``) before supervisor sends ``SIGTERM``:

.. code-block:: ini

    [program:my_huey]
    command=/path/to/huey_consumer.py my_app.huey -w 4
    stopwaitsecs=30
    stopsignal=INT

With this configuration, supervisor sends ``SIGINT`` first, waits 30 seconds
for a graceful shutdown, and only sends ``SIGTERM`` if the consumer is still
running.

.. _recipe-monitoring:

Monitoring Queue Depth
----------------------

Huey provides several introspection methods that are useful for building a
monitoring endpoint or health check:

.. code-block:: python

    def get_queue_stats():
        return {
            'pending': huey.pending_count(),
            'scheduled': huey.scheduled_count(),
            'results': huey.result_count(),
        }

If you are using a web framework, you can expose this as an endpoint:

.. code-block:: python

    # Flask example.
    @app.route('/huey/health/')
    def huey_health():
        stats = get_queue_stats()
        return jsonify(stats)

You can also inspect the actual tasks in the queue:

.. code-block:: python

    # List all pending tasks (deserializes each one, can be expensive).
    for task in huey.pending():
        print(task.name, task.id, task.args)

    # List all scheduled tasks.
    for task in huey.scheduled():
        print(task.name, task.id, task.eta)

.. note::
    :py:meth:`Huey.pending` and :py:meth:`Huey.scheduled` deserialize every
    task in the queue, which can be slow if the queue is very large. Use
    :py:meth:`Huey.pending_count` and :py:meth:`Huey.scheduled_count` when you
    only need the count.

.. _recipe-task-metrics:

Using Signals for Task Metrics
------------------------------

Signals can be used to record execution metrics for every task. This recipe
shows how to time task execution and record it to a metrics system:

.. code-block:: python

    import time
    from huey.signals import SIGNAL_EXECUTING, SIGNAL_COMPLETE, SIGNAL_ERROR

    _task_start_times = {}

    @huey.signal(SIGNAL_EXECUTING)
    def on_executing(signal, task):
        _task_start_times[task.id] = time.monotonic()

    @huey.signal(SIGNAL_COMPLETE, SIGNAL_ERROR)
    def on_finished(signal, task, exc=None):
        start = _task_start_times.pop(task.id, None)
        if start is not None:
            duration = time.monotonic() - start
            # Record to your metrics system (statsd, prometheus, etc).
            metrics.timing('huey.task.duration', duration, tags={
                'task': task.name,
                'status': 'error' if signal == 'error' else 'ok',
            })

.. warning::
    Signal handlers are executed synchronously by the consumer worker. Keep
    them fast -- a slow signal handler blocks the worker from picking up the
    next task. If your metrics client performs network I/O, consider buffering
    writes or using an async client.

    Also note that ``_task_start_times`` is a plain dict. This works correctly
    with thread and greenlet workers (shared memory), but with process workers
    each process has its own dict, which is still correct since a given task
    runs in a single process.

.. _recipe-signed-serializer:

Signed Serializer for Untrusted Environments
---------------------------------------------

By default Huey uses ``pickle`` to serialize tasks and results. If your Redis
instance is shared or network-exposed, a malicious actor could inject a crafted
pickle payload. The :py:class:`SignedSerializer` adds an HMAC signature to
every message, so tampered data is rejected:

.. code-block:: python

    from huey import RedisHuey
    from huey.serializer import SignedSerializer

    huey = RedisHuey(
        'my-app',
        serializer=SignedSerializer(secret='my-secret-key'))

The ``secret`` must be the same for both the application process and the
consumer. If a message has been tampered with, deserialization will raise a
``ValueError``.

.. note::
    The signed serializer does **not** encrypt the data -- it only detects
    tampering. The task arguments are still visible in Redis. If you need
    encryption, you can subclass :py:class:`Serializer` and implement your
    own ``_serialize``/``_deserialize`` methods using a library like
    ``cryptography``.

.. _recipe-dynamic-fanout:

Dynamic Fan-Out
---------------

Chord members must be known at enqueue time. When the set of sub-tasks depends
on a runtime value (e.g., paginated API results), enqueue the chord from inside
a task:

.. code-block:: python

    @huey.task()
    def fetch_page(url):
        return requests.get(url).json()

    @huey.task()
    def aggregate(results):
        combined = {}
        for page_data in results:
            combined.update(page_data)
        return combined

    @huey.task()
    def discover_and_fetch(base_url):
        # Discover the pages to fetch at runtime.
        index = requests.get(base_url).json()
        urls = [item['url'] for item in index['items']]

        result = huey.enqueue(
            chord([fetch_page.s(u) for u in urls], aggregate.s()))

        # Optionally, store the callback task ID so the caller can track it.
        huey.put('fanout-result-id', result.callback.id)

.. _recipe-run-arbitrary-functions:

Run Arbitrary Functions as Tasks
--------------------------------

Instead of explicitly declaring all tasks up-front, you can write a general-
purpose task that accepts a dotted import path and calls any function:

.. code-block:: python

    from importlib import import_module

    @huey.task()
    def path_task(path, *args, **kwargs):
        module_path, name = path.rsplit('.', 1)
        mod = import_module(module_path)
        return getattr(mod, name)(*args, **kwargs)

    # Usage: runs myapp.utils.reindex('products') in the consumer.
    path_task('myapp.utils.reindex', 'products')

.. warning::
    This pattern is powerful but should be used with care. The function must be
    importable by the consumer process, and the arguments must be picklable.
    Avoid exposing this to untrusted input.

Dynamic periodic tasks
----------------------

To create periodic tasks dynamically we need to register them so that they are
added to the in-memory schedule managed by the consumer's scheduler thread.
Since this registry is in-memory, any dynamically defined tasks must be
registered within the process that will ultimately schedule them: the consumer.

.. warning::
    The following example will not work with the **process** worker-type
    option, since there is currently no way to interact with the scheduler
    process. When threads or greenlets are used, the worker threads share the
    same in-memory schedule as the scheduler thread, allowing modification to
    take place.

Example:

.. code-block:: python

    def dynamic_ptask(message):
        print('dynamically-created periodic task: "%s"' % message)

    @huey.task()
    def schedule_message(message, cron_minutes, cron_hours='*'):
        # Create a new function that represents the application
        # of the "dynamic_ptask" with the provided message.
        def wrapper():
            dynamic_ptask(message)

        # The schedule that was specified for this task.
        schedule = crontab(cron_minutes, cron_hours)

        # Need to provide a unique name for the task. There are any number of
        # ways you can do this -- based on the arguments, etc. -- but for our
        # example we'll just use the time at which it was declared.
        task_name = 'dynamic_ptask_%s' % int(time.time())

        huey.periodic_task(schedule, name=task_name)(wrapper)

Assuming the consumer is running, we can now set up as many instances as we
like of the "dynamic ptask" function:

.. code-block:: pycon

    >>> from demo import schedule_message
    >>> schedule_message('I run every 5 minutes', '*/5')
    <Result: task ...>
    >>> schedule_message('I run between 0-15 and 30-45', '0-15,30-45')
    <Result: task ...>

When the consumer executes the "schedule_message" tasks, our new periodic task
will be registered and added to the schedule.

.. _recipe-multiple-queues:

Multiple Queues
---------------

A huey application consists of a :py:class:`Huey` instance (which is a named
queue), tasks registered with that instance, and a consumer process that runs
them. One instance is one queue, served by one consumer -- and routing
therefore happens at decoration time: whichever instance's ``task()``
decorator you use is the queue the task runs on.

Before reaching for a second queue, consider whether :ref:`task priorities
<priority>` solve your problem. If the goal is simply "urgent tasks should
jump the line", priorities give you that with one queue and no extra
processes. Separate queues earn their keep when you want:

* Different concurrency or worker-type per class of task -- e.g.
  ``-k process`` for CPU-bound work and ``-k greenlet -w 50`` for IO-bound
  work.
* Isolation -- a flood of cheap tasks must never be able to starve your
  critical tasks of workers.
* Per-machine routing -- certain tasks should only run on certain hosts.

To run multiple queues, declare multiple instances. A dedicated module keeps
imports clean, and the instances can share a connection pool:

.. code-block:: python

    # myapp/queues.py
    from huey import RedisHuey
    from redis import ConnectionPool

    pool = ConnectionPool(host='localhost', port=6379, max_connections=20)

    emails = RedisHuey('myapp.emails', connection_pool=pool)
    reports = RedisHuey('myapp.reports', connection_pool=pool)

Tasks are routed by the decorator used to declare them:

.. code-block:: python

    # myapp/tasks.py
    from myapp.queues import emails, reports

    @emails.task(retries=2)
    def send_email(to, subject, body):
        ...

    @reports.task()
    def build_report(day):
        ...

    @reports.periodic_task(crontab(minute='0', hour='3'))
    def nightly_rollup():
        # Enqueued by the *reports* consumer's scheduler only.
        ...

Each queue gets its own consumer, tuned independently:

.. code-block:: shell

    huey_consumer.py myapp.queues.emails  -w 8 -k greenlet
    huey_consumer.py myapp.queues.reports -w 2 -k process

Running N consumers means supervising N processes. With systemd this is a
single template unit, ``/etc/systemd/system/huey@.service``, where ``%i``
expands to the attribute name in ``myapp.queues``:

.. code-block:: ini

    [Unit]
    Description=huey consumer for %i

    [Service]
    WorkingDirectory=/srv/myapp
    ExecStart=/srv/myapp/venv/bin/huey_consumer myapp.queues.%i -w 4
    KillSignal=SIGINT
    TimeoutStopSec=60
    Restart=on-failure

    [Install]
    WantedBy=multi-user.target

.. code-block:: shell

    systemctl enable --now huey@emails huey@reports

(See :ref:`deployment` for the full discussion of supervisor configuration.)

This works with any storage backend. Since the sqlite storage namespaces all
of its tables by queue name, multiple instances can even share a single
database file:

.. code-block:: python

    emails = SqliteHuey('emails', filename='/var/lib/myapp/huey.db')
    reports = SqliteHuey('reports', filename='/var/lib/myapp/huey.db')

Pitfalls to be aware of:

* Everything is per-instance: results, schedules, locks and revocations. A
  :py:class:`Result` handle can only be read through the instance that
  produced it, and revoking a task on one queue has no effect on another.
* Periodic tasks belong to the instance that declared them, and are enqueued
  by that instance's consumer. No coordination is needed between consumers of
  *different* queues -- the ``-n`` / ``--no-periodic`` dance is only required
  when running multiple consumers of the *same* queue
  (:ref:`multiple-consumers`).
* The queue ``name`` is the storage namespace. Two instances with the same
  name on the same storage are the same queue; instances sharing a sqlite
  file must use distinct names.
* ``immediate`` mode is a per-instance setting -- in tests, remember to flip
  it on every instance.

Django users wanting multiple queues with the ``settings.HUEY``-style
configuration should check out the third-party
`django-huey <https://github.com/gaiacoop/django-huey>`_ package.

.. _recipe-redis-sentinel:

High-Availability Redis: Sentinel, Valkey and Cluster
-----------------------------------------------------

:py:class:`RedisHuey` accepts a pre-configured ``connection_pool``, which
means huey works with `Redis Sentinel
<https://redis.io/docs/latest/operate/oss_and_stack/management/sentinel/>`_
out-of-the-box. The pool returned by ``master_for()`` re-discovers the
current master automatically after a failover:

.. code-block:: python

    from redis.sentinel import Sentinel
    from huey import RedisHuey

    sentinel = Sentinel(
        [('10.0.0.1', 26379), ('10.0.0.2', 26379), ('10.0.0.3', 26379)],
        # IMPORTANT: the socket timeout must comfortably exceed the
        # consumer's blocking read timeout (default 1s). If it does not,
        # every blocking dequeue raises TimeoutError at the socket level
        # and the consumer degrades to logging errors and polling.
        socket_timeout=5.0)

    huey = RedisHuey(
        'my-app',
        connection_pool=sentinel.master_for('my-master').connection_pool)

Always use ``master_for()``. Huey reads *and* writes on every code-path, so a
``slave_for()`` pool will fail with ``ReadOnlyError``. If your deployment
requires authentication, pass ``password=`` for the data nodes and
``sentinel_kwargs={'password': '...'}`` for the sentinels themselves.

Django users configure this by assigning the instance directly (djhuey
accepts a :py:class:`Huey` instance as well as a settings dict):

.. code-block:: python

    # settings.py
    from redis.sentinel import Sentinel
    from huey import RedisHuey

    sentinel = Sentinel([('10.0.0.1', 26379), ...], socket_timeout=5.0)
    HUEY = RedisHuey(
        'my-app',
        connection_pool=sentinel.master_for('my-master').connection_pool)

**What happens during a failover.** The consumer is failover-tolerant by
construction: when the master goes away, workers log the dequeue error and
apply backoff, the scheduler does the same, and once Sentinel promotes a new
master the pool reconnects to it automatically -- no restart required. Two
caveats to understand: Redis replication is asynchronous, so writes that land
in the failover window (enqueues, results) can be lost when the old master's
unreplicated data is discarded; and a task that was dequeued but unfinished
when its worker lost the connection is gone -- which is huey's normal
at-most-once behavior on worker death, not something Sentinel introduces.
High-availability Redis does not make individual tasks durable; pair it with
idempotent task design and the :ref:`recipe-interrupted-tasks` recipe.

**Valkey and Redict** are wire-compatible with Redis and work with
:py:class:`RedisHuey` unchanged -- simply point it at your valkey host (the
``redis-py`` client speaks to either). If you prefer the official
``valkey-glide`` client, huey ships ``ValkeyGlideHuey`` in
``huey.contrib.valkey_glide``.

**Redis Cluster.** Huey's Redis usage is single-key (the one Lua script was
made cluster-safe in 2.4.2), but :py:class:`RedisHuey` constructs a standard
redis-py client and connection pool, and does not support redis-py's
``RedisCluster`` client directly. For high availability, Sentinel is the
supported topology.

.. _recipe-flask:

Using Huey with Flask
---------------------

Huey is framework-agnostic and needs no extension to work with Flask. There
are only two questions to answer: where to declare the :py:class:`Huey`
instance, and how to give tasks access to the application context.

Declare the instance alongside (or before) the app, and import it from your
tasks module:

.. code-block:: python

    # app.py
    from flask import Flask
    from huey import RedisHuey

    app = Flask(__name__)
    huey = RedisHuey('my-app')

.. code-block:: python

    # tasks.py
    from app import app, huey

    @huey.task()
    def send_welcome_email(user_id):
        # Tasks run in the consumer process, outside any request. If the
        # task uses Flask extensions (database, mail, etc.), give it an
        # application context:
        with app.app_context():
            user = User.query.get(user_id)
            mail.send(make_welcome_message(user))

Views simply call the task to enqueue it:

.. code-block:: python

    # views.py
    from app import app
    from tasks import send_welcome_email

    @app.route('/signup/', methods=['POST'])
    def signup():
        user = create_user(request.form)
        send_welcome_email(user.id)
        return redirect(url_for('welcome'))

If most of your tasks need the application context, wrap the boilerplate in
a small decorator:

.. code-block:: python

    import functools

    def flask_task(*task_args, **task_kwargs):
        def decorator(fn):
            @functools.wraps(fn)
            def inner(*args, **kwargs):
                with app.app_context():
                    return fn(*args, **kwargs)
            return huey.task(*task_args, **task_kwargs)(inner)
        return decorator

    @flask_task(retries=2)
    def send_welcome_email(user_id):
        ...

The consumer is pointed at an entry module that imports the app and all of
the tasks (see :ref:`imports`):

.. code-block:: shell

    huey_consumer.py main.huey -w 4

A complete, runnable application is available in `examples/flask_ex
<https://github.com/coleifer/huey/tree/master/examples/flask_ex>`_.

.. _recipe-fastapi:

Using Huey with FastAPI
-----------------------

Huey works well as the background task-queue for an async application like
FastAPI: task functions themselves are regular (synchronous) functions
executed by the consumer in a separate process, while the web app enqueues
work and awaits results without blocking the event loop.

Declare the instance and tasks in their own module, as usual:

.. code-block:: python

    # tasks.py
    from huey import RedisHuey

    huey = RedisHuey('my-app')

    @huey.task()
    def generate_report(user_id):
        ...  # Heavy lifting happens in the consumer.
        return report_data

Enqueueing from an async request handler is fine as-is -- it is a single,
fast storage write:

.. code-block:: python

    # api.py
    from fastapi import FastAPI
    from huey.contrib.asyncio import aget_result

    from tasks import generate_report, huey

    app = FastAPI()

    @app.post('/report/{user_id}')
    async def begin_report(user_id: int):
        rh = generate_report(user_id)
        return {'task_id': rh.id}

    @app.get('/report/status/{task_id}')
    async def report_status(task_id: str):
        # Non-blocking, non-destructive read of the result store.
        value = huey.result(task_id, preserve=True)
        return {'ready': value is not None, 'value': value}

To hold the request open until the task finishes, await the result with the
:ref:`asyncio helpers <asyncio>` -- other requests continue to be served
while this coroutine waits:

.. code-block:: python

    @app.post('/report/{user_id}/wait')
    async def report_wait(user_id: int):
        rh = generate_report(user_id)
        value = await aget_result(rh)
        return {'value': value}

Notes:

* The consumer runs separately, exactly as with any huey application:
  ``huey_consumer.py tasks.huey -w 4``.
* Task functions are plain ``def`` functions -- huey does not execute
  ``async def`` tasks. IO-bound workloads can still get high concurrency in
  the consumer via ``-k greenlet``.
* If a task raised an exception, reading its result raises
  :py:class:`TaskException` -- handle it in the status endpoint if your
  tasks can fail.
* ``huey.result(task_id)`` is destructive by default; ``preserve=True``
  keeps the result so the status endpoint can be polled repeatedly.
