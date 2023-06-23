.. _asyncio:

AsyncIO
-------

While Huey does not provide first-class support for a full asyncio pipeline, in
practice one of the most useful locations to be "async"-friendly is when
blocking while waiting for a task result to be ready. When waiting for a task
result, Huey must poll the storage backend to determine if the result is ready
which means lots of opportunity for an asynchronous solution.

In order to simplify this, Huey provides two helpers for ``await``-ing task
results:

.. py:function:: aget_result(result, backoff=1.15, max_delay=1.0, preserve=False)

    :param Result result: a result handle returned when calling a task.
    :return: task return value.

    AsyncIO helper for awaiting the result of a task execution.

    Example:

    .. code-block:: python

        @huey.task()
        def sleep(n):
            time.sleep(n)
            return n

        async def main():
            # Single task, will finish in ~2 seconds (other coroutines can run
            # during this time!).
            rh = sleep(2)
            result = await aget_result(rh)

            # Awaiting multiple results. This will also finish in ~2 seconds.
            r1 = sleep(2)
            r2 = sleep(2)
            r3 = sleep(2)
            results = await asyncio.gather(
                aget_result(r1),
                aget_result(r2),
                aget_result(r3))


.. py:function:: aget_result_group(rg, *args, **kwargs)

    :param ResultGroup rg: a result-group handle for multiple tasks.
    :return: return values for all tasks in the result group.

    AsyncIO helper for awaiting the result of multiple task executions.

    Example:

    .. code-block:: python

        @huey.task()
        def sleep(n):
            time.sleep(n)
            return n

        async def main():
            # Spawn 3 "sleep" tasks, each sleeping for 2 seconds.
            rg = sleep.map([2, 2, 2])

            # Await the results. This will finish in ~2 seconds while also
            # allowing other coroutines to run.
            results = await aget_result_group(rg)
