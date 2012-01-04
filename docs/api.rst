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

.. _function-decorators:

Function decorators and helpers
-------------------------------

.. py:module:: huey.decorators

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

    Function decorator that marks the decorated function for processing by the
    consumer *at a specific interval*.  Calls to functions decorated with ``periodic_command``
    will execute normally, unlike :py:func:`queue_command`, which enqueues commands
    for execution by the consumer.  Rather, the ``periodic_command`` decorator
    serves to **mark a function as needing to be executed periodically** by the
    consumer.
    
    .. note::
        By default, the consumer will not execute ``periodic_command`` functions.
        To enable this, simply add ``PERIODIC = True`` to your configuration.

    The ``validate_datetime`` parameter is a function which accepts a datetime
    object and returns a boolean value whether or not the decorated function
    should execute at that time or not.  The consumer will send a datetime to
    the function every minute, giving it the same granularity as the linux
    crontab, which it was designed to mimic.
    
    For simplicity, there is a special function :py:func:`crontab`, which can
    be used to quickly specify intervals at which a function should execute.  It
    is described below.
    
    Here is an example of how you might use the ``periodic_command`` decorator
    and the ``crontab`` helper:
    
    .. code-block:: python
        
        from config import invoker
        from huey.decorators import periodic_command, crontab
        
        @periodic_command(invoker, crontab(minute='*/5'))
        def every_five_minutes():
            # this function gets executed every 5 minutes by the consumer
            print "It's been five minutes"
    
    .. note::
        Because functions decorated with ``periodic_command`` are meant to be
        executed at intervals in isolation, they should not take any required
        parameters nor should they be expected to return a meaningful value.
        This is the same regardless of whether or not you are using a result store.
    
    :param invoker: an :py:class:`Invoker` instance
    :param validate_datetime: a callable which takes a ``datetime`` and returns
        a boolean whether the decorated function should execute at that time or not
    :rtype: decorated function

.. py:function:: crontab(month='*', day='*', day_of_week='*', hour='*', minute='*')

    Convert a "crontab"-style set of parameters into a test function that will
    return ``True`` when a given ``datetime`` matches the parameters set forth in
    the crontab.
    
    Acceptable inputs:
    
    - "*" = every distinct value
    - "\*/n" = run every "n" times, i.e. hours='\*/4' == 0, 4, 8, 12, 16, 20
    - "m-n" = run every time m..n
    - "m,n" = run on m and n
    
    :rtype: a test function that takes a ``datetime`` and returns a boolean

The Invoker and AsyncData classes
---------------------------------

.. py:module:: huey.queue

.. py:class:: Invoker(queue[, result_store=None[, task_store=None[, store_none=False[, always_eager=False]]]])

    The ``Invoker`` ties together your application's queue, result store, and supplies
    some options to configure how tasks are executed and how their results are stored.
    
    Applications will have **at least one** ``Invoker`` instance, as it is required
    by the :ref:`function decorators <function-decorators>`.  Typically it should
    be instantiated along with the ``Queue``, or wherever you create your configuration.
    
    Example:
    
    .. code-block:: python
    
        from huey.backends.redis_backend import RedisBlockingQueue, RedisDataStore
        from huey.queue import Invoker

        queue = RedisBlockingQueue('test-queue', host='localhost', port=6379)
        result_store = RedisDataStore('results', host='localhost', port=6379)

        # Create an invoker instance, which points at the queue and result store
        # which are used by the application's Configuraiton object
        invoker = Invoker(queue, result_store=result_store)

.. py:class:: AsyncData(result_store, task_id)

    Although you will probably never instantiate an ``AsyncData`` object yourself,
    they are returned by any calls to :py:func:`queue_command` decorated functions
    (provided the invoker is configured with a result store).  The ``AsyncData``
    talks to the result store and is responsible for fetching results from tasks.
    Once the consumer finishes executing a task, the return value is placed in the
    result store, allowing the producer to retrieve it.
    
    Working with the ``AsyncData`` class is very simple:
    
    .. code-block:: python
    
        >>> from main import count_some_beans
        >>> res = count_some_beans(100)
        >>> res # <--- what is "res" ?
        <huey.queue.AsyncData object at 0xb7471a4c>
        
        >>> res.get() # <--- get the result of this task, assuming it executed
        'Counted 100 beans'
    
    What happens when data isn't available yet?  Let's assume the next call takes
    about a minute to calculate:
    
    .. code-block:: python
    
        >>> res = count_some_beans(10000000) # let's pretend this is slow
        >>> res.get() # data is not ready, so returns None
        
        >>> res.get() is None # data still not ready
        True
        
        >>> res.get(blocking=True, timeout=5) # block for 5 seconds
        Traceback (most recent call last):
          File "<stdin>", line 1, in <module>
          File "/home/charles/tmp/huey/src/huey/huey/queue.py", line 46, in get
            raise DataStoreTimeout
        huey.exceptions.DataStoreTimeout
        
        >>> res.get(blocking=True) # no timeout, will block until it gets data
        'Counted 10000000 beans'
    
    .. py:method:: get([blocking=True[, timeout=None[, backoff=1.15[, max_delay=1.0]]]])
    
        Attempt to retrieve the return value

.. _django-api:

Django API
----------
