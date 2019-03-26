.. huey documentation master file, created by
   sphinx-quickstart on Wed Nov 16 12:48:28 2011.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

huey, a little task queue
=========================

.. image:: http://media.charlesleifer.com/blog/photos/huey-logo.png

a lightweight alternative, huey is:

* written in python (2.7+, 3.4+)
* clean and simple APIs
* redis, sqlite, or in-memory storage

huey supports:

* multi-process, multi-thread or greenlet task execution models
* schedule tasks to execute at a given time, or after a given delay
* schedule recurring tasks, like a crontab
* automatically retry tasks that fail
* task result storage
* task locking
* task pipelines and chains

.. image:: http://i.imgur.com/2EpRs.jpg

At a glance
-----------

Use the :py:meth:`~Huey.task` and :py:meth:`~Huey.periodic_task` decorators to
turn functions into tasks that will be run by the consumer:

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

To run the consumer with a single worker thread:

.. code-block:: console

    $ huey_consumer.py my_app.huey

Here's how to run the consumer with four worker processes (good setup for
CPU-intensive processing):

.. code-block:: console

    $ huey_consumer.py my_app.huey -k process -w 4

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

Table of contents
-----------------

.. toctree::
   :maxdepth: 2

   installation
   quickstart
   consumer
   imports
   troubleshooting
   signals
   shared_resources
   api
   contrib

Huey is named in honor of my cat

.. image:: http://m.charlesleifer.com/t/800x-/blog/photos/p1473037658.76.jpg?key=mD9_qMaKBAuGPi95KzXYqg


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

