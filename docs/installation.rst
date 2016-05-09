.. _installation:

Installing
==========

huey can be installed from PyPI using `pip <http://www.pip-installer.org/en/latest/index.html>`_.

.. code-block:: bash

    $ pip install huey

huey has no dependencies outside the standard library, but currently the only
fully-implemented storage backend it ships with requires `redis <http://redis.io>`_.
To use the redis backend, you will need to install the Redis python client:

.. code-block:: bash

    $ pip install redis

If your tasks are IO-bound rather than CPU-bound, you might consider using the ``greenlet`` worker
type. To use the greenlet workers, you need to install ``gevent``:

.. code-block:: bash

    pip install gevent

Using git
---------

If you want to run the very latest, you can clone the `source
repo <https://github.com/coleifer/huey>`_ and install the library:

.. code-block:: bash

    $ git clone https://github.com/coleifer/huey.git
    $ cd huey
    $ python setup.py install

You can run the tests using the test-runner:

.. code-block:: bash

    $ python setup.py test

The source code is available online at https://github.com/coleifer/huey
