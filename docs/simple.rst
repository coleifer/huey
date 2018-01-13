.. _simple:

Simple Server
-------------

Huey provides a simple client/server database that can be used for development
and testing. The server design is inspired by `redis <https://redis.io>`_ and
implements commands that map to the methods described by the storage API. If
you'd like to read a technical post about the implementation, check out
`this blog post <http://charlesleifer.com/blog/building-a-simple-redis-server-with-python/>`_.

The server can optionally use `gevent <https://www.gevent.org/>`_, but if
gevent is not available you can use threads (use ``-t`` for threads).

Running the simple server
^^^^^^^^^^^^^^^^^^^^^^^^^

Usage::

    Usage: simple.py [options]

    Options:
      -h, --help            show this help message and exit
      -d, --debug           Log debug messages.
      -e, --errors          Log error messages only.
      -t, --use-threads     Use threads instead of gevent.
      -H HOST, --host=HOST  Host to listen on.
      -m MAX_CLIENTS, --max-clients=MAX_CLIENTS
                            Maximum number of clients.
      -p PORT, --port=PORT  Port to listen on.
      -l LOG_FILE, --log-file=LOG_FILE
                            Log file.

By default the server will listen on localhost, port 31337.

Example (with logging)::

    $ python simple.py --debug --log-file=/var/log/huey-simple.log


Using simple server with Huey
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

To use the simple server with Huey, use the :py:class:`SimpleHuey` class:

.. code-block:: python

    from huey.contrib.simple_storage import SimpleHuey


    huey = SimpleHuey('my-app')

    @huey.task()
    def add(a, b):
        return a + b

The :py:class:`SimpleHuey` class relies on a :py:class:`SimpleStorage` storage
backend, which in turn, uses the ``simple.Client`` client class.


Using stand-alone
^^^^^^^^^^^^^^^^^

To interact directly with the simple server, there is a Python client in the
``huey.contrib.simple`` module.

The server is capable of storing the following data-types natively:

* strings and/or binary data
* numerical values
* null
* lists (may be nested)
* dictionaries (may be nested)

.. py:class:: Client([host='127.0.0.1'[, port=31337]])

    Client for interacting with the simple server.

    :param host: Host the server is running on.
    :param port: Port the server is running on.

    .. py:method:: connect()

        Connect to the server.

        .. note:: Must be called before using any client methods.

    .. py:method:: enqueue(queue, data)

        Add data to a FIFO queue.

        :param str queue: queue name.
        :param data: one of the supported data-types.

    .. py:method:: dequeue(queue)

        Pop data from a FIFO queue.

        :param str queue: queue name.
        :returns: oldest data that was inserted into the queue or ``None`` if
            the queue is empty.

    .. py:method:: unqueue(queue, data)

        Remove the data from the queue, if present in the queue.

        :param str queue: queue name.
        :param data: one of the supported data-types.
        :returns: number of items removed.

    .. py:method:: queue_size(queue)

        :param str queue: queue name.
        :returns: number of items in the queue.

    .. py:method:: flush_queue(queue)

        Clear all items from the queue.

        :param str queue: queue name.
        :returns: number of items removed from the queue.

    .. py:method:: add_to_schedule(data, ts)

        Add timestamped data to the schedule.

        :param data: one of the supported data-types.
        :param datetime ts: timestamp associated with the data.

    .. py:method:: read_schedule(ts)

        Read the schedule and return any data whose timestamp is older-than or
        equal-to the given timestamp.

        Once an item has been read from the schedule, it is removed.

        :param datetime ts: timestamp associated with the data.
        :returns: a list of scheduled data.

    .. py:method:: schedule_size()

        :returns: number of items in schedule.

    .. py:method:: schedule_size()

        :returns: number of items in schedule.

    .. py:method:: flush_schedule()

        Clear all scheduled data.

        :returns: number of items removed.

    .. py:method:: set(key, value)

        Put data in the key/value store.

        :param key: string key.
        :param value: one of the supported data-types.
        :returns: 1 on success

    .. py:method:: get(key)

        Non-destructively read data from the key/value store.

        :param key: string key.
        :returns: data associated with key or ``None`` if key not found.

    .. py:method:: pop_data(key)

        Destructively read data from the key/value store.

        :param key: string key.
        :returns: data associated with key or ``None`` if key not found.

    .. py:method:: mset([__data=None[, **kwargs]])

        Insert multiple key/value pairs into the database. This method may be
        called with either a dictionary or using keyword-arguments.

        :returns: Number of items set.

    .. py:method:: mget(*keys)

        Non-destructively read multiple keys and return a list containing the
        associated value. If a key does not exist, then it's value will be
        ``None``.

        :returns: List of data at each of the given keys.

    .. py:method:: mpop(*keys)

        Destructively read multiple keys and return a list containing the
        associated value. If a key does not exist, then it's value will be
        ``None``.

        :returns: List of data at each of the given keys.

    .. py:method:: has_data_for_key(key)

        :returns: Boolean indicating if the key exists.

    .. py:method:: put_if_empty(key, value)

        Store the key/value pair only if the key does not already exist.

        :returns: 1 on success, 0 if key already existed.

    .. py:method:: result_store_size()

        :returns: number of key/value pairs stored.

    .. py:method:: flush_results()

        Clear all key/value pairs.

        :returns: number of key/value pairs removed.

    .. py:method:: flush_all()

        Flush all queues, schedule and key/value pairs.
