"""Disposable mutation evidence for the reviewed refresh policy strategy."""

from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
from psycopg import sql

from app.adapters.actions import ActionRefused
from app.adapters.postgres.timescale.plans import RefreshWindow, TimeDuration
from app.adapters.postgres.timescale.refresh_action import (
    RemoveRefreshPolicy,
    SetRefreshPolicy,
)
from app.adapters.postgres.timescale.refresh_plan import (
    RefreshState,
    inspect_refresh,
    plan_refresh,
)
from compatibility.timescale.policy_tables import (
    PolicyTable,
    disposable_hypertable,
    registry,
    reviewed,
)
from compatibility.timescale.source import TimescaleSource

WEEK_WINDOW = {
    "start_amount": 7, "start_unit": "day", "end_amount": 1, "end_unit": "hour",
    "schedule_amount": 1, "schedule_unit": "hour",
}
MONTH_WINDOW = {**WEEK_WINDOW, "start_amount": 30}


@dataclass(frozen=True)
class Aggregate:
    source: PolicyTable
    view: str = 'hourly"quoted'

    @property
    def identifier(self) -> sql.Identifier:
        return sql.Identifier(self.source.schema, self.view)

    @property
    def node_id(self) -> str:
        return f"{self.source.schema}.{self.view}"


@pytest.fixture
async def aggregate(source: TimescaleSource) -> AsyncIterator[Aggregate]:
    async with disposable_hypertable(source, "refresh") as table:
        target = Aggregate(table)
        await source.session().schema_change(sql.SQL(
            "CREATE MATERIALIZED VIEW {} WITH (timescaledb.continuous) AS "
            "SELECT public.time_bucket(INTERVAL '1 hour', observed_at) AS bucket, count(*) AS readings "
            "FROM {} GROUP BY 1 WITH NO DATA"
        ).format(target.identifier, table.identifier).as_string())
        yield target


async def state(source: TimescaleSource, target: Aggregate) -> RefreshState:
    return await inspect_refresh(source.session(), target.source.schema, target.view)


def window(days: int) -> RefreshWindow:
    return RefreshWindow(
        start_offset=TimeDuration(amount=days, unit="day"), end_offset=TimeDuration(amount=1, unit="hour"),
        schedule_interval=TimeDuration(amount=1, unit="hour"),
    )


async def test_set_replace_and_remove_through_registered_actions(
    source: TimescaleSource, aggregate: Aggregate,
) -> None:
    actions = registry(source)
    offers = await actions.action_offers(aggregate.node_id)
    assert SetRefreshPolicy.name in {item.name for item in offers.actions}
    assert offers.reason_for(RemoveRefreshPolicy.name) == "This continuous aggregate has no refresh policy"
    setter = actions.action(SetRefreshPolicy.name)
    remover = actions.action(RemoveRefreshPolicy.name)
    assert isinstance(setter, SetRefreshPolicy) and isinstance(remover, RemoveRefreshPolicy)

    preview = await setter.preview(aggregate.node_id, WEEK_WINDOW)
    assert "The source hypertable has no retention policy" in preview.items
    assert preview.fingerprint is not None
    await setter.perform_reviewed(aggregate.node_id, WEEK_WINDOW, preview.fingerprint)
    first = (await state(source, aggregate)).existing
    assert first is not None
    assert (first.start_offset, first.end_offset, first.schedule_interval) == ("7 days", "01:00:00", "01:00:00")

    await setter.perform_reviewed(
        aggregate.node_id, MONTH_WINDOW, await reviewed(setter, aggregate.node_id, MONTH_WINDOW),
    )
    second = (await state(source, aggregate)).existing
    assert second is not None and second.job_id != first.job_id and second.start_offset == "30 days"

    await remover.perform_reviewed(aggregate.node_id, {}, await reviewed(remover, aggregate.node_id, {}))
    assert (await state(source, aggregate)).existing is None


async def test_window_ending_before_it_starts_is_refused_at_review(
    source: TimescaleSource, aggregate: Aggregate,
) -> None:
    setter = registry(source).action(SetRefreshPolicy.name)
    assert isinstance(setter, SetRefreshPolicy)
    inverted = {**WEEK_WINDOW, "start_amount": 1, "start_unit": "hour", "end_amount": 1, "end_unit": "day"}
    preview = await setter.preview(aggregate.node_id, inverted)
    assert preview.blocked and "start further back" in preview.summary


