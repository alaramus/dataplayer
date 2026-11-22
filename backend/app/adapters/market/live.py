"""A symbol watched live, the shared frame (D323, D425).

What a watch first says is read over REST, as the grid reads it; what
changes after comes from the exchange's public streams. Every batch is rows
in the columns the grid already shows for the same feed. An exchange says
where its streams are, what its snapshot holds and what one of its messages
means; a `Watch` is one screen's watch of one symbol at one interval, and
may keep what a message needs, such as a book its deltas apply to.
"""

import asyncio
import contextlib
from collections.abc import AsyncGenerator, Sequence
from typing import Any, Protocol

from app.adapters.live import LiveRows
from app.adapters.market.session import MarketSession
from app.adapters.market.stream import QUEUE_SIZE, Item, MarketStream, StreamSpec
from app.adapters.protocol import AdapterError

DEFAULT_INTERVAL = "1m"
SNAPSHOT_CANDLES = 300
SNAPSHOT_TRADES = 100
BOOK_LEVELS = 20


class Watch(Protocol):
    def streams(self) -> Sequence[StreamSpec]: ...

    async def snapshot(self) -> list[LiveRows]:
        """The symbol as it stands, read once the streams are watched."""
        ...

    def batch(self, item: dict[str, Any]) -> list[LiveRows]:
        """One message of a stream as rows; none for what changes nothing."""
        ...


async def watch(
    session: MarketSession[Any],
    the_watch: Watch,
    refusals: dict[int, AdapterError],
    exchange: str,
) -> AsyncGenerator[LiveRows]:
    queue: asyncio.Queue[Item] = asyncio.Queue(maxsize=QUEUE_SIZE)
    async with session.kept() as kept, contextlib.AsyncExitStack() as held:
        for spec in the_watch.streams():
            found = kept.streams.get(spec.key)
            stream = found if isinstance(found, MarketStream) else None
            if stream is None:
                stream = MarketStream.of(spec, kept.forget_stream, refusals, exchange)
                kept.streams[spec.key] = stream
            # Watched before the snapshot is read, so nothing between the two
            # is missed; what both hold is left out by the watch.
            await held.enter_async_context(stream.watched(queue))
        for frame in await the_watch.snapshot():
            yield frame
        while True:
            item = await queue.get()
            if isinstance(item, AdapterError):
                raise item
            for rows in the_watch.batch(item):
                yield rows
