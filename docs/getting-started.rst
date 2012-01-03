.. _getting-started:

Getting Started
===============

The goal of this document is to help you get running quickly and with as little
fuss as possible.  Because huey works with python in general but also has some
special integration, this guide is broken up into two parts:

* :ref:`getting-started-python <Standard guide>`
* :ref:`getting-started-django <Getting started, Django edition>`


.. _getting-started-python

Getting started, python
-----------------------

There are three main components (or processes) to consider when running huey:

* the producer(s), i.e. a web application
* the consumer(s), which executes jobs placed into the queue
* the queue where tasks are stored, e.g. Redis

These three processes are shown in the screenshot below -- the left-hand pane
shows the producer: a simple program that asks the user for input on how many 
"beans" to count.  In the top-right, the consumer is running.  It is doing the 
actual "computation" and simply printing the number of beans counted.  In the 
bottom-right is the queue, Redis in this example, which we're monitoring and
shows tasks being enqueued (``LPUSH``) and read (``BRPOP``) from the database.

.. image:: example.jpg


Trying it out yourself
^^^^^^^^^^^^^^^^^^^^^^

Assuming you've got :ref:`huey installed <installation>`, let's look at the code
from this example.

The first step is to configure your queue.  The consumer needs to be pointed at
a subclass of :py:class:`BaseConfiguration`, which specifies things like the backend to
use, where to log activity, etc.

.. code-block:: python

    # config.py
    from huey.backends.redis_backend import RedisBlockingQueue
    from huey.bin.config import BaseConfiguration
    from huey.queue import Invoker


    queue = RedisBlockingQueue('test-queue', host='localhost', port=6379)
    invoker = Invoker(queue)


    class Configuration(BaseConfiguration):
        QUEUE = queue

The interesting parts of this configuration module are the :py:class:`Invoker` object
and the :py:class:`RedisBlockingQueue` object.  The ``queue`` is responsible for 
storing and retrieving messages, and the ``invoker`` is used by your application 
code to coordinate function calls with a queue backend.  We'll see how the ``invoker`` 
is used when looking at the actual function responsible for counting beans:

.. code-block:: python

    # commands.py
    from huey.decorators import queue_command

    from config import invoker # import the invoker we instantiated in config.py


    @queue_command(invoker)
    def count_beans(num):
        print 'Counted %s beans' % num

The above example shows the API for writing "commands" that are executed by the
queue consumer -- simply decorate the code you want executed by the consumer
with the :py:func:`queue_command` decorator and when it is called, the main
process will return *immediately* after enqueueing the function call.  The
``invoker`` is passed in to the decorator, which instructs huey where to send
the message.

The main executable is very simple.  It imports both the configuration **and**
the commands - this is to ensure that when we run the consumer by pointing it
at the configuration, the commands are also imported and loaded into memory.

.. code-block:: python

    # main.py
    from config import Configuration # import the configuration class
    from commands import count_beans # import our command


    if __name__ == '__main__':
        beans = raw_input('How many beans? ')
        count_beans(int(beans))
        print 'Enqueued job to count %s beans' % beans

To run these scripts, follow these steps:

1. Ensure you have `Redis <http://redis.io>`_ running locally
2. Ensure you have :ref:`installed huey <installation>`
3. Start the consumer: ``huey_consumer.py main.Configuration``
4. Run the main program: ``python main.py``


Getting results from jobs
^^^^^^^^^^^^^^^^^^^^^^^^^

The above example illustrates a "send and forget" approach, but what if your
application needs to do something with the results of a task?  To get results 
from your tasks, we'll set up the ``RedisDataStore`` by adding the following
lines to the ``config.py`` module:

.. code-block:: python

    from huey.backends.redis_backend import RedisBlockingQueue, RedisDataStore
    from huey.bin.config import BaseConfiguration
    from huey.queue import Invoker


    queue = RedisBlockingQueue('test-queue', host='localhost', port=6379)
    result_store = RedisDataStore('results', host='localhost', port=6379) # new

    invoker = Invoker(queue, result_store=result_store) # added result store


    class Configuration(BaseConfiguration):
        QUEUE = queue
        RESULT_STORE = result_store # added

To better illustrate getting results, we'll also modify the ``commands.py``
module to return a string rather than simply printing to stdout:

.. code-block:: python

    from huey.decorators import queue_command

    from config import invoker


    @queue_command(invoker)
    def count_beans(num):
        return 'Counted %s beans' % num # changed "print" to "return"

We're ready to fire up the consumer.  Instead of simply executing the main
program, though, we'll start an interpreter and run the following:

.. code-block:: python

    >>> from main import count_beans
    >>> res = count_beans(100)
    >>> res # <--- what is "res" ?
    <huey.queue.AsyncData object at 0xb7471a4c>
    >>> res.get() # <--- get the result of this task
    'Counted 100 beans'

Following the same layout as our last example, here is a screenshot of the three
main processes at work:

1. Top-left, interpreter which produces a job then asks for the result
2. Top-right, the consumer which runs the job and stores the result
3. Bottom-right, the Redis database, which we can see is storing the results and
   then deleting them after they've been retrieved

.. image:: example_results.jpg


.. _getting-started-django

Getting started, Django
-----------------------


