.. _troubleshooting:

Troubleshooting and Common Pitfalls
===================================

This document outlines some of the common pitfalls you may encounter when
getting set up with huey.  It is arranged in a problem/solution format.

Tasks not running
    First step is to enable logging if you haven't already by adding a ``LOGFILE``
    setting to the configuration.  Check for any exceptions.  The most common cause
    of tasks not running is that they are not being loaded, in which case you will
    see :py:class:`QueueException` "XXX not found in CommandRegistry" errors.

"QueueException: XXX not found in CommandRegistry" in log file
    Exception occurs when a command is called by a task producer, but is not imported
    by the consumer when it loads the configuration file.  To fix this, ensure that 
    by loading the config file you also import any :py:func:`queue_command` decorated 
    functions as well.  If using Django, ensure that your commands in are modules 
    named ``commands.py`` and their app is in ``INSTALLED_APPS``.
    
    For more information on how commands are imported, see the :ref:`docs <imports>`

"Unable to import XXX" when starting consumer
    This error message occurs when the module containing the configuration
    specified cannot be loaded (not on the pythonpath, mistyped, etc).  One
    quick way to check is to open up a python shell and try to import the
    configuration.

    Example syntax: ``huey_consumer.py main_module.Configuration``

'Missing module-level "XXX"' when starting consumer
    This occurs when the module containing the configuration was loaded
    successfully, but the actual configuration class could not be found.
    Ensure the configuration object exists in the module you're trying to
    import from.

    Example syntax: ``huey_consumer.py main_module.Configuration``

Tasks not returning results
    Ensure that you have configured a ``RESULT_STORE``

Periodic tasks are not being executed
    Ensure that ``PERIODIC = True`` in your configuration

Periodic tasks are being executed multiple times per-interval
    If you are running multiple consumer processes, it means that more than one
    of them is also enqueueing periodic tasks.  To fix, create a separate config
    that has ``PERIODIC = True`` and only run it with one consumer.

Scheduled tasks are not being run at the correct time
    Check the time on the server the consumer is running on - if different from
    the producer this may cause problems.  By default all local times are converted
    to UTC when calling ``.schedule()``, and the consumer runs with ``UTC = True``
    by default.
