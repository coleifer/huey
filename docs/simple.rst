.. _simple:

Simple Server
-------------

Huey supports a simple client/server database that can be used for development
and testing. The server design is inspired by `redis <https://redis.io>`_ and
implements commands that map to the methods described by the storage API. If
you'd like to read a technical post about the implementation, check out
`this blog post <http://charlesleifer.com/blog/building-a-simple-redis-server-with-python/>`_.

The server can optionally use `gevent <https://www.gevent.org/>`_, but if
gevent is not available you can use threads (use ``-t`` for threads).

To obtain the simple server, you can clone the ``simpledb`` repository:

.. code-block:: console

    $ git clone https://github.com/coleifer/simpledb
    $ cd simpledb
    $ python setup.py install

Running the simple server
^^^^^^^^^^^^^^^^^^^^^^^^^

Usage::

    Usage: simpledb.py [options]

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
      -x EXTENSIONS, --extensions=EXTENSIONS
                            Import path for Python extension module(s).

By default the server will listen on localhost, port 31337.

Example (with logging)::

    $ python simpledb.py --debug --log-file=/var/log/huey-simple.log


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
