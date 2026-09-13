"""Connections polled for metrics by the metrics process (D127, D128)."""

import uuid
from collections.abc import AsyncIterator, Sequence

import pytest
from sqlmodel import col, delete
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters import registry
from app.adapters.metrics import MetricSample
from app.connectors import crud as connector_crud
from app.connectors.models import Connector
from app.connectors.service import split_options
from app.core.db import async_session_maker
from app.metrics.counters import RateState
from app.metrics.models import MetricsConnector
from app.metrics.poller import ConnectionPoller
from app.metrics.store import MetricsStore
from tests.metrics.conftest import needs_store
from tests.utils.database import working_postgres_options
from tests.utils.user import create_random_user

START = 1_789_000_000


def test_a_counter_becomes_a_rate_per_second_and_a_gauge_stays_as_it_is() -> None:
    state = RateState()
    first = [MetricSample("tx", "commits", 100, counter=True), MetricSample("db", "size", 5, unit="B")]
    later = [MetricSample("tx", "commits", 130, counter=True), MetricSample("db", "bytes", 3000, unit="B", counter=True)]

    assert [(s.field, s.value) for s in state.expand("c", START, first)] == [("size", 5.0)]
    rates = state.expand("c", START + 15, later)

    assert [(s.field, s.value, s.unit) for s in rates] == [("commits", 2.0, "/s")]
    assert [(s.field, s.value, s.unit) for s in state.expand("c", START + 30, [MetricSample("db", "bytes", 3600, unit="B", counter=True)])] == [
        ("bytes", 40.0, "B/s")
    ]


def test_a_counter_that_went_down_says_nothing() -> None:
    state = RateState()
    state.expand("c", START, [MetricSample("tx", "commits", 100, counter=True)])

    assert state.expand("c", START + 15, [MetricSample("tx", "commits", 5, counter=True)]) == []


class Clock:
    def __init__(self) -> None:
        self.now = float(START)

    def __call__(self) -> float:
        return self.now


@pytest.fixture
async def reporting_connector(db: AsyncSession) -> AsyncIterator[Connector]:
    owner = await create_random_user(db)
    config, secrets = split_options(registry.get("postgres"), working_postgres_options())
    async with async_session_maker() as session:
        connector = await connector_crud.create(
            session, name="polled", adapter_type="postgres", config=config, secrets=secrets, owner_id=owner.id
        )
        session.add(MetricsConnector(connector_id=connector.id, enabled=True, interval_seconds=15))
        await session.commit()
    yield connector
    async with async_session_maker() as session:
        await session.exec(delete(MetricsConnector))
        await session.exec(delete(Connector).where(col(Connector.id) == connector.id))
        await session.commit()


@needs_store
async def test_a_reporting_connection_is_polled_on_its_interval(
    store: MetricsStore, reporting_connector: Connector
) -> None:
    polled: list[uuid.UUID] = []
    values = iter([100.0, 130.0, 160.0])

    async def sampler(connector: Connector) -> Sequence[MetricSample]:
        polled.append(connector.id)
        return [MetricSample("transactions", "commits", next(values), counter=True), MetricSample("sessions", "count", 3, label="total")]

    clock = Clock()
    poller = ConnectionPoller(store, sampler=sampler, clock=clock)

    await poller.round()
    await poller.round()
    clock.now += 15
    await poller.round()

    assert polled == [reporting_connector.id, reporting_connector.id]
    catalog = {(s.metric, s.field, s.label): s for s in await store.catalog([reporting_connector.id])}
    assert set(catalog) == {("transactions", "commits", ""), ("sessions", "count", "total")}
    assert catalog[("transactions", "commits", "")].unit == "/s"
    assert catalog[("transactions", "commits", "")].host == ""
    points = await store.raw_points([catalog[("transactions", "commits", "")].id], START - 60, START + 60)
    assert list(points.values()) == [[[START + 15.0, 2.0]]]


@needs_store
async def test_a_connection_that_cannot_be_read_is_asked_again_later(
    store: MetricsStore, reporting_connector: Connector
) -> None:
    calls = 0

    async def failing(connector: Connector) -> Sequence[MetricSample]:
        nonlocal calls
        del connector
        calls += 1
        raise RuntimeError("the database went away")

    clock = Clock()
    poller = ConnectionPoller(store, sampler=failing, clock=clock)

    await poller.round()
    clock.now += 15
    await poller.round()
    clock.now += 16
    await poller.round()

    # Once, then not at the interval, then after the doubled wait.
    assert calls == 2
    assert poller.counts.failures == 2
    assert await store.catalog([reporting_connector.id]) == []


@needs_store
async def test_a_connection_whose_reporting_is_off_is_not_polled(
    store: MetricsStore, reporting_connector: Connector
) -> None:
    async with async_session_maker() as session:
        row = await session.get(MetricsConnector, reporting_connector.id)
        assert row is not None
        row.enabled = False
        session.add(row)
        await session.commit()

    async def sampler(connector: Connector) -> Sequence[MetricSample]:
        raise AssertionError(f"{connector.id} was polled")

    await ConnectionPoller(store, sampler=sampler, clock=Clock()).round()
