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
    
    .. py:method:: get([blocking=False[, timeout=None[, backoff=1.15[, max_delay=1.0]]]])
    
        Attempt to retrieve the return value of a task.  By default, it will simply
        ask for the value, returning ``None`` if it is not ready yet.  If you want
        to wait for a value, you can specify ``blocking = True`` -- this will loop,
        backing off up to the provided ``max_delay`` until the value is ready or
        until the ``timeout`` is reached.  If the ``timeout`` is reached before the
        result is ready, a :py:class:`DataStoreTimeout` exception will be raised.
        
        :param blocking: boolean, whether to block while waiting for task result
        :param timeout: number of seconds to block for (used with `blocking=True`)
        :param backoff: amount to backoff delay each time no result is found
        :param max_delay: maximum amount of time to wait between iterations when
            attempting to fetch result.

Configuration
-------------

.. py:module:: huey.bin.config

.. py:class:: BaseConfiguration()

    Applications using huey should subclass ``BaseConfiguration`` when specifying
    the configuration options to use.  ``BaseConfiguration`` is where the queue,
    result store, and many other settings are configured.  The configuration is
    then used by the consumer to access the queue.  All configuration settings
    are class attributes.
    
    .. py:attribute:: QUEUE
    
        An instance of a ``Queue`` class, which must be a subclass of :py:class:`BaseQueue`.
        Tells consumer what queue to pull messages from.
    
    .. py:attribute:: RESULT_STORE
    
        An instance of a ``DataStore`` class, which must be a subclass of :py:class:`DataStore` or ``None``.
        Tells consumer where to store results of messages.
    
    .. py:attribute:: TASK_STORE
    
        An instance of a ``DataStore`` class, which must be a subclass of :py:class:`DataStore` or ``None``.
        Tells consumer where to serialize the schedule of pending tasks in the event the consumer is
        shut down unexpectedly.
    
    .. py:attribute:: PERIODIC = False
    
        A boolean value indicating whether the consumer should enqueue periodic tasks
    
    .. py:attribute:: THREADS = 1
    
        Number of worker threads to run

    .. py:attribute:: LOGFILE = None
    .. py:attribute:: LOGLEVEL = logging.INFO
    .. py:attribute:: BACKOFF = 1.15
    .. py:attribute:: INITIAL_DELAY = .1
    .. py:attribute:: MAX_DELAY = 10
    .. py:attribute:: UTC = True
    
        Whether to run using local ``now()`` or ``utcnow()`` when determining
        times to execute periodic commands and scheduled commands.

Queues and DataStores
---------------------

Huey communicates with two types of data stores -- queues and datastores.  Thinking
of them as python datatypes, a queue is sort of like a ``list`` and a datastore is
sort of like a ``dict``.  Queues are FIFOs that store tasks -- producers put tasks
in on one end and the consumer reads and executes tasks from the other.  DataStores
are key-based stores that can store arbitrary results of tasks keyed by task id.
DataStores can also be used to serialize task schedules so in the event your consumer
goes down you can bring it back up and not lose any tasks that had been scheduled.

Huey, like just about a zillion other projects, uses a "pluggable backend" approach,
where the interface is defined on a couple classes :py:class:`BaseQueue` and :py:class:`BaseDataStore`,
and you can write an implementation for any datastore you like.  The project ships
with backends that talk to `redis <http://redis.io>`_, a fast key-based datastore,
but the sky's the limit when it comes to what you want to interface with.  Below is
an outline of the methods that must be implemented on each class.

Base classes
^^^^^^^^^^^^

.. py:module:: huey.backends.base

.. py:class:: BaseQueue(name, **connection)

    Queue implementation -- any connections that must be made should be created
    when instantiating this class.
        
    :param name: A string representation of the name for this queue
    :param connection: Connection parameters for the queue
    
    .. py:attribute:: blocking = False
    
        Whether the backend blocks when waiting for new results.  If set to ``False``,
        the backend will be polled at intervals, if ``True`` it will read and wait.
    
    .. py:method:: write(data)
    
        Write data to the queue - has no return value.
        
        :param data: a string
    
    .. py:method:: read()
        
        Read data from the queue, returning None if no data is available --
        an empty queue should not raise an Exception!
        
        :rtype: a string message or ``None`` if no data is present
    
    .. py:method:: flush()
    
        Optional: Delete everything in the queue -- used by tests
    
    .. py:method:: __len__()
    
        Optional: Return the number of items in the queue -- used by tests

.. py:class:: BaseDataStore(name, **connection)

    Data store implementation -- any connections that must be made should be created
    when instantiating this class.
    
    :param name: A string representation of the name for this data store
    :param connection: Connection parameters for the data store

    .. py:method:: put(key, value)
    
        Store the ``value`` using the ``key`` as the identifier
    
    .. py:method:: get(key)
        
        Retrieve the value stored at the given ``key``, returns a special value
        :py:class:`EmptyData` if no data exists at the given key.  This is to
        differentiate between "no data" and a stored ``None`` value.
        
        .. warning:: After a result is fetched it should be removed from the store!
    
    .. py:method:: flush()
    
        Remove all keys

