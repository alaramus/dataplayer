"""The metrics process: agent datagrams in, connections polled, samples into the store (D127).

Run as `python -m app.metrics.collector`. One process: it holds the UDP port,
the keys agents sign with, what it accepted from each agent instance, and the
previous reading of every connection counter. It waits while no store is set
up and starts over when the setting changes.
"""

import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, fields

from cryptography.exceptions import InvalidTag
from sqlalchemy.exc import SQLAlchemyError

from app.core import logs
from app.core.config import settings
from app.core.db import async_session_maker, loop_factory
from app.metrics import crud, keys, protocol
from app.metrics.holder import options_of
from app.metrics.poller import ConnectionPoller, poll_forever
from app.metrics.restarts import RestartWatch, Run, known_runs
from app.metrics.store import (
    AgentRunRow,
    MetricsStore,
    PointRow,
    ProcessPart,
    ProcessRow,
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
# A datagram under a key id not known yet reads the keys again, at most this
# often: an agent registered a moment ago should not wait a whole refresh.
# Short, or the first datagrams of an agent registered just after a read are
# dropped; a flood of unknown ids costs one small query a second at most.
MISS_REFRESH_SECONDS = 1.0
SETTING_POLL_SECONDS = 5.0
REPORT_SECONDS = 60.0

# The agents a key id may name, each with its key.
KeyLookup = Callable[[str], Awaitable[Sequence[tuple[uuid.UUID, str]]]]


@dataclass
class Counts:
    received: int = 0
    malformed: int = 0
    unknown_key: int = 0
    bad_signature: int = 0
    refused_body: int = 0
    stale: int = 0
    future: int = 0
    replayed: int = 0
    queue_full: int = 0
    points: int = 0
    process_parts: int = 0
    hosts: int = 0
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
    """The keys agents sign with, by key id, read from the application database.

    Held unsealed for the life of a store: a signature is checked with the key
    itself, and every datagram is checked.
    """

    def __init__(self) -> None:
        self._by_id: dict[str, list[tuple[uuid.UUID, str]]] = {}
        self._unsealed: dict[str, str] = {}
        self._read_at = 0.0

    async def refresh(self) -> None:
        async with async_session_maker() as session:
            rows = await crud.agent_keys(session)
        by_id: dict[str, list[tuple[uuid.UUID, str]]] = {}
        unsealed: dict[str, str] = {}
        for agent_id, fingerprint, sealed in rows:
            key = self._unsealed.get(fingerprint)
            if key is None:
                try:
                    key = keys.unseal(sealed)
                except (InvalidTag, UnicodeDecodeError):
                    logger.warning("The key of agent %s cannot be unsealed", agent_id)
                    continue
            unsealed[fingerprint] = key
            by_id.setdefault(fingerprint[: keys.KEY_ID_LENGTH], []).append((agent_id, key))
        self._by_id, self._unsealed = by_id, unsealed
        self._read_at = time.monotonic()

    async def agents_for(self, key_id: str) -> Sequence[tuple[uuid.UUID, str]]:
        found = self._by_id.get(key_id)
        if found is None and time.monotonic() - self._read_at > MISS_REFRESH_SECONDS:
            await self.refresh()
            found = self._by_id.get(key_id)
        return found or ()


class Collector:
    """Turns datagrams into rows. Holds what was accepted and known series ids."""

    def __init__(
        self,
        store: MetricsStore,
        agents_for: KeyLookup,
        counts: Counts,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._store = store
        self._agents_for = agents_for
        self._counts = counts
        self._clock = clock
        self._freshness = protocol.Freshness()
        self._restarts = RestartWatch()
        self._series: dict[tuple[uuid.UUID, SeriesKey], int] = {}
        self._pending: list[PointRow] = []

    @property
    def pending(self) -> int:
        return len(self._pending)

    async def load(self) -> None:
        """What the store knows of every host's agent process, so a restart of
        this process is not taken for a restart of every agent."""
        self._restarts = RestartWatch(known_runs(await self._store.runs()))

    async def handle(self, raw: bytes) -> None:
        frame = protocol.frame_of(raw)
        if frame is None:
            self._counts.malformed += 1
            return
        candidates = await self._agents_for(frame.key_id)
        if not candidates:
            self._counts.unknown_key += 1
            return
        agent_id = next((agent for agent, key in candidates if protocol.signed_with(frame, key)), None)
        if agent_id is None:
            self._counts.bad_signature += 1
            return
        report = protocol.report_of(frame.body)
        if report is None:
            self._counts.refused_body += 1
            return
        refusal = self._freshness.check(
            (agent_id, report.agent.instance), report.seq, report.time, int(self._clock())
        )
        if refusal is not None:
            setattr(self._counts, refusal, getattr(self._counts, refusal) + 1)
            return
        await self._write(agent_id, report)

    def forget_quiet(self) -> None:
        self._freshness.forget_quiet(int(self._clock()))

    async def _write(self, agent_id: uuid.UUID, report: protocol.Report) -> None:
        host = report.host.name
        run = Run(report.agent.instance, report.agent.version, report.agent.started, report.host.boot)
        seen = self._restarts.observe((agent_id, host), run)
        row = AgentRunRow(agent_id, host, run.instance, run.version, run.started, run.boot)
        if isinstance(report, protocol.HostReport) and seen.current:
            await self._store.write_run(row, report.info, report.time)
            self._counts.hosts += 1
        elif seen.new:
            await self._store.write_run(row)
        if seen.restart is not None:
            await self._store.write_restart(RestartRow(agent_id, host, seen.restart.ts, seen.restart.cause))
            self._counts.restarts += 1
            logger.info("Host %s of agent %s restarted (%s)", host, agent_id, seen.restart.cause)
        source = Source(kind="agent", id=agent_id)
        if isinstance(report, protocol.ProcessesReport):
            await self._store.write_processes(
                source,
                ProcessPart(
                    host=host,
                    ts=report.time,
                    total=report.total,
                    rows=[ProcessRow(*row) for row in report.rows],
                ),
            )
            self._counts.process_parts += 1
        elif isinstance(report, protocol.MetricsReport):
            await self._points(agent_id, source, host, report)

    async def _points(
        self, agent_id: uuid.UUID, source: Source, host: str, report: protocol.MetricsReport
    ) -> None:
        keyed = [
            (SeriesKey(host, metric, field, label), unit, value)
            for metric, field, label, unit, value in report.samples
        ]
        unknown = [(key, unit, report.time) for key, unit, _ in keyed if (agent_id, key) not in self._series]
        if unknown:
            for key, series_id in (await self._store.series_ids(source, unknown)).items():
                self._series[(agent_id, key)] = series_id
        for key, _, value in keyed:
            self._pending.append(PointRow(series_id=self._series[(agent_id, key)], ts=report.time, value=value))

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
            logger.exception("A datagram could not be stored")
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
        collector.forget_quiet()
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
    """Take datagrams while there is no store to write them to, and count them."""
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
    stopped forwarding an agent's datagrams to a container that bound its port
    only minutes later, and started again only when the container was
    recreated. So the socket is there from the start, and what arrives before
    a store exists is counted and dropped.
    """
    loop = asyncio.get_running_loop()
    counts = Counts()
    queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=QUEUE_SIZE)
    receiver = Receiver(queue, counts)

    def receiving(receiver: Receiver = receiver) -> Receiver:
        return receiver

    transport, _ = await loop.create_datagram_endpoint(
        receiving,
        local_addr=(settings.METRICS_UDP_HOST, settings.METRICS_UDP_PORT),
    )
    logger.info(
        "Receiving agent datagrams on %s:%s/udp",
        settings.METRICS_UDP_HOST,
        settings.METRICS_UDP_PORT,
    )
    reporting = asyncio.create_task(_report(counts))
    try:
        while True:
            store, configured_at = await _prepared_store(queue, counts)
            agent_keys = AgentKeys()
            collector = Collector(store, agent_keys.agents_for, counts)
            try:
                await agent_keys.refresh()
                await collector.load()
            except (SQLAlchemyError, OSError, StoreUnavailable):
                await store.aclose()
                logger.exception("Agent keys or hosts could not be read; trying again")
                await asyncio.sleep(SETTING_POLL_SECONDS)
                continue
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
    logs.configure("metrics")
    asyncio.run(serve(), loop_factory=loop_factory)


if __name__ == "__main__":
    main()
