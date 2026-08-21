"""Looking at the filesystem from an async test.

The rule that keeps blocking calls out of async code applies to a test as much
as to a handler, and honouring it costs one helper rather than a suppression.
"""

from collections.abc import Callable

from anyio import to_thread


async def look[T](at: Callable[[], T]) -> T:
    return await to_thread.run_sync(at)
