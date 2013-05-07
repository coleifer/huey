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
    see :py:class:`QueueException` "XXX not found in TaskRegistry" errors.

"QueueException: XXX not found in CommandRegistry" in log file
    Exception occurs when a task is called by a task producer, but is not imported
    by the consumer.  To fix this, ensure that by loading the :py:class:`Huey` object,
    you also import any decorated functions as well.

    For more information on how tasks are imported, see the :ref:`docs <imports>`

"Error importing XXX" when starting consumer
    This error message occurs when the module containing the configuration
    specified cannot be loaded (not on the pythonpath, mistyped, etc).  One
    quick way to check is to open up a python shell and try to import the
    configuration.

    Example syntax: ``huey_consumer.py main_module.huey``

Tasks not returning results
    Ensure that you have specified a ``result_store`` when creating your
    :py:class:`Huey` object.

Periodic tasks are being executed multiple times per-interval
    If you are running multiple consumer processes, it means that more than one
    of them is also enqueueing periodic tasks.  To fix, only run one consumer
    with ``--periodic`` and run the others with ``--no-periodic``.

Scheduled tasks are not being run at the correct time
    Check the time on the server the consumer is running on - if different from
    the producer this may cause problems.  By default all local times are converted
    to UTC when calling ``.schedule()``, and the consumer runs in UTC.
