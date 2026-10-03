.. _shared_resources:

Managing shared resources
=========================

Tasks may need to make use of shared resources from the application, such as a
database connection or an API client.

The simplest approach is to manage the resource explicitly. For example, Peewee
database connections can be used as a context manager, so if we need to run
some queries inside a task, we might write:

.. code-block:: python

    database = peewee.PostgresqlDatabase('my_app')
    huey = RedisHuey()

    @huey.task()
    def check_comment_spam(comment_id):
        # Open DB connection at start of task, close upon exit.
        with database:
            comment = Comment.get(Comment.id == comment_id)

            if akismet.is_spam(comment.body):
                comment.is_spam = True
                comment.save()

Huey provides a :py:meth:`Huey.context_task` decorator that accepts an object
implementing the context-manager API, and automatically wraps the task within
the given context:

.. code-block:: python

    @huey.context_task(database)
    def check_comment_spam(comment_id):
        comment = Comment.get(Comment.id == comment_id)

        if akismet.is_spam(comment.body):
            comment.is_spam = True
            comment.save()

Startup hooks
-------------

The :py:meth:`Huey.on_startup` decorator is used to register a callback that is
executed once when each worker starts running. This hook provides a convenient
way to initialize shared resources or perform other initializations which
should happen within the context of the worker thread or process.

As an example, suppose many of our tasks will be executing queries against a
Postgres database. Rather than opening and closing a connection for every task,
we will instead open a connection when each worker starts. This connection may
then be used by any tasks that are executed by that consumer:

.. code-block:: python

    import peewee

    db = peewee.PostgresqlDatabase('my_app')

    @huey.on_startup()
    def open_db_connection():
        if not db.is_closed():
            db.close()
        db.connect()

    @huey.task()
    def run_query(n):
        db.execute_sql('select pg_sleep(%s)', (n,))
        return n

The above code works correctly because `peewee <https://github.com/coleifer/peewee>`_
stores connection state in a threadlocal. This is important if we are running
the workers in threads (huey's default).

Pre and post execute hooks
--------------------------

* :py:meth:`Huey.pre_execute` - called right before a task is executed. The
  handler function should accept one argument: the task that will be executed.
  Pre-execute hooks can raise a :py:class:`CancelExecution` exception to
  instruct the consumer that the task should not be run.
* :py:meth:`Huey.post_execute` - called after task has finished. The handler
  function should accept three arguments: the task that was executed, the
  return value, and the exception (if one occurred, otherwise is ``None``).

.. code-block:: python

    from huey import CancelExecution

    @huey.pre_execute()
    def pre_execute_hook(task):
        if datetime.datetime.now().weekday() == 6:
            raise CancelExecution('No tasks on sunday!')

    @huey.post_execute()
    def post_execute_hook(task, task_value, exc):
        if exc is not None:
            print('Task "%s" failed with error: %s!' % (task.id, exc))

.. note::
    Printing the error message is redundant, as the huey logger already logs
    any unhandled exceptions raised by a task, along with a traceback.
