.. _sqlite:

SQLite Storage
--------------

The :py:class:`SqliteHuey` and the associated :py:class:`SqliteStorage` can be
used instead of the default :py:class:`RedisHuey`. :py:class:`SqliteHuey` is
implemented in such a way that it can safely be used with a multi-process,
multi-thread, or multi-greenlet consumer.

Using ``SqliteHuey`` is almost exactly the same as using :py:class:`RedisHuey`.
Begin by instantiating the ``Huey`` object, passing in the name of the queue
**and the filename** of the SQLite database:

.. code-block:: python

    from huey.contrib.sqlitedb import SqliteHuey

    huey = SqliteHuey('my_app', filename='/var/www/my_app/huey.db')
