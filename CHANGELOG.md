Changelog
=========

## master

[View commits](https://github.com/coleifer/huey/compare/2.3.1...HEAD)

## 2.3.1

* Add `SIGNAL_INTERRUPTED` to signal when a task is interrupted when a consumer
  exits abruptly.
* Use the `Huey.create_consumer()` API within the Django management command, to
  allow Django users to customize the creation of the `Consumer` instance.

[View commits](https://github.com/coleifer/huey/compare/2.3.0...2.3.1)

## 2.3.0

* Use monotonic clock for timing operations within the consumer.
* Ensure internal state is cleaned up on file-lock when released.
* Support passing around TaskException as a pickled value.
* Set the multiprocessing mode to "fork" on MacOS and Python 3.8 or newer.
* Added option to enforce FIFO behavior when using Sqlite as storage.
* Added the `on_shutdown` handler to djhuey namespace.
* Ensure exception is set on AsyncResult in mini-huey.

[View commits](https://github.com/coleifer/huey/compare/2.2.0...2.3.0)

## 2.2.0

* Fix task `repr` (refs #460).
* Adds task-id into metadata for task exceptions (refs #461).
* Ensure database connection is not closed when using the `call_local` method
  of Django helper extension `db_periodic_task()`.
* Allow pickle protocol to be explicitly configured in serializer parameters.
* Adds `FileHuey` and full `FileStorage` implementation.
* Add `shutdown()` hook, which will be run in the context of the worker
  threads/processes during shutdown. This hook can be used to clean-up shared
  or global resources, for example.
* Allow pipelines to be chained together. Additionally, support chaining task
  instances.

[View commits](https://github.com/coleifer/huey/compare/2.1.3...2.2.0)

## 2.1.3

* Fix semantics of `SIGNAL_COMPLETE` so that it is not sent until the result is
  ready.
* Use classes for the specific Huey implementations (e.g. `RedisHuey`) so that
  it is easier to subclass / extend. Previously we just used a partial
  application of the constructor, which could be confusing.
* Fix shutdown logic in consumer when using multiprocess worker model.
  Previously the consumer would perform a "graceful" shutdown, even when an
  immediate shutdown was requested (SIGTERM). Also cleans up the
  signal-handling code and ensures that interrupted tasks log a warning
  properly to indicate they were interrupted.

[View commits](https://github.com/coleifer/huey/compare/2.1.2...2.1.3)

## 2.1.2

* Allow `AsyncResult` object used in `MiniHuey` to support the `__call__()`
  method to block and resolve the task result.
* When running the django `run_huey` management command, the huey loggers will
  not be configured if another logging handler is already registered to the
  huey namespace.
* Added experimental contrib storage engine using `kyoto tycoon <http://fallabs.com/kyototycoon>`_
  which supports task priority and the option to do automatic result
  expiration. Requires the `ukt <https://github.com/coleifer/ukt>`_ python
  package and a custom kyototycoon lua script.
* Allow the Sqlite storage engine busy timeout to be configured when
  instantiating `SqliteHuey`.

[View commits](https://github.com/coleifer/huey/compare/2.1.1...2.1.2)

## 2.1.1

* Ensure that `task()`-decorated functions retain their docstrings.
* Fix logger setup so that the consumer log configuration is only applied to
  the `huey` namespace, rather than the root logger.
* Expose `result`, `signal` and `disconnect_signal` in the Django huey
  extension.
* Add `SignedSerializer`, which signs and validates task messages.
* Refactor the `SqliteStorage` so that it can be more easily extended to
  support other databases.

[View commits](https://github.com/coleifer/huey/compare/2.1.0...2.1.1)

## 2.1.0

* Added new contrib module `sql_huey`, which uses `peewee <https://github.com/coleifer/peewee>`_
  to provide storage layer using any of the supported databases (sqlite, mysql
  or postgresql).
* Added `RedisExpireHuey`, which modifies the usual Redis result storage logic
  to use an expire time for task result values. A consequence of this is that
  this storage implementation must keep all result keys at the top-level Redis
  keyspace. There are some small changes to the storage APIs as well, but will
  only possibly affect maintainers of alternative storage layers.
* Also added a `PriorityRedisExpireHuey` which combines the priority-queue
  support from `PriorityRedisHuey` with the result-store expiration mechanism
  of `RedisExpireHuey`.
* Fix gzip compatibility issue when using Python 2.x.
* Add option to `Huey` to use `zlib` as the compression method instead of gzip.
* Added `FileStorageMethods` storage mixin, which uses the filesystem for task
  result-store APIs (put, peek, pop).
* The storage-specific `Huey` implementations (e.g. `RedisHuey`) are no longer
  subclasses, but instead are partial applications of the `Huey` constructor.

[View commits](https://github.com/coleifer/huey/compare/2.0.1...2.1.0)

### 2.0.1

* Small fixes, fixed typo in Exception class being caught by scheduler.

[View commits](https://github.com/coleifer/huey/compare/2.0.0...2.0.1)

# 2.0.0

This section describes the changes in the 2.0.0 release. A detailed list of
changes can be found here: https://huey.readthedocs.io/en/latest/changes.html

Overview of changes:

* `always_eager` mode has been renamed to `immediate` mode. Unlike previous
  versions, `immediate` mode involves the same code paths used by the consumer
  process. This makes it easier to test features like task revocation and task
  scheduling without needing to run a dedicated consumer process. Immediate
  mode uses an in-memory storage layer by default, but can be configured to use
  "live" storage like Redis or Sqlite.
* The events stream API has been removed in favor of simpler callback-driven
  [signals](https://huey.readthedocs.io/en/latest/signals.html) APIs. These
  callbacks are executed synchronously within the huey consumer process.
* A new serialization format is used in 2.0.0, however consumers running 2.0
  will continue to be able to read and deserialize messages enqueued by Huey
  version 1.11.0 for backwards compatibility.
* Support for [task priorities](https://huey.readthedocs.io/en/latest/guide.html#task-priority).
* New `Serializer` abstraction allows users to customize the serialization
  format used when reading and writing tasks.
* Huey consumer and scheduler can be more easily run within the application
  process, if you prefer not to run a separate consumer process.
* Tasks can now specify an `on_error` handler, in addition to the
  previously-supported `on_complete` handler.
* Task pipelines return a special `ResultGroup` object which simplifies reading
  the results of a sequence of task executions.
* `SqliteHuey` has been promoted out of `contrib`, onto an equal footing with
  `RedisHuey`. To simplify deployment, the dependency on
  [peewee](https://github.com/coleifer/peewee) was removed and the Sqlite
  storage engine uses the Python `sqlite3` driver directly.

[View commits](https://github.com/coleifer/huey/compare/1.11.0...2.0.0)

## 1.11.0

**Backwards-incompatible changes**

Previously, it was possible for certain tasks to be silently ignored if a task
with that name already existed in the registry. To fix this, I have made two
changes:

1. The task-name, when serialized, now consists of the task module and the name
   of the decorated function. So, "queue_task_foo" becomes "myapp.tasks.foo".
2. An exception will be raised when attempting to register a task function with
   the same module + name.

Together, these changes are intended to fix problems described in #386.

Because these changes will impact the serialization (and deserialization) of
messages, **it is important that you consume all tasks (including scheduled
tasks) before upgrading**.

**Always-eager mode changes**

In order to provide a more consistent API, tasks enqueued using `always_eager`
mode will now return a dummy `TaskResultWrapper` implementation that wraps the
return value of the task. This change is designed to provide the same API for
reading task result values, regardless of whether you are using always-eager
mode or not.

Previously, tasks executed with `always_eager` would return the Python value
directly from the task. When using Huey with the consumer, though, task results
are not available immediately, so a special wrapper `TaskResultWrapper` is
returned, which provides helper methods for retrieving the return value of the
task. Going forward, `always_eager` tasks will return `EagerTaskResultWrapper`,
which implements the same `get()` API that is typically used to retrieve task
return values.

[View commits](https://github.com/coleifer/huey/compare/1.10.5...1.11.0)

### v1.10.5

* Compatibility with redis-py 3.0, updated requirements / dependencies.
* Add pre-/post- hooks into the djhuey namespace.

[View commits](https://github.com/coleifer/huey/compare/1.10.4...1.10.5)

### v1.10.4

* Log time taken to execute tasks at default log level.
* Fix missing import in SQLite storage backend.
* Small refactoring in Redis storage backend to make it easier to override the
  driver / client implementation.
* Fix failing tests for simpledb storage backend.

[View commits](https://github.com/coleifer/huey/compare/1.10.3...1.10.4)

### v1.10.3

* Fixed regression where in *always eager* mode exceptions within tasks were
  being swallowed instead of raised.
* Added an API for registering hooks to run when each worker process starts-up.
  This simplifies creating global/process-wide shared resources, such as a
  connection pool or database client. [Documentation](https://huey.readthedocs.io/en/latest/api.html#Huey.on_startup).

[View commits](https://github.com/coleifer/huey/compare/1.10.2...1.10.3)

### v1.10.2

* More granular "extras" installation options.

[View commits](https://github.com/coleifer/huey/compare/1.10.1...1.10.2)

### v1.10.1

* Remove call to SimpleDB Client.connect(), as the `simpledb` APIs have
  changed and no longer use this method.
* Ensure that pre- and post-execute hooks are run when using Huey in
  "always_eager" mode.
* Gracefully stop Huey consumer when SIGINT is received.
* Improved continuous integration, now testing on Python 3.7 as well.

[View commits](https://github.com/coleifer/huey/compare/1.10.0...1.10.1)

## v1.10.0

* Ensure that the default SIGINT handler is registered. This fixes an edge-case
  that arises when the consumer is run without job control, which causes
  interrupt signals to be ignored.
* Restarts (SIGHUP) are now graceful by default.

[View commits](https://github.com/coleifer/huey/compare/1.9.1...1.10.0)

### v1.9.1

* Ensure the scheduler loop does not drift (fixes #304).
* Add `TaskResultWrapper.reset()` to enable resetting the results of tasks that
  failed and are subsequently being retried.
* Allow task-decorated functions to be also decorated as periodic tasks.

[View commits](https://github.com/coleifer/huey/compare/1.9.0...1.9.1)

## v1.9.0

[View commits](https://github.com/coleifer/huey/compare/1.8.0...1.9.0)

#### ROLLBACK of 1.8.0 Django Changes

Due to problems with the django patch that added support for multiple huey
instances, I've decided to rollback those changes.

Django integration in Huey 1.9.0 will work the same as it had previously in
1.7.x and earlier.

Apologies, I should have reviewed the patch more thoroughly and insisted on
better test coverage.

## v1.8.0

[View commits](https://github.com/coleifer/huey/compare/1.7.0...1.8.0)

#### Backwards-incompatible change to Django integration

**NOTE: These changes were remove in 1.9.0**

In 1.8.0, support for multiple huey instances was added (with thanks to @Sebubu
and @MarcoGlauser for the patches). Although existing Django/Huey apps should
continue to work, there is a new configuration format available and I'd
recommend that you take a look at the docs and switch over to it:

[Django integration documentation](http://huey.readthedocs.io/en/latest/contrib.html#django)

## v1.7.0

#### Backwards-incompatible change

Previous versions of huey would store the traceback and associated metadata for
a failed task within the `result_store`, regardless of whether `store_errors`
was true or not. As of 1.7.0, task exceptions will only be stored in the result
store if `store_errors` is True. See #290 for discussion.

[View commits](https://github.com/coleifer/huey/compare/1.6.1...1.7.0)

### v1.6.1

* Add backwards-compatibility to queue serialization protocol so that 1.6
  consumers can continue to work with tasks enqueued by huey versions 1.5 and
  lower.

[View commits](https://github.com/coleifer/huey/compare/1.6.0...1.6.1)

## v1.6.0

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

[View commits](https://github.com/coleifer/huey/compare/1.5.6...1.6.0)

### v1.5.6

* Allow arbitrary settings to be specified in ``task()`` decorators.
* New task name format includes function module as part of task name.
* Fix for operating systems that do not implement SIGHUP.
* Fix bug in `contrib.minimal` task scheduler timing.

[View commits](https://github.com/coleifer/huey/compare/1.5.5...1.5.6)

### v1.5.5

* Implemented [pre-execute](http://huey.readthedocs.io/en/latest/api.html#Huey.register_pre_execute)
  and [post-execute](http://huey.readthedocs.io/en/latest/api.html#Huey.register_pre_execute)
  hooks.
* Implemented task cancellation mechanism as part of pre-execute hooks.

[View commits](https://github.com/coleifer/huey/compare/1.5.4...1.5.5)

### v1.5.4

* Implemented atomic "set if not exists" for Redis and SQLite, which is used by
  the locking APIs.

[View commits](https://github.com/coleifer/huey/compare/1.5.3...1.5.4)

### v1.5.3

* Includes addition of `TaskLock` and `Huey.lock_task()` helpers.
* Extend `Huey` API to add method for creating the consumer.

[View commits](https://github.com/coleifer/huey/compare/1.5.2...1.5.3)

### v1.5.2

* Added support for gracefully restarting the consumer using SIGHUP.
* Fixed a bug where periodic tasks were not being given unique task IDs when
  executed by the consumer. Periodic tasks now receive a unique ID each time
  they are invoked.

[View commits](https://github.com/coleifer/huey/compare/1.5.1...1.5.2)

### v1.5.1

Added support for specifying a `retry` and `retry_delay` on periodic tasks.
Simply pass the desired values into the `periodic_task()` decorator after the
validation function, as keyword arguments.

[View commits](https://github.com/coleifer/huey/compare/1.5.0...1.5.1)

## v1.5.0

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

[View commits](https://github.com/coleifer/huey/compare/1.4.1...1.5.0)

### v1.4.1

* Support using `7` to represent *Sunday* when doing day-of-week calculations
  in the `crontab` helper.
* Fix bug #243, wherein Django interpreted boolean CLI arguments as having a
  boolean default value.

[View commits](https://github.com/coleifer/huey/compare/1.4.0...1.4.1)

## v1.4.0

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

[View commits](https://github.com/coleifer/huey/compare/1.3.1...1.4.0)

### v1.3.1

Smarter conversion between datetimes, so that huey will correctly interpret
naive or timezone-aware datetimes and properly convert to UTC when configured
to do so. Previously, huey only operated on naive datetimes. Many thanks to
@Antoine for this patch-set.

Documentation clean-ups and additions.

[View commits](https://github.com/coleifer/huey/compare/1.3.0...1.3.1)

## v1.3.0

Adds flag to preserve result-store value in certain circumstances. Contains yet
more hacking at the consumer configuration options, specifically hard-coded
defaults are removed from the option definitions.

The `run_huey` management command was simplified as we are dropping support for
older (officially unsupported) versions of Django.

Added a `sqlitedb` contrib module that uses a local SQLite database instead of
Redis for Queue persistence, task scheduling and result-storage.

[View commits](https://github.com/coleifer/huey/compare/1.2.3...1.3.0)

### v1.2.3

Contains an attempt at fixing the django management command handling of the
`default` option.

[View commits](https://github.com/coleifer/huey/compare/1.2.2...1.2.3)

### v1.2.2

Contains small bugfix for an earlier bugfix meant to prevent time.sleep() from
being called with a negative time interval.

[View commits](https://github.com/coleifer/huey/compare/1.2.0...1.2.2)

## v1.2.0

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

[View commits](https://github.com/coleifer/huey/compare/1.1.2...1.2.0)

### v1.1.2

I've added a new API for fetching a task's result given on the task's ID. You
can now call `huey.result(task_id)` and retrieve the result if the task has
finished executing. Additionally, the [Huey.result](https://huey.readthedocs.io/en/latest/api.html#Huey.result)
method accepts the same parameters as [AsyncData.get](https://huey.readthedocs.io/en/latest/api.html#AsyncData.get),
allowing you to block for results, specify a timeout, etc.

There is also a new parameter on the above methods, ``preserve=False``. By
default, the result store will delete a task result once it has been read. Specifying
``preserve=True`` ensures the data is not removed.

[View commits](https://github.com/coleifer/huey/compare/1.1.1...1.1.2)

### v1.1.1

This is a small release with a couple minor bugfixes.

* Fixed task metadata serialization bug. #140
* Small cleanup to event iterator storage implementation.
* Updated [getting started documentation](https://huey.readthedocs.io/en/latest/getting-started.html)
  to reflect changes in the 1.x APIs.

[View commits](https://github.com/coleifer/huey/compare/1.1.0...1.1.1)

## v1.1.0

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

# v1.0.0

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
