.. _mini:

Mini-Huey
---------

:py:class:`MiniHuey` provides a very lightweight huey-like API that may be
useful for certain classes of applications. Unlike :py:class:`Huey`, the
``MiniHuey`` consumer runs inside a greenlet in your main application process.
This means there is no separate consumer process to run, not is there any
persistence for the enqueued/scheduled tasks; whenever a task is enqueued or is
scheduled to run, a new greenlet is spawned to execute the task.

Usage and task declaration:

.. py:class:: MiniHuey([name='huey'[, interval=1[, pool_size=None]]])

    :param str name: Name given to this huey instance.
    :param int interval: How frequently to check for scheduled tasks (seconds).
    :param int pool_size: Limit number of concurrent tasks to given size.

.. code-block:: python

    from huey import crontab
    from huey.contrib.minimal import MiniHuey


    huey = MiniHuey()

    @huey.task()
    def fetch_url(url):
        return urllib2.urlopen(url).read()

    @huey.task(crontab(minute='0', hour='4'))
    def run_backup():
        pass

.. note::
    There is not a separate decorator for *periodic*, or *crontab*, tasks. Just
    use :py:meth:`MiniHuey.task` and pass in a validation function.

When your application starts, be sure to start the ``MiniHuey`` scheduler:

.. code-block:: python

    from gevent import monkey; monkey.patch_all()

    huey.start()  # Kicks off scheduler in a new greenlet.
    start_wsgi_server()  # Or whatever your main application is doing...

.. warning::
    Tasks enqueued manually for immediate execution will be run regardless of
    whether the scheduler is running. If you want to be able to schedule tasks
    in the future or run periodic tasks, you will need to call
    :py:meth:`~MiniHuey.start`.

Calling tasks and getting results works about the same as regular huey:

.. code-block:: python

    async_result = fetch_url('https://www.google.com/')
    html = async_result.get()  # Block until task is executed.

    # Fetch the Yahoo! page in 30 seconds.
    async_result = fetch_url.schedule(args=('https://www.yahoo.com/',),
                                      delay=30)
    html = async_result.get()  # Blocks for ~30s.
