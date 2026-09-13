import asyncio
import time

from huey.constants import EmptyData
from huey.exceptions import ResultTimeout


async def aget_result(res, backoff=1.15, max_delay=1.0, preserve=False,
                      timeout=None):
    """
    Await a task result.

    Example usage:

        @huey.task()
        def sleep(n):
            time.sleep(n)
            return n

        # Call the task and get the normal result-handle.
        rh = sleep(2)

        # Asynchronously await the result of the task.
        result = await aget_result(rh)

    More advanced example of waiting for multiple results concurrently:

        r1 = sleep(1)
        r2 = sleep(2)
        r3 = sleep(3)

        # Asynchronously await the results of all 3 tasks. Will take
        # ~3 seconds.
        results = await asyncio.gather(
            aget_result(r1),
            aget_result(r2),
            aget_result(r3))

    Give up after ``timeout`` seconds by raising ``ResultTimeout``:

        try:
            result = await aget_result(rh, timeout=5)
        except ResultTimeout:
            ...

    NOTE: the Redis operation will be a normal blocking socket read, but in
    practice these will be super fast. The slow part is the necessity to wait
    between polling intervals (since the Redis command to read the result does
    not block).
    """
    delay = 0.1
    deadline = None if timeout is None else time.monotonic() + timeout
    while res._get(preserve) is EmptyData:
        if deadline is not None and time.monotonic() >= deadline:
            raise ResultTimeout('timed out waiting for result')
        await asyncio.sleep(delay)
        delay = min(delay * backoff, max_delay)
    return res.get(preserve=preserve)


async def aget_result_group(rg, *args, **kwargs):
    """
    Await the results of a ResultGroup.

    Example usage:

        @huey.task()
        def sleep(n):
            time.sleep(n)
            return n

        rg = sleep.map([2, 2, 2])

        # This should take ~2 seconds.
        results = await aget_result_group(rg)
    """
    tasks = [asyncio.create_task(aget_result(r, *args, **kwargs)) for r in rg]
    try:
        return await asyncio.gather(*tasks)
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
