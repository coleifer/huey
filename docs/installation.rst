.. _installation:

Installing
==========

huey can be installed from PyPI using ``pip``:

.. code-block:: shell

    pip install huey

huey has no dependencies outside the standard library, but `redis-py <https://github.com/andymccurdy/redis-py>`_
is required to utilize Redis for your task storage:

.. code-block:: shell

    pip install redis

If your tasks are IO-bound rather than CPU-bound, you might consider using the
``greenlet`` worker type. To use the greenlet workers, you need to
install ``gevent``:

.. code-block:: shell

    pip install gevent

Using git
---------

If you want to run the very latest, you can clone the `source repo <https://github.com/coleifer/huey>`_
and install the library:

.. code-block:: shell

    git clone https://github.com/coleifer/huey.git
    cd huey
    python setup.py install

You can run the tests using the test-runner:

.. code-block:: shell

    python setup.py test

The source code is available at: https://github.com/coleifer/huey
