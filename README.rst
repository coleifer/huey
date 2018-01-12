huey - a little task queue
==========================

.. image:: http://media.charlesleifer.com/blog/photos/huey-logo.png

a lightweight alternative.

* written in python (2.7+, 3.4+)
* optional dependency on the Python Redis client

supports:

* multi-process, multi-thread or greenlet task execution models
* schedule tasks to execute at a given time, or after a given delay
* schedule recurring tasks, like a crontab
* retry tasks that fail automatically
* task result storage
* task locking
* task pipelines and chains

.. image:: http://i.imgur.com/2EpRs.jpg

.. image:: https://api.travis-ci.org/coleifer/huey.svg?branch=master

Huey's API
----------

.. code-block:: python

    from huey import RedisHuey, crontab

    huey = RedisHuey('my-app', host='redis.myapp.com')

    @huey.task()
    def add_numbers(a, b):
        return a + b

    @huey.periodic_task(crontab(minute='0', hour='3'))
    def nightly_backup():
        sync_all_data()

To run the consumer with 4 worker processes:

.. code-block:: console

    $ huey_consumer.py my_app.huey -k process -w 4

To enqueue a task to add two numbers and print the result:

.. code-block:: python

    res = add_numbers(1, 2)  # Enqueues task.
    print(res.get())  # Prints "3".

To schedule two numbers to be added in 10 seconds:

.. code-block:: python

    res = add_numbers.schedule(args=(1, 2), delay=10)

    # Attempt to get result without blocking.
    print(res.get(False))  # returns None.

    # Block until result is ready and print.
    print(res.get())  # after 10 seconds, prints "3".

Brokers
-------

To use Huey with Redis (**recommended**):

.. code-block:: python

    from huey import RedisHuey

    huey = RedisHuey()

To use Huey with SQLite (`docs <http://huey.readthedocs.io/en/latest/contrib.html#sqlite-storage>`_):

.. code-block:: python

    from huey.contrib.sqlitedb import SqliteHuey

    huey = SqliteHuey('my-app-queue.db')

To run Huey within the parent process using background greenlets (`docs <http://huey.readthedocs.io/en/latest/contrib.html#mini-huey>`_):

.. code-block:: python

    from huey.contrib.minimal import MiniHuey

    huey = MiniHuey()
    huey.start()  # Spawns scheduler background thread and returns immediately.

To run Huey with a simple Python broker (**should not be used in production**):

.. code-block:: python

    from huey.contrib.simple_storage import SimpleHuey

    huey = SimpleHuey()

    # Be sure to run the Python broker process, e.g.:
    # $ python huey/contrib/simple.py  # Starts Python broker.

Documentation
----------------

`See Huey documentation <https://huey.readthedocs.io/>`_.

Project page
---------------

`See source code and issue tracker on Github <https://github.com/coleifer/huey/>`_.

Huey is named in honor of my cat:

.. image:: http://m.charlesleifer.com/t/800x-/blog/photos/p1473037658.76.jpg?key=mD9_qMaKBAuGPi95KzXYqg

