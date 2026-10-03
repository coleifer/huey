.. _changes:

Changes in 3.0
==============

The 3.0 release of Huey is API-compatible with the previous versions. The main
change is the addition of new features:

* :py:class:`chord` and :py:class:`group` - :ref:`description <groups-and-chords>`
* :ref:`task timeouts <task-timeouts>`
* :ref:`rate limiting <rate-limiting>`
* low-latency result notification (Redis-only) via ``notify_result=True``.
* removed Python 2.x compatibility.

Changes in 2.0
==============

The 2.0 release of Huey is mostly API-compatible with previous versions.

.. warning::
    The serialization format for tasks has changed. An attempt has been made to
    provide backward compatibility when reading messages enqueued by an older
    version of Huey, but this is not guaranteed to work.

Summary
-------

The ``always_eager`` mode has been renamed :ref:`immediate`. As the new name
implies, tasks are run immediately instead of being enqueued. Immediate mode is
designed to be used during testing and development. When immediate mode is
enabled, Huey switches to using in-memory storage by default, so as to avoid
accidental writes to a live storage. Immediate mode improves greatly on
``always_eager`` mode, as it no longer requires special-casing and follows the
same code-paths used when Huey is in live mode. See :ref:`immediate` for more
details.

Previously, the Huey consumer accepted options to run in UTC or local-time.
Various APIs, particularly around scheduling and task revocation, needed to be
compatible with however the consumer was configured, and it could easily get
confusing. As of 2.0, UTC-vs-localtime is specified when instantiating Huey,
and all conversion happens internally, which should make things easier to
think about.

The events APIs have been removed and replaced by a :ref:`signals` system.
Signal handlers are executed synchronously by the worker(s) as they run, which
is easier to use than the events API. That API used a pub/sub approach and
required a dedicated listener thread to make any use of it.

Errors are no longer stored in a separate list. Should a task fail due to an
unhandled exception, the exception will be placed in the result store, and can
be introspected using the task's :py:class:`Result` handle.

Huey now supports :ref:`priority`. To use priorities with Redis, you need to be
running Redis 5.0 or newer, and should use :py:class:`PriorityRedisHuey`. The
original :py:class:`RedisHuey` continues to support older versions of Redis.
:py:class:`SqliteHuey` and the in-memory storage provide full support for task
priorities.

Details
-------

Changes when initializing :py:class:`Huey`:

* ``result_store`` parameter has been renamed to ``results``.
* ``events`` parameter is removed.
* ``store_errors`` parameter is removed. Also the ``max_errors`` parameter of
  the Redis storage engine is removed.
* ``global_registry`` parameter is removed. Tasks are registered to the Huey
  instance with which they are decorated, rather than to a global registry.
* ``always_eager`` has been renamed ``immediate``.

New initialization arguments:

* Boolean ``utc`` parameter (defaults to true). This setting is used to control
  how Huey interprets datetimes internally. Previously, this logic was spread
  across a number of APIs and a consumer flag.
* Serializer parameter accepts an (optional) object implementing the
  :py:class:`Serializer` interface. Defaults to using ``pickle``.
* Accepts option to use gzip ``compression`` when serializing data.

Other changes to :py:class:`Huey`:

* Immediate mode can be enabled or disabled at runtime by setting the
  :py:attr:`~Huey.immediate` property.
* Special classes of exceptions for the various storage operations have been
  removed. For more information see :ref:`exceptions`.
* The ``Huey.errors()`` method is gone.

Changes to the :py:meth:`~Huey.task` and :py:meth:`~Huey.periodic_task`
decorators:

* Previously these decorators accepted two optional keyword arguments,
  ``retries_as_argument`` and ``include_task``. Since the remaining retries are
  stored as an attribute on the task itself, the first is redundant. In 2.0
  these are replaced by a new keyword argument ``context``, which, if ``True``,
  will pass the task instance to the decorated function as a keyword argument.
* Enqueueing a task pipeline will now return a :py:class:`ResultGroup` instead
  of a list of individual :py:class:`Result` instances.

Changes to the :py:class:`Result` handle (previous called
``TaskResultWrapper``):

* The ``task_id`` property is renamed to ``id``.
* Task instances that are revoked via :py:meth:`Result.revoke` will default to
  using ``revoke_once=True``.
* The :py:meth:`~Result.reschedule` method no longer requires a delay or eta.
  Leaving both empty will reschedule the task immediately.

Changes to :py:func:`crontab`:

* The order of arguments has been changed to match the order used on linux
  crontab. The order is now minute, hour, day, month, day of week.

Miscellaneous:

* ``RedisHuey`` defaults to using a blocking pop on the queue, which should
  improve latency and reduce chatter. To go back to the old polling default,
  specify ``blocking=False`` when creating your huey instance.
* ``SqliteHuey`` no longer has any third-party dependencies and has been moved
  into the main ``huey`` module.
* The :py:class:`MiniHuey` contrib module has been renamed to
  ``huey.contrib.mini``.
* The ``SimpleStorage`` contrib module has been removed.

Django-specific:

* The ``backend_class`` setting has been renamed to ``huey_class`` (used to
  specify import-path to Huey implementation, e.g. ``huey.RedisHuey``).
