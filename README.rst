huey - a little task queue
==========================

.. image:: http://i.imgur.com/2EpRs.jpg

a lightweight alternative.

* written in python
* support for django
* no deps outside the standard lib, except Redis (or you can roll your own backend)

supports:

* multi-threaded task execution
* scheduled execution at a given time
* periodic execution, like a crontab
* retrying tasks that fail
* task result storage

named after my cat:

.. image:: http://charlesleifer.com/docs/huey/_images/huey.jpg
