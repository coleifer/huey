.. huey documentation master file, created by
   sphinx-quickstart on Wed Nov 16 12:48:28 2011.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

huey
====

.. image:: https://media.charlesleifer.com/blog/photos/huey3-logo.png

*a lightweight alternative*.

huey is:

* a task queue
* written in python
* clean and simple API

huey has:

* support for redis (or valkey/redict), postgres, sqlite, file-system, or in-memory storage
* zero dependencies (``redis-py`` required to use redis-like brokers,
  ``psycopg`` for postgres).
* `example code <https://github.com/coleifer/huey/tree/master/examples/>`_.
* :ref:`django <django>` integration (native or via django.tasks) with
  optional :ref:`admin integration <django-admin-stats>` for visibility and
  management.

huey supports:

* multi-process, multi-thread or greenlet task execution models
* schedule tasks to execute at a given time, or after a given delay
* schedule recurring tasks, like a crontab
* automatically retry tasks that fail
* task prioritization
* task result storage
* task expiration
* task locking, rate-limits and timeouts
* task pipelines and chains
* groups (fan-out), chords (map / reduce)

.. image:: https://i.imgur.com/2EpRs.jpg

At a glance
-----------

:py:meth:`~Huey.task` and :py:meth:`~Huey.periodic_task` decorators turn
functions into tasks executed by the consumer:

.. code-block:: python

    from huey import RedisHuey, crontab

    huey = RedisHuey('my-app', host='redis.myapp.com')

    @huey.task()
    def add_numbers(a, b):
        return a + b

    @huey.task(retries=2, retry_delay=60)
    def flaky_task(url):
        return this_might_fail(url)

    @huey.periodic_task(crontab(minute='0', hour='3'))
    def nightly_backup():
        sync_all_data()

Calling a ``task``-decorated function will enqueue the function call. A result
handle is returned immediately, which can be used to fetch the result once the
task is finished:

.. code-block:: pycon

    >>> from demo import add_numbers
    >>> res = add_numbers(1, 2)
    >>> res
    <Result: task 6b6f36fc-da0d-4069-b46c-c0d4ccff1df6>

    >>> res()
    3

Tasks can be scheduled to run in the future:

.. code-block:: pycon

    >>> res = add_numbers.schedule((2, 3), delay=10)
    >>> res(blocking=True)  # Will block until task finishes, in ~10s.
    5

For much more, check out the :ref:`guide`.

Running the consumer
^^^^^^^^^^^^^^^^^^^^

Run the consumer with four worker processes:

.. code-block:: shell

    huey_consumer my_app.huey -k process -w 4

To run the consumer with a single worker thread (default):

.. code-block:: shell

    huey_consumer my_app.huey

If your work-loads are mostly IO-bound, you can run the consumer with threads
or greenlets instead:

.. code-block:: shell

    huey_consumer my_app.huey -k greenlet -w 32

For more information, see the :ref:`consuming-tasks` document.

Table of contents
-----------------

.. toctree::
   :maxdepth: 2

   installation
   guide
   consumer
   deployment
   monitoring
   imports
   shared_resources
   signals
   api
   contrib
   troubleshooting
   recipes
   changes

Huey is named in honor of my cat

.. image:: https://m.charlesleifer.com/t/800x-/blog/photos/p1473037658.76.jpg?key=mD9_qMaKBAuGPi95KzXYqg


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

