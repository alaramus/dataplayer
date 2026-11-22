"""One upstream socket of an exchange's public streams, shared by its watchers (D323, D425).

Kept with the connection's client, started by the first watcher and stopped
by the last; each watcher has a bounded queue. What the socket says after it
opens — a subscription — and what it must say to stay open — a ping — are
the exchange's; reconnecting after a drop, and saying a refusal in the
exchange's words, are shared. `websockets` is imported here alone.
"""

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import InvalidStatus, WebSocketException

from app.adapters.protocol import AdapterError

logger = logging.getLogger(__name__)

OPEN_TIMEOUT_SECONDS = 10.0
RETRY_SECONDS = (1.0, 2.0, 5.0, 10.0, 30.0)
# A watcher that falls this far behind loses the oldest batches first: a
# book or a candle is replaced by the next one anyway.
QUEUE_SIZE = 500

type Item = dict[str, Any] | AdapterError


@dataclass(frozen=True)
class StreamSpec:
    """Where a stream is, what it is told on opening, and how it is kept alive."""

    url: str
    # Sent as they are after every open, a reopen included.
    greeting: tuple[str, ...] = ()
    # Sent every `ping_seconds` while the socket is open.
    ping: str | None = None
    ping_seconds: float = 20.0
    # What the exchange answers a ping with when that is not JSON, skipped
    # rather than read as a broken message (D425).
    pong: str | None = None

    @property
    def key(self) -> str:
        """What the stream is kept under: one socket a subscription."""
        return "\n".join((self.url, *self.greeting))


@dataclass
class MarketStream:
    """One upstream socket, and the queue of every watcher of it."""

    url: str
    on_idle: Callable[[MarketStream], None] = lambda stream: None
    greeting: tuple[str, ...] = ()
    ping: str | None = None
    ping_seconds: float = 20.0
    pong: str | None = None
    # Statuses that mean the exchange will not serve this address, and the
    # refusal each watcher is then told.
    refusals: dict[int, AdapterError] = field(default_factory=dict)
    # For the log only.
    exchange: str = "exchange"
    queues: set[asyncio.Queue[Item]] = field(default_factory=set)
    task: asyncio.Task[None] | None = None

    @classmethod
    def of(
        cls,
        spec: StreamSpec,
        on_idle: Callable[[MarketStream], None],
        refusals: dict[int, AdapterError],
        exchange: str,
    ) -> MarketStream:
        return cls(
            spec.url,
            on_idle=on_idle,
            greeting=spec.greeting,
            ping=spec.ping,
            ping_seconds=spec.ping_seconds,
            pong=spec.pong,
            refusals=refusals,
            exchange=exchange,
        )

    @asynccontextmanager
    async def watched(self, queue: asyncio.Queue[Item]) -> AsyncIterator[None]:
        """What the stream says goes into the queue until the watcher leaves."""
        self.queues.add(queue)
        if self.task is None:
            self.task = asyncio.create_task(self._run())
        try:
            yield
        finally:
            self.queues.discard(queue)
            if not self.queues:
                await self.close()
                self.on_idle(self)

    def _publish(self, item: Item) -> None:
        for queue in self.queues:
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(item)

    async def _keep_alive(self, socket: ClientConnection) -> None:
        if self.ping is None:
            return
        while True:
            await asyncio.sleep(self.ping_seconds)
            await socket.send(self.ping)

    async def _run(self) -> None:
        """Read the upstream until nobody watches, coming back after a drop."""
        attempt = 0
        while True:
            try:
                async with connect(
                    self.url,
                    proxy=None,
                    open_timeout=OPEN_TIMEOUT_SECONDS,
                    # A watcher that leaves is not kept waiting for the
                    # exchange to agree the socket is closed.
                    close_timeout=1.0,
                    max_size=2**20,
                ) as socket:
                    attempt = 0
                    for greeting in self.greeting:
                        await socket.send(greeting)
                    pinging = asyncio.create_task(self._keep_alive(socket))
                    try:
                        async for message in socket:
                            if self.pong is not None and message == self.pong:
                                continue
                            self._publish(json.loads(message))
                    finally:
                        pinging.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await pinging
            except InvalidStatus as refusal:
                refused = self.refusals.get(refusal.response.status_code)
                if refused is not None:
                    self._publish(refused)
                    return
                logger.warning(
                    "%s stream refused: %s",
                    self.exchange,
                    refusal.response.status_code,
                )
            except (OSError, TimeoutError, WebSocketException, ValueError) as failure:
                logger.info("%s stream dropped: %r", self.exchange, failure)
            delay = RETRY_SECONDS[min(attempt, len(RETRY_SECONDS) - 1)]
            attempt += 1
            await asyncio.sleep(delay)

    async def close(self) -> None:
        task, self.task = self.task, None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
