huey - a little task queue
==========================

.. image:: http://media.charlesleifer.com/blog/photos/huey-logo.png

a lightweight alternative.

* written in python
* only dependency is the Python Redis client

supports:

* multi-process, multi-thread or greenlet task execution models
* schedule tasks to execute at a given time, or after a given delay
* schedule recurring tasks, like a crontab
* retry tasks that fail automatically
* task result storage

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


Documentation
----------------

`See Huey documentation <https://huey.readthedocs.io/>`_.

Project page
---------------

`See source code and issue tracker on Github <https://github.com/coleifer/huey/>`_.

Huey is named in honor of my cat:

.. image:: http://media.charlesleifer.com/blog/photos/thumbnails/IMG_20130402_154858_650x650.jpg

