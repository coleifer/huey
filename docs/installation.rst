.. _installation:

Installing
==========

huey can be installed very easily using `pip <http://www.pip-installer.org/en/latest/index.html>`_.

.. code-block:: shell

    pip install huey

huey has no dependencies outside the standard library, but currently the only
fully-implemented queue backend it ships with requires [redis](http://redis.io).
To use the redis backend, you will need to install the python client.

.. code-block:: shell

    pip install redis


Using git
---------

If you want to run the very latest, feel free to pull down the repo from github
and install by hand.

.. code-block:: shell

    git clone https://github.com/coleifer/huey.git
    cd huey
    python setup.py install

You can run the tests using the test-runner::

    python setup.py test
