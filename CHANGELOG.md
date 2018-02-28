Changelog
=========

v1.7.1 (unreleased)
-------------------

[View commits](https://github.com/coleifer/huey/compare/1.7.0...HEAD)

v1.7.0
------

[View commits](https://github.com/coleifer/huey/compare/1.6.1...1.7.0)

#### Backwards-incompatible change

Previous versions of huey would store the traceback and associated metadata for
a failed task within the `result_store`, regardless of whether `store_errors`
was true or not. As of 1.7.0, task exceptions will only be stored in the result
store if `store_errors` is True. See #290 for discussion.

v1.6.1
------

[View commits](https://github.com/coleifer/huey/compare/1.6.0...1.6.1)

* Add backwards-compatibility to queue serialization protocol so that 1.6
  consumers can continue to work with tasks enqueued by huey versions 1.5 and
  lower.


v1.6.0
------

[View commits](https://github.com/coleifer/huey/compare/1.5.6...1.6.0)

* Support for [task pipelining](http://huey.readthedocs.io/en/latest/getting-started.html#task-pipelines) and task function partials
  (which is not compatible with 1.5's task serialization format see note below).
* Support for triggering task retries using `RetryTask` exception.
* Support for task locking, restricting concurrency of a given task.
* Getting result of task that failed with an exception results in a `TaskException` being raised.
* Updated health check to ensure the task scheduler is always running.
* Refactor implementation of `task()` and `periodic_task()` decorators, which should have the added benefit of making them easier to extend.
* Refactored result-store APIs to simplify serialization / deserialization logic.
* Fixed bug in serialization of task exceptions.
* Added simple client/server implementation for testing locally. [Blog post on the subject](http://charlesleifer.com/blog/building-a-simple-redis-server-with-python/).

#### Task serialization format

In v1.6.0, the serialization format of tasks has changed to accomodate an extra
piece of metadata. As a result, tasks enqueued with huey versions previous to
1.6 will not be able to be consumed by the 1.6 consumer.

At present there is a workaround available in 1.6.1, but it will be removed
when 1.7.0 is released later.

v1.5.6
------

[View commits](https://github.com/coleifer/huey/compare/1.5.5...1.5.6)

* Allow arbitrary settings to be specified in ``task()`` decorators.
* New task name format includes function module as part of task name.
* Fix for operating systems that do not implement SIGHUP.
* Fix bug in `contrib.minimal` task scheduler timing.

v1.5.5
------

[View commits](https://github.com/coleifer/huey/compare/1.5.4...1.5.5)

* Implemented [pre-execute](http://huey.readthedocs.io/en/latest/api.html#Huey.register_pre_execute)
  and [post-execute](http://huey.readthedocs.io/en/latest/api.html#Huey.register_pre_execute)
  hooks.
* Implemented task cancellation mechanism as part of pre-execute hooks.

v1.5.4
------

[View commits](https://github.com/coleifer/huey/compare/1.5.3...1.5.4)

* Implemented atomic "set if not exists" for Redis and SQLite, which is used by
  the locking APIs.

v1.5.3
------

[View commits](https://github.com/coleifer/huey/compare/1.5.2...1.5.3)

* Includes addition of `TaskLock` and `Huey.lock_task()` helpers.
* Extend `Huey` API to add method for creating the consumer.

v1.5.2
------

[View commits](https://github.com/coleifer/huey/compare/1.5.1...1.5.2)

* Added support for gracefully restarting the consumer using SIGHUP.
* Fixed a bug where periodic tasks were not being given unique task IDs when
  executed by the consumer. Periodic tasks now receive a unique ID each time
  they are invoked.

v1.5.1
------

[View commits](https://github.com/coleifer/huey/compare/1.5.0...1.5.1)

Added support for specifying a `retry` and `retry_delay` on periodic tasks.
Simply pass the desired values into the `periodic_task()` decorator after the
validation function, as keyword arguments.

v1.5.0
------

[View commits](https://github.com/coleifer/huey/compare/1.4.1...1.5.0)

* Allow all instances of a task to be revoked/restored by adding the
  `revoke()`, `restore()` and `is_revoked()` methods to all decorated tasks
  (where previously they were only available on periodic tasks).
* Periodic task instances now have a unique identifier.
* Added documentation on how to correctly use the Django consumer management
  command with the `gevent` worker model.
* Logging will lazily resolve log messages.
* Bug was fixed that prevented the local (non-global) task registry from
  working as intended. This is now fixed.
* Docstrings added to the `BaseStorage` APIs.

Thanks to @mindojo-victor and @nachtmaar for help with some of the above items.

v1.4.1
------

[View commits](https://github.com/coleifer/huey/compare/1.4.0...1.4.1)

* Support using `7` to represent *Sunday* when doing day-of-week calculations
  in the `crontab` helper.
* Fix bug #243, wherein Django interpreted boolean CLI arguments as having a
  boolean default value.


v1.4.0
------

[View commits](https://github.com/coleifer/huey/compare/1.3.1...1.4.0)

Fixed a subtle bug in the way Huey calculated when to run the periodic task
scheduler. If you had configured the consumer to check the schedule at an
interval that was not a factor of 60, then there is a chance that periodic
tasks may be scheduled at incorrect intervals from one minute to the next. This
is fixed in 1.4.0.

Added better signal handling in order to support graceful shutdown. Graceful
shutdown involves letting workers finish executing any tasks they may be
processing at the time the shutdown signal is received. The default behavior is
to interrupt the workers mid-task. Huey uses `SIGTERM` to shutdown the
consumer immediately, and `SIGINT` to gracefully shutdown.

Added support for using either a global task registry, or a registry bound to
a particular `Huey` instance. The default behavior is to use a global registry
(backwards-compatible). To bind the registry to a single `Huey` instance, pass
`global_registry=False` when initializing your `Huey` object.

Added a `reschedule()` method to the `TaskResultWrapper`.

Documentation clean-ups and additions, particularly around the logic used to
handle datetime conversion. Also added docs on shutdown modes for huey
consumer.

v1.3.1
------

[View commits](https://github.com/coleifer/huey/compare/1.3.0...1.3.1)

Smarter conversion between datetimes, so that huey will correctly interpret
naive or timezone-aware datetimes and properly convert to UTC when configured
to do so. Previously, huey only operated on naive datetimes. Many thanks to
@Antoine for this patch-set.

Documentation clean-ups and additions.

v1.3.0
------

[View commits](https://github.com/coleifer/huey/compare/1.2.3...1.3.0)

Adds flag to preserve result-store value in certain circumstances. Contains yet
more hacking at the consumer configuration options, specifically hard-coded
defaults are removed from the option definitions.

The `run_huey` management command was simplified as we are dropping support for
older (officially unsupported) versions of Django.

Added a `sqlitedb` contrib module that uses a local SQLite database instead of
Redis for Queue persistence, task scheduling and result-storage.

v1.2.3
------

[View commits](https://github.com/coleifer/huey/compare/1.2.2...1.2.3)

Contains an attempt at fixing the django management command handling of the
`default` option.

v1.2.2
------

[View commits](https://github.com/coleifer/huey/compare/1.2.0...1.2.2)

Contains small bugfix for an earlier bugfix meant to prevent time.sleep() from
being called with a negative time interval.

v1.2.0
------

[View commits](https://github.com/coleifer/huey/compare/1.1.2...1.2.0)

Removed the metadata APIs added in 1.1.0, as they seemed poorly-designed and
altogether a decent idea terribly implemented. Perhaps something I'll revisit,
but which should be easy to implement as a third-party library using the events
APIs.

* `AsyncData` is renamed to `TaskResultWrapper`.
* `Huey.result()` is a new method that provides the result of a task, given a
  task ID.
* Fixed a handful of bugs related to the error serialization.
* Change the default consumer log handler from RotatingFileHandler to the
  vanilla FileHandler class.

v1.1.2
------

[View commits](https://github.com/coleifer/huey/compare/1.1.1...1.1.2)

I've added a new API for fetching a task's result given on the task's ID. You
can now call `huey.result(task_id)` and retrieve the result if the task has
finished executing. Additionally, the [Huey.result](https://huey.readthedocs.io/en/latest/api.html#Huey.result)
method accepts the same parameters as [AsyncData.get](https://huey.readthedocs.io/en/latest/api.html#AsyncData.get),
allowing you to block for results, specify a timeout, etc.

There is also a new parameter on the above methods, ``preserve=False``. By
default, the result store will delete a task result once it has been read. Specifying
``preserve=True`` ensures the data is not removed.

v1.1.1
------

[View commits](https://github.com/coleifer/huey/compare/1.1.0...1.1.1)

This is a small release with a couple minor bugfixes.

* Fixed task metadata serialization bug. #140
* Small cleanup to event iterator storage implementation.
* Updated [getting started documentation](https://huey.readthedocs.io/en/latest/getting-started.html)
  to reflect changes in the 1.x APIs.

v1.1.0
------

* Big changes to simplify the way ``Huey`` is instantiated. No changes should
  be necessary if already using ``RedisHuey``.
* Refactored the storage APIs and simplified the public interface. There is
  now a single object, whereas before there were 4 components (queue, result
  store, scheduler and event emitter).
* Added methods for retrieving and introspecting the pending task queue, the
  schedule, results, and errors.
* Errors can now be stored, in addition to regular task results.
* Added metadata methods for tracking task execution, errors, task duration,
  and more. These will be the building blocks for tools to provide some
  insight into the inner-workings of your consumers and producers.
* Many new events are emitted by the consumer, and some have parameters. These
  are documented [here](https://huey.readthedocs.io/en/latest/events.html).

v1.0.0
------

What follows is a description of the changes between 0.4.9 and 1.0.0. There are
some backwards-incompatible changes to be aware of as well as new options for
the consumer. Most APIs are the same, however.


Backwards incompatible changes:

* ``huey.djhuey`` moved to ``huey.contrib.djhuey``. You will need to update
  any import statements as well as your Django ``INSTALLED_APPS`` setting to
  reflect the new module path.
* Redis backend is now the only one available, and the corresponding code moved
  from ``huey.backends.redis_backend`` to ``huey.storage``.
* Removed the "RabbitMQ" and "SQLite" queue backends.
* Removed the ``-t`` and ``--threads`` option from the consumer. You should now
  use ``-w`` or ``--workers``.
* Removed the ``-p`` and ``--periodic`` no-op options from the consumer. These
  are enabled by default so the option had no meaning.
* The ``scheduler-interval`` option is configured using ``-s`` when previously
  it was ``-S``. Furthermore, this must be a value between 1 and 60.
* Removed the ``peewee_helpers`` module.


New features:

* The queue consumer now supports multi-process or multi-greenlet execution
  models (in addition to multi-threaded, which previously was the only option).
* Added `pending()`, `scheduled()` and `all_results()` methods to the `Huey`
  class to allow introspection of the Queue's state at the current moment in
  time.
