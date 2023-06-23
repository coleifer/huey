"""
Example script showing how you can use asyncio to read results.
"""
import asyncio
import time

from huey.contrib.asyncio import aget_result
from huey.contrib.asyncio import aget_result_group

from tasks import *


async def main():
    s = time.time()
    r1, r2, r3 = [slow(2) for _ in range(3)]
    results = await asyncio.gather(
        aget_result(r1),
        aget_result(r2),
        aget_result(r3))
    print(results)
    print(round(time.time() - s, 2))

    # Using result group.
    s = time.time()
    results = await aget_result_group(slow.map([2, 2, 2]))
    print(results)
    print(round(time.time() - s, 2))


if __name__ == '__main__':
    asyncio.run(main())
