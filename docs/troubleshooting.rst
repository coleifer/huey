.. _troubleshooting:

Troubleshooting and Common Pitfalls
===================================

This document outlines some of the common pitfalls you may encounter when
getting set up with huey.  It is arranged in a problem/solution format.

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
