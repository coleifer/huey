.. _installation:

Installing
==========

huey can be installed from PyPI using ``pip``:

.. code-block:: shell

    pip install huey

huey has no dependencies outside the standard library. The sqlite, file-system
and in-memory storage layers work out-of-the-box. The others need a client
library, which is most easily installed using the matching extra:

.. code-block:: shell

    # redis-py, to use Redis (or Valkey / Redict) for task storage.
    pip install huey[redis]

    # psycopg 3.2 or newer, to use Postgres for task storage.
    pip install huey[postgres]

    # cysqlite, to use CySqliteHuey instead of SqliteHuey.
    pip install huey[cysqlite]

    # peewee, for the task statistics recorder and admin dashboards.
    pip install huey[stats]

These pull in `redis-py <https://github.com/redis/redis-py>`_,
`psycopg <https://www.psycopg.org/>`_,
`cysqlite <https://cysqlite.readthedocs.io/>`_ and
`peewee <https://docs.peewee-orm.com/>`_ respectively, and may equally be
installed by name.

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
    pip install .

You can run the tests using the test-runner:

.. code-block:: shell

    python runtests.py
