.. _troubleshooting:

Troubleshooting and Common Pitfalls
===================================

This document outlines some of the common pitfalls you may encounter when
getting set up with huey.  It is arranged in a problem/solution format.

Tasks not running
    First step is to increase logging verbosity by running the consumer with
    ``--verbose``.  You can also specify a logfile using the ``--logfile``
    option.

    Check for any exceptions.  The most common cause of tasks not running is
    that they are not being loaded, in which case you will
    see :py:class:`HueyException` "XXX not found in TaskRegistry" errors.

"HueyException: XXX not found in TaskRegistry" in log file
    Exception occurs when a task is called by a task producer, but is not
    imported by the consumer.  To fix this, ensure that by loading the
    :py:class:`Huey` object, you also import any decorated functions as well.

    For more information on how tasks are imported, see the :ref:`import documentation <imports>`.

"Error importing XXX" when starting consumer
    This error message occurs when the module containing the configuration
    specified cannot be loaded (not on the pythonpath, mistyped, etc).  One
    quick way to check is to open up a python shell and try to import the
    configuration.

    Example syntax: ``huey_consumer.py main_module.huey``

Tasks not returning results
    Ensure that you have not accidentally specified ``results=False`` when
    instantiating your :py:class:`Huey` object.

Scheduled tasks are not being run at the correct time
    Check the time on the server the consumer is running on - if different from
    the producer this may cause problems. Huey uses UTC internally by default,
    and naive datetimes will be converted from local time to UTC (if local time
    happens to not be UTC).

Cronjobs are not being run
    The consumer and scheduler run in UTC by default.

Greenlet workers seem stuck
    If you wish to use the Greenlet worker type, you need to be sure to
    monkeypatch in your application's entrypoint. At the top of your ``main``
    module, you can add the following code: ``from gevent import monkey; monkey.patch_all()``.
    Furthermore, if your tasks are CPU-bound, ``gevent`` can appear to lock up
    because it only supports cooperative multi-tasking (as opposed to
    pre-emptive multi-tasking when using threads). For Django, it is necessary
    to apply the patch inside the ``manage.py`` script. See the Django docs
    section for the code.

Testing projects using Huey
    Use ``immediate=True``:

    .. code-block:: python

        test_mode = os.environ.get('TEST_MODE')

        # When immediate=True, Huey will default to using an in-memory
        # storage layer.
        huey = RedisHuey(immediate=test_mode)

        # Alternatively, you can set the `immediate` attribute:
        huey.immediate = True if test_mode else False
