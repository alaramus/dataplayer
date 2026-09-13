"""The metrics process: agent packets in, connections polled, samples into the store (D127).

Run as `python -m app.metrics.collector`. One process: it holds the UDP port
and the previous sample of every counter. It waits while no store is set up and
starts over when the setting changes.
"""

import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, fields

from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.db import async_session_maker, loop_factory
from app.metrics import crud, keys
from app.metrics.counters import CounterState
from app.metrics.holder import options_of
from app.metrics.packets import process_snapshot_of, read_envelope, samples_of
from app.metrics.poller import ConnectionPoller, poll_forever
from app.metrics.restarts import Restart, RestartWatch
from app.metrics.store import (
    MetricsStore,
    PointRow,
    RestartRow,
    SeriesKey,
    Source,
    StoreUnavailable,
    store_url,
)

logger = logging.getLogger("app.metrics.collector")

QUEUE_SIZE = 10_000
BATCH_POINTS = 200
BATCH_SECONDS = 1.0
KEYS_REFRESH_SECONDS = 15.0
# A packet under a key not known yet reads the keys again, at most this often:
# an agent registered a moment ago should not wait a whole refresh. Short, or
# the first packets of an agent registered just after a read are dropped; a
# flood of unknown keys costs one small query a second at most.
MISS_REFRESH_SECONDS = 1.0
SETTING_POLL_SECONDS = 5.0
REPORT_SECONDS = 60.0

AgentLookup = Callable[[str], Awaitable[uuid.UUID | None]]


@dataclass
class Counts:
    received: int = 0
    malformed: int = 0
    unknown_key: int = 0
    queue_full: int = 0
    points: int = 0
    snapshots: int = 0
    failed_writes: int = 0
    no_store: int = 0
    restarts: int = 0

    def line(self) -> str:
        return " ".join(f"{item.name}={getattr(self, item.name)}" for item in fields(self))


class Receiver(asyncio.DatagramProtocol):
    """Never awaits: a slow store degrades a chart, a stalled socket loses all."""

    def __init__(self, queue: asyncio.Queue[bytes], counts: Counts) -> None:
        self._queue = queue
        self._counts = counts

    def datagram_received(self, data: bytes, addr: tuple[str | object, int]) -> None:
        del addr
        self._counts.received += 1
        try:
            self._queue.put_nowait(data)
        except asyncio.QueueFull:
            self._counts.queue_full += 1


class AgentKeys:
    """Which agent a key belongs to, read from the application database."""

    def __init__(self) -> None:
        self._by_fingerprint: dict[str, uuid.UUID] = {}
        self._read_at = 0.0

    async def refresh(self) -> None:
        async with async_session_maker() as session:
            self._by_fingerprint = await crud.key_fingerprints(session)
        self._read_at = time.monotonic()

    async def agent_for(self, key: str) -> uuid.UUID | None:
        fingerprint = keys.fingerprint(key)
        agent = self._by_fingerprint.get(fingerprint)
        if agent is None and time.monotonic() - self._read_at > MISS_REFRESH_SECONDS:
            await self.refresh()
            agent = self._by_fingerprint.get(fingerprint)
        return agent


class Collector:
    """Turns packets into rows. Holds counter state and known series ids."""

    def __init__(self, store: MetricsStore, agent_for: AgentLookup, counts: Counts) -> None:
        self._store = store
        self._agent_for = agent_for
        self._counts = counts
        self._counters = CounterState()
        self._restarts = RestartWatch()
        self._series: dict[tuple[uuid.UUID, SeriesKey], int] = {}
        self._pending: list[PointRow] = []

    @property
    def pending(self) -> int:
        return len(self._pending)

    async def handle(self, raw: bytes) -> None:
        envelope = read_envelope(raw)
        if envelope is None:
            self._counts.malformed += 1
            return
        agent_id = await self._agent_for(envelope.key)
        if agent_id is None:
            self._counts.unknown_key += 1
            return
        source = Source(kind="agent", id=agent_id)
        snapshot = process_snapshot_of(envelope)
        if snapshot is not None:
            await self._store.write_processes(source, snapshot)
            self._counts.snapshots += 1
            await self._restarted(
                agent_id, envelope.host, self._restarts.observe_processes((agent_id, envelope.host), snapshot)
            )
            return
        measured = samples_of(envelope)
        await self._restarted(agent_id, envelope.host, self._restarts.observe((agent_id, envelope.host), measured))
        samples = self._counters.expand((agent_id, envelope.host), measured)
        keyed = [
            (SeriesKey(envelope.host, sample.metric, sample.field, sample.label), sample)
            for sample in samples
        ]
        unknown = [
            (key, sample.unit, sample.ts)
            for key, sample in keyed
            if (agent_id, key) not in self._series
        ]
        if unknown:
            for key, series_id in (await self._store.series_ids(source, unknown)).items():
                self._series[(agent_id, key)] = series_id
        for key, sample in keyed:
            self._pending.append(
                PointRow(
                    series_id=self._series[(agent_id, key)], ts=sample.ts, value=sample.value
                )
            )

    async def _restarted(self, agent_id: uuid.UUID, host: str, restart: Restart | None) -> None:
        if restart is None:
            return
        await self._store.write_restart(RestartRow(agent_id, host, restart.ts, restart.cause, restart.actions))
        self._counts.restarts += 1
        logger.info("Host %s of agent %s restarted (%s)", host, agent_id, restart.cause)

    def forget_series(self) -> None:
        """Resolve every series again. A purge in the web process deletes rows
        this cache still points at; forgetting bounds how long that lasts."""
        self._series.clear()

    async def flush(self) -> None:
        if not self._pending:
            return
        batch, self._pending = self._pending, []
        await self._store.write_points(batch)
        self._counts.points += len(batch)


