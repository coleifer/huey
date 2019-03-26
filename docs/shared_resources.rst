.. _shared_resources:

Managing shared resources
=========================

Tasks frequently need to make use of shared resources from the application,
such as a database connection.

The simplest approach is to simply manage the connection yourself. For example,
Peewee database connections can be used as a context manager, so if we need to
run some queries inside a task, we might write:

.. code-block:: python

    database = peewee.PostgresqlDatabase('my_app')
    huey = RedisHuey()

    @huey.task()
    def check_comment_spam(comment_id):
        with database:
            comment = Comment.get(Comment.id == comment_id)

            if akismet.is_spam(comment.body):
                comment.is_spam = True
                comment.save()

Another option would be to write a decorator that acquires the shared resource
before calling the task function, and then closes it after the task has
finished. To make this a little simpler, Huey provides a special helper
:py:meth:`Huey.closing_task` decorator that will call ``open()`` on the given
object at the start of a task, and ``close()`` after the task has finished
(regardless of whether an exception occurred).

First let's define a helper class that implements ``open()`` and ``close()``
for managing a Postgres database connection:

.. code-block:: python

    # Postgres DB used by our app.
    db = peewee.PostgresqlDatabase('my_app')

    # Simple wrapper that implements open/close methods.
    class DBResource(object):
        def __init__(self, db):
            self.db = db
        def open(self):
            if not self.db.is_closed():
                self.db.connect()
        def close(self):
            self.db.close()

    db_res = DBResource(db)

Now we can use the :py:meth:`Huey.closing_task` decorator to manage our
database resource during the execution of a task:

.. code-block:: python

    huey = RedisHuey()

    @huey.closing_task(db_res)
    def generate_report(report_date, company_id):
        # At this point, db_res.open() has been called and we can assume
        # that our database connection is now ready to use.

        # Do some database stuff, etc...
        query = ...
        n_records = ...

        # Once our task returns, the db_res.close() method will be called.
        return n_records

Pre and post execute hooks
--------------------------

TODO

Startup hooks
-------------

Another option is to use a connection pool, but where would the pool be
initialized? Bear in mind that the consumer may be configured to run workers as
separate processes, and sharing a connection pool across processes will not
work.
