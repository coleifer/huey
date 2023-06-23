import asyncio

from huey.constants import EmptyData


async def aget_result(res, backoff=1.15, max_delay=1.0, preserve=False):
    """
    Await a task result.

    Example usage:

        @huey.task()
        def some_task(...):
            ...


        # Call the task and get the normal result-handle.
        rh = some_task(...)

        # Asynchronously await the result of the task.
        result = await aget_result(rh)

    More advanced example of waiting for multiple results concurrently:

        r1 = some_task(...)
        r2 = some_task(...)
        r3 = some_task(...)

        # Asynchronously await the results of all 3 tasks.
        results = await asyncio.gather(
            aget_result(r1),
            aget_result(r2),
            aget_result(r3))

    NOTE: the Redis operation will be a normal blocking socket read, but in
    practice these will be super fast. The slow part is the necessity to call
    `sleep()` between polling intervals (since the Redis command to read the
    result does not block).
    """
    delay = 0.1
    while res._result is EmptyData:
        delay = min(delay, max_delay)
        if res._get(preserve) is EmptyData:
            await asyncio.sleep(delay)
            delay *= backoff
    return res._result


async def aget_result_group(rg, *args, **kwargs):
    return await asyncio.gather(*[
        aget_result(r, *args, **kwargs)
        for r in rg])
