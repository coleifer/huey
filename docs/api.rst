.. _api:

Huey's API
==========

.. note::
    The django API is a slightly simplified version of the general python API.
    For details on using the django API, :ref:`read here <django-api>`

Most end-users will interact with the API using the two decorators in ``huey.decorators``:

* :py:func:`queue_command`
* :py:func:`periodic_command`

Each decorator takes an :py:class:`Invoker` instance -- the Invoker is responsible
for coordinating with the various backends (the message queue, the result store if you're
using one, scheduling commands, etc).  The API documentation will follow the structure
of the huey API, starting with the highest-level interfaces (the decorators) and
eventually discussing the lowest-level interfaces, the :py:class:`BaseQueue` and :py:class:`BaseDataStore` objects.

Function decorators
-------------------

.. py:function:: queue_command(invoker)

    Function decorator that marks the decorated function for processing by the
    consumer.  Calls to the decorated function will do the following:
    
    1. Serialize the function call into a message suitable for storing in the queue
    2. Enqueue the message for execution by the consumer
    3. If a :py:class:`ResultStore` has been configured, return an :py:class:`AsyncData`
       instance which can retrieve the result of the function, or ``None`` if not
       using a result store.
    
    .. note::
        The Invoker can be configured to execute the function immediately by
        instantiating it with ``always_eager = True`` -- this is useful for
        running in debug mode or when you do not wish to run the consumer.
    
    Here is how you might use the ``queue_command`` decorator:
    
    .. code-block:: python
    
        # assume that we've created an invoker alongside the rest of the
        # config
        from config import invoker
        from huey.decorators import queue_command
        
        @queue_command(invoker)
        def count_some_beans(num):
            # do some counting!
            return 'Counted %s beans' % num
    
    Now, whenever you call this function in your application, the actual processing
    will occur when the consumer dequeues the message and your application will
    continue along on its way.
    
    Without a result store:
    
    .. code-block:: python
    
        >>> res = count_some_beans(1000000)
        >>> res is None
        True
    
    With a result store:
    
    .. code-block:: python
    
        >>> res = count_some_beans(1000000)
        >>> res
        <huey.queue.AsyncData object at 0xb7471a4c>
        >>> res.get()
        'Counted 1000000 beans'

    :param invoker: an :py:class:`Invoker` instance
    :rtype: decorated function
    
    The return value of any calls to the decorated function depends on whether the invoker
    is configured with a result store.  If a result store is configured, the
    decorated function will return an :py:class:`AsyncData` object which can fetch the
    result of the call from the result store -- otherwise it will simply
    return ``None``.
    
    The ``queue_command`` decorator also does one other important thing -- it adds
    a special function **onto** the decorated function, which makes it possible
    to *schedule* the execution for a certain time in the future:
    
    .. py:function:: {decorated func}.schedule(args=None, kwargs=None, eta=None, convert_utc=True)
    
        Use the special ``.schedule()`` function to schedule the execution of a
        queue command for a given time in the future:
        
        .. code-block:: python
        
            import datetime
            
            # get a datetime object representing one hour in the future
            in_an_hour = datetime.datetime.now() + datetime.timedelta(seconds=3600)
            
            # schedule "count_some_beans" to run in an hour
            count_some_beans.schedule(args=(100000,), eta=in_an_hour)
    
        :param args: arguments to call the decorated function with
        :param kwargs: keyword arguments to call the decorated function with
        :param eta: a ``datetime`` instance specifying the time at which the
                    function should be executed
        :param convert_utc: whether the ``eta`` should be converted from local
                            time to UTC, defaults to ``True``
        :rtype: like calls to the decorated function, will return an :py:class:`AsyncData`
                object if a result store is configured, otherwise returns ``None``

.. py:function:: periodic_command(invoker, validate_datetime)


.. _django-api:

Django API
----------