async def test_window_reaching_data_the_source_drops_is_refused(
    source: TimescaleSource, aggregate: Aggregate,
) -> None:
    removal = await plan_refresh(source.session(), aggregate.source.schema, aggregate.view, window(7))
    # Paused, so the source keeps its rows while the intent is still read.
    await source.session().query(sql.SQL(
        "SELECT job_id FROM {}({}(%s::regclass, INTERVAL '10 days'), scheduled => false)"
    ).format(
        sql.Identifier(removal.strategy.function_schema, "alter_job"),
        sql.Identifier(removal.strategy.function_schema, "add_retention_policy"),
    ).as_string(), (aggregate.source.identifier.as_string(),))
    setter = registry(source).action(SetRefreshPolicy.name)
    assert isinstance(setter, SetRefreshPolicy)
    blocked = await setter.preview(aggregate.node_id, MONTH_WINDOW)
    assert blocked.blocked and "retention policy drops" in blocked.summary
    allowed = await setter.preview(aggregate.node_id, WEEK_WINDOW)
    assert not allowed.blocked
    assert "The source drops chunks older than 10 days; the window starts after that" in allowed.items


async def test_policy_added_externally_after_review_requires_new_review(
    source: TimescaleSource, aggregate: Aggregate,
) -> None:
    setter = registry(source).action(SetRefreshPolicy.name)
    assert isinstance(setter, SetRefreshPolicy)
    fingerprint = await reviewed(setter, aggregate.node_id, WEEK_WINDOW)
    plan = await plan_refresh(source.session(), aggregate.source.schema, aggregate.view, window(7))
    await source.session().query(sql.SQL(
        "SELECT {}(%s::regclass, INTERVAL '10 days', INTERVAL '1 hour', INTERVAL '1 hour')"
    ).format(sql.Identifier(plan.strategy.function_schema, "add_continuous_aggregate_policy")).as_string(), (
        plan.target.view_oid,
    ))
    with pytest.raises(ActionRefused, match="review it again"):
        await setter.perform_reviewed(aggregate.node_id, WEEK_WINDOW, fingerprint)
    current = (await state(source, aggregate)).existing
    assert current is not None and current.start_offset == "10 days"


async def test_window_the_source_rejects_keeps_the_existing_policy(
    source: TimescaleSource, aggregate: Aggregate,
) -> None:
    setter = registry(source).action(SetRefreshPolicy.name)
    assert isinstance(setter, SetRefreshPolicy)
    await setter.perform_reviewed(aggregate.node_id, WEEK_WINDOW, await reviewed(setter, aggregate.node_id, WEEK_WINDOW))
    before = (await state(source, aggregate)).existing
    # One hour of one-hour buckets: planning admits it, the source requires two buckets.
    narrow = {**WEEK_WINDOW, "start_amount": 2, "start_unit": "hour"}
    fingerprint = await reviewed(setter, aggregate.node_id, narrow)
    with pytest.raises(ActionRefused):
        await setter.perform_reviewed(aggregate.node_id, narrow, fingerprint)
    assert (await state(source, aggregate)).existing == before


async def test_strategy_verifies_the_installed_versions_add_shape(
    source: TimescaleSource, aggregate: Aggregate,
) -> None:
    plan = await plan_refresh(source.session(), aggregate.source.schema, aggregate.view, window(7))
    found = await source.session().query(
        "SELECT pronargs FROM pg_catalog.pg_proc WHERE oid = %s::pg_catalog.oid",
        (plan.strategy.add_function_oid,),
    )
    assert found == [{"pronargs": 8 if source.version == "2.18.0" else 7}]


async def test_fixture_aggregate_is_planned_against_its_sources_retention_without_change(
    source: TimescaleSource,
) -> None:
    inspected = await inspect_refresh(source.session(), "lab", "hourly")
    assert inspected.existing is None
    assert inspected.source_retention is not None and inspected.source_retention.older_than == "10 years"
    plan = await plan_refresh(source.session(), "lab", "hourly", window(30))
    assert plan.source_retention == inspected.source_retention
    with pytest.raises(ActionRefused, match="retention policy drops"):
        await plan_refresh(source.session(), "lab", "hourly", RefreshWindow(
            start_offset=TimeDuration(amount=20, unit="year"), end_offset=TimeDuration(amount=1, unit="day"),
            schedule_interval=TimeDuration(amount=1, unit="day"),
        ))
    assert (await inspect_refresh(source.session(), "lab", "hourly")) == inspected


@pytest.mark.parametrize("schema,view", [
    ("lab", "metrics"), ("public", "ordinary"), ("lab", "hourly'; SELECT 1; --"),
])
async def test_ineligible_targets_refuse_planning(source: TimescaleSource, schema: str, view: str) -> None:
    with pytest.raises(ActionRefused):
        await inspect_refresh(source.session(), schema, view)
