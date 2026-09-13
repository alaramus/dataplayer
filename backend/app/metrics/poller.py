"""Connections that report about themselves, polled by the metrics process (D127, D128).

Once, whatever serves the screens: only this process polls. A connection is read
on the interval its owner chose, with the owner's stored credentials, and a
failure backs the next attempt off the way connection health does (D19).
"""

import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

from app.adapters import registry
from app.adapters.metrics import MetricSample, SupportsMetrics
from app.adapters.registry import AdapterContext
from app.connectors.health import delay_after
from app.connectors.models import Connector
from app.connectors.service import build_adapter, merge_options
from app.core.db import async_session_maker
from app.metrics import crud
from app.metrics.counters import RateState
from app.metrics.store import MetricsStore, PointRow, SeriesKey, Source
from app.users import storage

logger = logging.getLogger(__name__)

TICK_SECONDS = 5.0
POLL_TIMEOUT_SECONDS = 10.0
CONCURRENCY = 4
BACKOFF_CAP_SECONDS = 600.0

Sampler = Callable[[Connector], Awaitable[Sequence[MetricSample]]]


async def read_samples(connector: Connector) -> Sequence[MetricSample]:
    kind = registry.get(connector.adapter_type)
    adapter = build_adapter(
        kind,
        merge_options(connector.config, connector.secrets),
        AdapterContext(home_dir=storage.home_dir(connector.owner_id)),
    )
    if not isinstance(adapter, SupportsMetrics):
        return []
    return await adapter.metric_samples()


@dataclass
class _Due:
    at: float = 0.0
    misses: int = 0


@dataclass
class PollCounts:
    polls: int = 0
    failures: int = 0


class ConnectionPoller:
    def __init__(
        self,
        store: MetricsStore,
        *,
        sampler: Sampler = read_samples,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._store = store
        self._sampler = sampler
        self._clock = clock
        self._rates = RateState()
        self._due: dict[uuid.UUID, _Due] = {}
        self.counts = PollCounts()

    async def round(self) -> None:
        async with async_session_maker() as session:
            reporting = await crud.reporting_connectors(session)
        now = self._clock()
        live = {connector.id for connector, _ in reporting}
        for gone in set(self._due) - live:
            del self._due[gone]
        due = [
            (connector, row.interval_seconds)
            for connector, row in reporting
            if self._due.get(connector.id, _Due()).at <= now
        ]
        gate = asyncio.Semaphore(CONCURRENCY)

        async def one(connector: Connector, interval: int) -> None:
            async with gate:
                await self._poll(connector, interval, now)

        await asyncio.gather(*(one(connector, interval) for connector, interval in due))

    async def _poll(self, connector: Connector, interval: int, now: float) -> None:
        state = self._due.setdefault(connector.id, _Due())
        self.counts.polls += 1
        try:
            readings = await asyncio.wait_for(self._sampler(connector), POLL_TIMEOUT_SECONDS)
        except Exception:
            # Anything a driver or a database can raise: one connection that
            # cannot be read must not stop the others being read.
            self.counts.failures += 1
            state.misses += 1
            state.at = now + delay_after(misses=state.misses, base=interval, cap=max(interval, BACKOFF_CAP_SECONDS))
            logger.info("Connection %s could not be read for metrics", connector.id, exc_info=True)
            return
        state.misses = 0
        state.at = now + interval
        samples = self._rates.expand(connector.id, int(now), readings)
        if not samples:
            return
        source = Source(kind="connector", id=connector.id)
        keyed = [(SeriesKey("", s.metric, s.field, s.label), s) for s in samples]
        ids = await self._store.series_ids(source, [(key, s.unit, s.ts) for key, s in keyed])
        await self._store.write_points([PointRow(ids[key], s.ts, s.value) for key, s in keyed])


async def poll_forever(poller: ConnectionPoller) -> None:
    while True:
        try:
            await poller.round()
        except Exception:
            logger.exception("A round of connection metrics failed")
        await asyncio.sleep(TICK_SECONDS)
