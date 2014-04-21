huey - a little task queue
==========================

.. image:: http://i.imgur.com/2EpRs.jpg

a lightweight alternative.

* written in python
* no deps outside the standard lib, except Redis (or you can roll your own backend)
* support for Django

supports:

* multi-threaded task execution
* scheduled execution at a given time
* periodic execution, like a crontab
* retrying tasks that fail
* task result storage

Huey's API
----------

::

    from huey import RedisHuey, crontab

    huey = RedisHuey('my-app', host='redis.myapp.com')

    @huey.task()
    def add_numbers(a, b):
        return a + b

    @huey.periodic_task(crontab(minute='0', hour='3'))
    def nightly_backup():
        sync_all_data()


Documentation
----------------

`See Huey documentation <http://huey.readthedocs.org/>`_.

Project page
---------------

`See source code and issue tracker on Github <https://github.com/coleifer/huey/>`_.

named after my cat:

.. image:: http://media.charlesleifer.com/blog/photos/thumbnails/IMG_20130402_154858_650x650.jpg

