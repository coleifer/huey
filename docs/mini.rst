.. _mini:

Mini-Huey
---------

:py:class:`MiniHuey` provides a very lightweight huey-like API that may be
useful for certain applications. The ``MiniHuey`` consumer runs inside a
greenlet in your main application process.  This means there is no separate
consumer process to manage, nor is there any persistence for the
enqueued/scheduled tasks; whenever a task is enqueued or is scheduled to run, a
new greenlet is spawned to execute the task.

*MiniHuey* may be useful if:

* Your application is a WSGI application.
* Your tasks do stuff like check for spam, send email, make requests to
  web-based APIs, query a database server.
* You do not need automatic retries, persistence for your message queue,
  dynamic task revocation.
* You wish to keep things nice and simple and don't want the overhead of
  additional process(es) to manage.

*MiniHuey* may be a bad choice if:

* Your application is incompatible with gevent (e.g. uses asyncio).
* Your tasks do stuff like process large files, crunch numbers, parse large XML
  or JSON documents, or other CPU or disk-intensive work.
* You need a persistent store for messages and results, so the consumer can be
  restarted without losing any unprocessed messages.

If you are not sure, then you should probably not use *MiniHuey*. Use the
regular :py:class:`Huey` instead.

Usage and task declaration:

.. py:class:: MiniHuey([name='huey'[, interval=1[, pool_size=None]]])

    :param str name: Name given to this huey instance.
    :param int interval: How frequently to check for scheduled tasks (seconds).
    :param int pool_size: Limit number of concurrent tasks to given size.

    .. py:method:: task([validate_func=None])

        Task decorator similar to :py:meth:`Huey.task` or :py:meth:`Huey.periodic_task`.
        For tasks that should be scheduled automatically at regular intervals,
        simply provide a suitable :py:func:`crontab` definition.

        The decorated task will gain a ``schedule()`` method which can be used
        like the :py:meth:`TaskWrapper.schedule` method.

        Examples task declarations:

        .. code-block:: python

            from huey import crontab
            from huey.contrib.mini import MiniHuey

            huey = MiniHuey()

            @huey.task()
            def fetch_url(url):
                return urlopen(url).read()

            @huey.task(crontab(minute='0', hour='4'))
            def run_backup():
                pass

        Example usage. Running tasks and getting results work about the same as
        regular Huey:

        .. code-block:: python

            # Executes the task asynchronously in a new greenlet.
            result = fetch_url('https://google.com/')

            # Wait for the task to finish.
            html = result.get()

        Scheduling a task for execution:

        .. code-block:: python

            # Fetch in ~30s.
            result = fetch_url.schedule(('https://google.com',), delay=30)

            # Wait until result is ready, takes ~30s.
            html = result.get()

    .. py:method:: start()

        Start the scheduler in a new green thread. The scheduler is needed if
        you plan to schedule tasks for execution using the ``schedule()``
        method, or if you want to run periodic tasks.

        Typically this method should be called when your application starts up.
        For example, a WSGI application might do something like:

        .. code-block:: python

            # Always apply gevent monkey-patch before anything else!
            from gevent import monkey; monkey.patch_all()

            from my_app import app  # flask/bottle/whatever WSGI app.
            from my_app import mini_huey

            # Start the scheduler. Returns immediately.
            mini_huey.start()

            # Run the WSGI server.
            from gevent.pywsgi import WSGIServer
            WSGIServer(('127.0.0.1', 8000), app).serve_forever()

    .. py:method:: stop()

        Stop the scheduler.

.. note::
    There is not a separate decorator for *periodic*, or *crontab*, tasks. Just
    use :py:meth:`MiniHuey.task` and pass in a validation function. A
    validation function can be generated using the :py:func:`crontab` function.

.. note::
    Tasks enqueued for immediate execution will be run regardless of whether
    the scheduler is running. You only need to start the scheduler if you plan
    to schedule tasks in the future or run periodic tasks.