Redis implementation
^^^^^^^^^^^^^^^^^^^^

All the following use the `python redis driver <https://github.com/andymccurdy/redis-py>`_
written by Andy McCurdy.

.. py:module:: huey.backends.redis_backend

.. py:class:: RedisQueue(name, **connection)

    Does a simple ``RPOP`` to pull messages from the queue, meaning that it polls.

    :param name: the name of the queue to use
    :param connection: a list of values passed directly into the ``redis.Redis`` class

.. py:class:: RedisBlockingQueue(name, **connection)

    Does a ``BRPOP`` to pull messages from the queue, meaning that it blocks on reads.

    :param name: the name of the queue to use
    :param connection: a list of values passed directly into the ``redis.Redis`` class

.. py:class:: RedisDataStore(name, **connection)

    Stores results in a redis hash using ``HSET``, ``HGET`` and ``HDEL``

    :param name: the name of the data store to use
    :param connection: a list of values passed directly into the ``redis.Redis`` class


.. _django-api:

Django API
==========

Good news, the django api is considerably simpler!  This is because django has
very specific conventions for how things should be configured.  If you're using
django you don't have to worry about invokers or configuration objects -- simply
configure the queue and result store in the settings and use the decorators and
management command to run the consumer.

Function decorators and helpers
-------------------------------

.. py:module:: huey.djhuey.decorators

.. py:function:: queue_command()

    Identical to the :py:func:`~huey.decorators.queue_command` described above,
    except that it takes no parameters.
    
    .. code-block:: python
    
        from huey.djhuey.decorators import queue_command
        
        @queue_command
        def count_some_beans(how_many):
            return 'Counted %s beans' % how_many

.. py:function:: periodic_command(validate_datetime)

    Identical to the :py:func:`~huey.decorators.periodic_command` described above,
    except that it does not take an invoker as its first argument.
    
    .. code-block:: python
    
        from huey.djhuey.decorators import periodic_command, crontab
        
        @periodic_command(crontab(minute='*/5'))
        def every_five_minutes():
            # this function gets executed every 5 minutes by the consumer
            print "It's been five minutes"

Configuration
-------------

All configuration occurs in the django settings module.  Settings are configured
using the same names as those in the python api with the exception that queues and
data stores can be specified using a string module path, and connection keyword-arguments
are specified using a dictionary.

Example configuration:

.. code-block:: python

    HUEY_CONFIG = {
        'QUEUE': 'huey.backends.redis_backend.RedisQueue',
        'QUEUE_CONNECTION': {
            'host': 'localhost',
            'port': 6379
        },
        'THREADS': 4,
    }

Required settings
^^^^^^^^^^^^^^^^^

``QUEUE`` (string or ``Queue`` instance)
    Either a queue instance or a string pointing to the module path and class
    name of the queue.  If a string is used, you may also need to specify a
    connection parameters.
    
    Example: ``huey.backends.redis_backend.RedisQueue``


Recommended settings
^^^^^^^^^^^^^^^^^^^^

``QUEUE_NAME`` (string), default = database name

``QUEUE_CONNECTION`` (dictionary)
    If the ``QUEUE`` was specified using a string, use this parameter to
    instruct the queue class how to connect.

``RESULT_STORE`` (string or ``DataStore`` instance)
    Either a ``DataStore`` instance or a string pointing to the module path and
    class name of the result store.
    
    Example: ``huey.backends.redis_backend.RedisDataStore``

``RESULT_STORE_NAME`` (string), default = database name

``RESULT_STORE_CONNECTION`` (dictionary)
    See notes for ``QUEUE_CONNECTION``

``TASK_STORE``
    Follows same pattern as ``RESULT_STORE``


Optional settings
^^^^^^^^^^^^^^^^^

``PERIODIC`` (boolean), default = False
    Determines whether or not to the consumer will enqueue periodic commands.
    If you are running multiple consumers, only one of them should be configured
    to enqueue periodic commands.

``THREADS`` (int), default = 1
    Number of worker threads to use when processing jobs

``LOGFILE`` (string), default = None

``LOGLEVEL`` (int), default = logging.INFO

``BACKOFF`` (numeric), default = 1.15
    How much to increase delay when no jobs are present

``INITIAL_DELAY`` (numeric), default = 0.1
    Initial amount of time to sleep when waiting for jobs

``MAX_DELAY`` (numeric), default = 10
    Max amount of time to sleep when waiting for jobs

``ALWAYS_EAGER``, default = ``False``
    Whether to skip enqueue-ing and run in-band (useful for debugging)
