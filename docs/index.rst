.. huey documentation master file, created by
   sphinx-quickstart on Wed Nov 16 12:48:28 2011.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

huey, a little task queue
=========================

.. image:: http://media.charlesleifer.com/blog/photos/huey-logo.png

a lightweight alternative, huey is:

* written in python
* only dependency is the Python Redis client
* clean and simple APIs

huey supports:

* multi-process, multi-thread or greenlet task execution models
* schedule tasks to execute at a given time, or after a given delay
* schedule recurring tasks, like a crontab
* retry tasks that fail automatically
* task result storage
* consumer event streaming

.. image:: http://i.imgur.com/2EpRs.jpg

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

Huey is named in honor of my cat

.. image:: http://m.charlesleifer.com/t/800x-/blog/photos/p1473037658.76.jpg?key=mD9_qMaKBAuGPi95KzXYqg

Contents:

.. toctree::
   :maxdepth: 2

   installation
   getting-started
   tasks
   consumer
   events
   imports
   troubleshooting
   api
   django



Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

