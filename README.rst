.. image:: http://media.charlesleifer.com/blog/photos/huey2-logo.png

*a lightweight alternative*.

huey is:

* a task queue (**2019-04-01**: `version 2.0 released <https://huey.readthedocs.io/en/latest/changes.html>`_)
* written in python (2.7+, 3.4+)
* clean and simple API
* redis, sqlite, or in-memory storage
* `example code <https://github.com/coleifer/huey/tree/master/examples/>`_.

huey supports:

* multi-process, multi-thread or greenlet task execution models
* schedule tasks to execute at a given time, or after a given delay
* schedule recurring tasks, like a crontab
* automatically retry tasks that fail
* task prioritization
* task result storage
* task locking
* task pipelines and chains

.. image:: http://i.imgur.com/2EpRs.jpg

.. image:: https://api.travis-ci.org/coleifer/huey.svg?branch=master

At a glance
-----------

.. code-block:: python

    from huey import RedisHuey, crontab

    huey = RedisHuey('my-app', host='redis.myapp.com')

    @huey.task()
    def add_numbers(a, b):
        return a + b

    @huey.task(retries=2, retry_delay=60)
    def flaky_task(url):
        # This task might fail, in which case it will be retried up to 2 times
        # with a delay of 60s between retries.
        return this_might_fail(url)

    @huey.periodic_task(crontab(minute='0', hour='3'))
    def nightly_backup():
        sync_all_data()

Calling a ``task``-decorated function will enqueue the function call for
execution by the consumer. A special result handle is returned immediately,
which can be used to fetch the result once the task is finished:

.. code-block:: pycon

    >>> from demo import add_numbers
    >>> res = add_numbers(1, 2)
    >>> res
    <Result: task 6b6f36fc-da0d-4069-b46c-c0d4ccff1df6>

    >>> res()
    3

Tasks can be scheduled to run in the future:

.. code-block:: pycon

    >>> res = add_numbers.schedule((2, 3), delay=10)  # Will be run in ~10s.
    >>> res(blocking=True)  # Will block until task finishes, in ~10s.
    5

For much more, check out the `guide <https://huey.readthedocs.io/en/latest/guide.html>`_
or take a look at the `example code <https://github.com/coleifer/huey/tree/master/examples/>`_.

Running the consumer
^^^^^^^^^^^^^^^^^^^^

Run the consumer with four worker processes:

.. code-block:: console

    $ huey_consumer.py my_app.huey -k process -w 4

To run the consumer with a single worker thread (default):

.. code-block:: console

    $ huey_consumer.py my_app.huey

If your work-loads are mostly IO-bound, you can run the consumer with threads
or greenlets instead. Because greenlets are so lightweight, you can run quite a
few of them efficiently:

.. code-block:: console

    $ huey_consumer.py my_app.huey -k greenlet -w 32

Storage
-------

Huey's design and feature-set were informed by the capabilities of the
`Redis <https://redis.io>`_ database. Redis is a fantastic fit for a
lightweight task queueing library like Huey: it's self-contained, versatile,
and can be a multi-purpose solution for other web-application tasks like
caching, event publishing, analytics, rate-limiting, and more.

Although Huey was designed with Redis in mind, the storage system implements a
simple API and many other tools could be used instead of Redis if that's your
preference.

Huey comes with builtin support for Redis, Sqlite and in-memory storage.

Documentation
----------------

`See Huey documentation <https://huey.readthedocs.io/>`_.

Project page
---------------

`See source code and issue tracker on Github <https://github.com/coleifer/huey/>`_.

Huey is named in honor of my cat:

.. image:: http://m.charlesleifer.com/t/800x-/blog/photos/p1473037658.76.jpg?key=mD9_qMaKBAuGPi95KzXYqg

