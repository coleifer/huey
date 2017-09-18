Changelog
=========

v1.4.2 (unreleased)
-------------------

[View commits](https://github.com/coleifer/huey/compare/1.4.1...HEAD)

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
