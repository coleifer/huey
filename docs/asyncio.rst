.. _asyncio:

AsyncIO
-------

Huey does not support a full asyncio pipeline. It provides two helpers for
``await``-ing task results, which poll the storage backend until the result is
ready. For a complete example of using Huey in an async web application, see
:ref:`recipe-fastapi`.

.. py:function:: aget_result(res, backoff=1.15, max_delay=1.0, preserve=False, timeout=None)

    :param Result res: a result handle returned when calling a task.
    :param timeout: seconds to wait before raising :py:class:`ResultTimeout`.
    :return: task return value.

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

            # Give up after 5 seconds.
            try:
                result = await aget_result(sleep(10), timeout=5)
            except ResultTimeout:
                ...


.. py:function:: aget_result_group(rg, *args, **kwargs)

    :param ResultGroup rg: a result-group handle for multiple tasks.
    :return: return values for all tasks in the result group.

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
