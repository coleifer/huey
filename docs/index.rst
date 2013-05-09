.. huey documentation master file, created by
   sphinx-quickstart on Wed Nov 16 12:48:28 2011.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

huey, a little task queue
=========================

a lightweight alternative.

* written in python
* no deps outside stdlib, except redis (or roll your own backend)
* support for django

supports:

* multi-threaded task execution
* scheduled execution at a given time
* periodic execution, like a crontab
* retrying tasks that fail
* task result storage


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


named after my cat

.. image:: http://media.charlesleifer.com/blog/photos/thumbnails/IMG_20130402_154858_650x650.jpg


Contents:

.. toctree::
   :maxdepth: 2

   installation
   upgrading
   getting-started
   consumer
   imports
   troubleshooting
   django
   api



Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