async def _work(queue: asyncio.Queue[bytes], collector: Collector, counts: Counts) -> None:
    deadline = time.monotonic() + BATCH_SECONDS
    while True:
        timeout = max(0.0, deadline - time.monotonic())
        try:
            raw = await asyncio.wait_for(queue.get(), timeout=timeout)
            await collector.handle(raw)
        except TimeoutError:
            pass
        except (SQLAlchemyError, OSError, StoreUnavailable):
            counts.failed_writes += 1
            logger.exception("A packet could not be stored")
        if collector.pending >= BATCH_POINTS or time.monotonic() >= deadline:
            try:
                await collector.flush()
            except (SQLAlchemyError, OSError):
                counts.failed_writes += 1
                logger.exception("A batch of points could not be stored")
            deadline = time.monotonic() + BATCH_SECONDS


async def _refresh(agent_keys: AgentKeys, collector: Collector) -> None:
    while True:
        await asyncio.sleep(KEYS_REFRESH_SECONDS)
        collector.forget_series()
        try:
            await agent_keys.refresh()
        except (SQLAlchemyError, OSError):
            logger.exception("Agent keys could not be read")


async def _report(counts: Counts) -> None:
    while True:
        await asyncio.sleep(REPORT_SECONDS)
        logger.info("metrics %s", counts.line())


async def _setting_changed(configured_at: object) -> None:
    while True:
        await asyncio.sleep(SETTING_POLL_SECONDS)
        async with async_session_maker() as session:
            setting = await crud.store_setting(session)
        if setting is None or setting.configured_at != configured_at:
            return


async def _discard(queue: asyncio.Queue[bytes], counts: Counts) -> None:
    """Take packets while there is no store to write them to, and count them."""
    while True:
        await queue.get()
        counts.no_store += 1


async def _prepared_store(queue: asyncio.Queue[bytes], counts: Counts) -> tuple[MetricsStore, object]:
    waiting_said = False
    discarding = asyncio.create_task(_discard(queue, counts))
    try:
        while True:
            async with async_session_maker() as session:
                setting = await crud.store_setting(session)
            if setting is None:
                if not waiting_said:
                    logger.info("No metrics store is set up yet; waiting")
                    waiting_said = True
                await asyncio.sleep(SETTING_POLL_SECONDS)
                continue
            store = MetricsStore(store_url(options_of(setting)))
            try:
                await store.migrate()
            except StoreUnavailable:
                await store.aclose()
                logger.warning("The metrics store is not answering; trying again")
                await asyncio.sleep(SETTING_POLL_SECONDS)
                continue
            return store, setting.configured_at
    finally:
        discarding.cancel()
        await asyncio.gather(discarding, return_exceptions=True)


async def serve() -> None:
    """Bind the port first and keep it for the life of the process.

    A published port nobody is listening on is not harmless: Docker Desktop
    stopped forwarding an agent's packets to a container that bound its port
    only minutes later, and started again only when the container was
    recreated. So the socket is there from the start, and what arrives before
    a store exists is counted and dropped.
    """
    loop = asyncio.get_running_loop()
    counts = Counts()
    queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=QUEUE_SIZE)
    receiver = Receiver(queue, counts)

    def protocol(receiver: Receiver = receiver) -> Receiver:
        return receiver

    transport, _ = await loop.create_datagram_endpoint(
        protocol,
        local_addr=(settings.METRICS_UDP_HOST, settings.METRICS_UDP_PORT),
    )
    logger.info(
        "Receiving agent packets on %s:%s/udp",
        settings.METRICS_UDP_HOST,
        settings.METRICS_UDP_PORT,
    )
    reporting = asyncio.create_task(_report(counts))
    try:
        while True:
            store, configured_at = await _prepared_store(queue, counts)
            agent_keys = AgentKeys()
            await agent_keys.refresh()
            collector = Collector(store, agent_keys.agent_for, counts)
            poller = ConnectionPoller(store)
            tasks = [
                asyncio.create_task(_work(queue, collector, counts)),
                asyncio.create_task(_refresh(agent_keys, collector)),
                asyncio.create_task(poll_forever(poller)),
            ]
            logger.info("Writing to the metrics store")
            try:
                await _setting_changed(configured_at)
                logger.info("The metrics store setting changed; starting over")
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                try:
                    await collector.flush()
                except (SQLAlchemyError, OSError):
                    logger.exception("The last batch of points could not be stored")
                await store.aclose()
    finally:
        reporting.cancel()
        transport.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(serve(), loop_factory=loop_factory)


if __name__ == "__main__":
    main()
