"""Disposable mutation evidence for the reviewed retention policy strategy."""

import asyncio
from collections.abc import AsyncIterator

import psycopg
import pytest
from psycopg import sql

from app.adapters.actions import ActionRefused
from app.adapters.postgres.actions import PostgresActions
from app.adapters.postgres.catalog import PostgresCatalog
from app.adapters.postgres.inspection import PostgresReader
from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.timescale import age_policy_execution
from app.adapters.postgres.timescale.age_policy_action import (
    RemoveRetentionPolicy,
    SetRetentionPolicy,
)
from app.adapters.postgres.timescale.age_policy_plan import (
    RETENTION,
    AgePolicySpec,
    AgePolicyState,
    age_policy_plan,
    inspect_age_policy,
    plan_age_policy,
)
from app.adapters.postgres.timescale.plans import AgePolicyPlan, TimeDuration
from compatibility.timescale.policy_tables import (
    PolicyTable,
    disposable_hypertable,
    jobs,
    registry,
    reviewed,
    rows,
)
from compatibility.timescale.source import TimescaleSource

TEN_YEARS = {"amount": 10, "unit": "year"}
TWENTY_YEARS = {"amount": 20, "unit": "year"}


@pytest.fixture
async def retention_table(source: TimescaleSource) -> AsyncIterator[PolicyTable]:
    async with disposable_hypertable(source, "retention") as target:
        yield target


async def policies(source: TimescaleSource, target: PolicyTable) -> list[dict[str, object]]:
    return await jobs(source, target, "policy_retention")


async def state(source: TimescaleSource, target: PolicyTable) -> AgePolicyState:
    return await inspect_age_policy(source.session(), RETENTION, target.schema, target.table)


async def native_add(source: TimescaleSource, plan: AgePolicyPlan, drop_after: str) -> None:
    await source.session().query(sql.SQL("SELECT {}(%s::regclass, %s::interval)").format(
        sql.Identifier(plan.strategy.function_schema, "add_retention_policy"),
    ).as_string(), (plan.target.relation_oid, drop_after))


async def test_set_replace_and_remove_through_registered_actions(
    source: TimescaleSource, retention_table: PolicyTable,
) -> None:
    target = retention_table
    actions = registry(source)
    before = await rows(source, target)
    names = {item.name for item in await actions.all_actions()}
    assert {SetRetentionPolicy.name, RemoveRetentionPolicy.name} <= names
    offers = await actions.action_offers(target.node_id)
    assert SetRetentionPolicy.name in {item.name for item in offers.actions}
    assert offers.reason_for(RemoveRetentionPolicy.name) == "This hypertable has no retention policy"
    setter = actions.action(SetRetentionPolicy.name)
    remover = actions.action(RemoveRetentionPolicy.name)
    assert isinstance(setter, SetRetentionPolicy) and isinstance(remover, RemoveRetentionPolicy)

    await setter.perform_reviewed(target.node_id, TEN_YEARS, await reviewed(setter, target.node_id, TEN_YEARS))
    first = await policies(source, target)
    assert len(first) == 1 and first[0]["scheduled"] is True
    current = (await state(source, target)).existing
    assert current is not None and current.older_than == "10 years"
    assert RemoveRetentionPolicy.name in {item.name for item in (await actions.action_offers(target.node_id)).actions}

    preview = await setter.preview(target.node_id, TWENTY_YEARS)
    assert f"Replaces job {first[0]['job_id']}, which drops chunks older than 10 years" in preview.items
    assert preview.fingerprint is not None
    await setter.perform_reviewed(target.node_id, TWENTY_YEARS, preview.fingerprint)
    second = await policies(source, target)
    assert len(second) == 1 and second[0]["job_id"] != first[0]["job_id"]
    current = (await state(source, target)).existing
    assert current is not None and current.older_than == "20 years"

    await remover.perform_reviewed(target.node_id, {}, await reviewed(remover, target.node_id, {}))
    assert await policies(source, target) == []
    assert await rows(source, target) == before


async def test_policy_added_externally_after_review_requires_new_review(
    source: TimescaleSource, retention_table: PolicyTable,
) -> None:
    target = retention_table
    setter = registry(source).action(SetRetentionPolicy.name)
    assert isinstance(setter, SetRetentionPolicy)
    fingerprint = await reviewed(setter, target.node_id, TEN_YEARS)
    plan = await plan_age_policy(
        source.session(), RETENTION, target.schema, target.table, TimeDuration(amount=10, unit="year"),
    )
    await native_add(source, plan, "30 days")
    with pytest.raises(ActionRefused, match="review it again"):
        await setter.perform_reviewed(target.node_id, TEN_YEARS, fingerprint)
    current = (await state(source, target)).existing
    assert current is not None and current.older_than == "30 days"


async def test_refused_replacement_keeps_the_existing_policy(
    source: TimescaleSource, retention_table: PolicyTable,
) -> None:
    target = retention_table
    setter = registry(source).action(SetRetentionPolicy.name)
    assert isinstance(setter, SetRetentionPolicy)
    await setter.perform_reviewed(target.node_id, TEN_YEARS, await reviewed(setter, target.node_id, TEN_YEARS))
    before = await policies(source, target)
    overflowing = {"amount": 2_147_483_647, "unit": "year"}
    fingerprint = await reviewed(setter, target.node_id, overflowing)
    with pytest.raises(ActionRefused):
        await setter.perform_reviewed(target.node_id, overflowing, fingerprint)
    assert await policies(source, target) == before
    current = (await state(source, target)).existing
    assert current is not None and current.older_than == "10 years"


async def test_paused_policy_is_removable_but_not_resumed_by_replacement(
    source: TimescaleSource, retention_table: PolicyTable,
) -> None:
    target = retention_table
    actions = registry(source)
    setter = actions.action(SetRetentionPolicy.name)
    remover = actions.action(RemoveRetentionPolicy.name)
    assert isinstance(setter, SetRetentionPolicy) and isinstance(remover, RemoveRetentionPolicy)
    await setter.perform_reviewed(target.node_id, TEN_YEARS, await reviewed(setter, target.node_id, TEN_YEARS))
    job = (await policies(source, target))[0]["job_id"]
    plan = await plan_age_policy(source.session(), RETENTION, target.schema, target.table, None)
    await source.session().query(sql.SQL("SELECT job_id FROM {}(%s::integer, scheduled => false)").format(
        sql.Identifier(plan.strategy.function_schema, "alter_job"),
    ).as_string(), (job,))
    preview = await setter.preview(target.node_id, TWENTY_YEARS)
    assert preview.blocked and "paused" in preview.summary
    offers = await actions.action_offers(target.node_id)
    assert "paused" in (offers.reason_for(SetRetentionPolicy.name) or "")
    assert RemoveRetentionPolicy.name in {item.name for item in offers.actions}
    await remover.perform_reviewed(target.node_id, {}, await reviewed(remover, target.node_id, {}))
    assert await policies(source, target) == []


async def test_fixture_policy_is_read_from_public_config_without_change(source: TimescaleSource) -> None:
    inspected = await inspect_age_policy(source.session(), RETENTION, "lab", "metrics")
    assert inspected.existing is not None
    assert inspected.existing.older_than == "10 years"
    assert inspected.strategy.extension_version == source.version
    with pytest.raises(ActionRefused, match="paused"):
        age_policy_plan(RETENTION, inspected, TimeDuration(amount=1, unit="day"))
    again = await inspect_age_policy(source.session(), RETENTION, "lab", "metrics")
    assert age_policy_plan(RETENTION, again, None).fingerprint() == (
        age_policy_plan(RETENTION, inspected, None).fingerprint()
    )


async def test_jobs_view_lock_alone_blocks_external_policy_changes(
    source: TimescaleSource, retention_table: PolicyTable,
) -> None:
    target = retention_table
    plan = await plan_age_policy(
        source.session(), RETENTION, target.schema, target.table, TimeDuration(amount=10, unit="year"),
    )
    async with source.session().acquire() as owner:
        async with owner.transaction():
            await owner.execute("SET LOCAL lock_timeout = '2s'")
            await owner.execute(age_policy_execution.JOBS_LOCK)
            async with source.session().acquire() as writer:
                with pytest.raises(psycopg.errors.LockNotAvailable):
                    async with writer.transaction():
                        await writer.execute("SET LOCAL lock_timeout = '200ms'")
                        await writer.execute(sql.SQL("SELECT {}(%s::regclass, %s::interval)").format(
                            sql.Identifier(plan.strategy.function_schema, "add_retention_policy"),
                        ), (plan.target.relation_oid, "30 days"))
    assert await policies(source, target) == []


async def test_cancellation_releases_locks_without_adding_a_policy(
    source: TimescaleSource, retention_table: PolicyTable, monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = retention_table
    duration = TimeDuration(amount=10, unit="year")
    reviewed_plan = await plan_age_policy(source.session(), RETENTION, target.schema, target.table, duration)
    locked = asyncio.Event()
    calls = 0

    async def pause_after_locked_read(
        reader: PostgresReader, spec: AgePolicySpec, schema: str, table: str,
        older_than: TimeDuration | None,
    ) -> AgePolicyPlan:
        nonlocal calls
        result = await plan_age_policy(reader, spec, schema, table, older_than)
        calls += 1
        if calls == 2:
            locked.set()
            await asyncio.Event().wait()
        return result

    monkeypatch.setattr(age_policy_execution, "plan_age_policy", pause_after_locked_read)
    task = asyncio.create_task(age_policy_execution.execute_age_policy(
        source.session(), RETENTION, target.schema, target.table, duration, reviewed_plan.fingerprint(),
    ))
    try:
        await asyncio.wait_for(locked.wait(), timeout=4)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert await policies(source, target) == []
    async with asyncio.timeout(5):
        await native_add(source, reviewed_plan, "30 days")
    assert len(await policies(source, target)) == 1


@pytest.mark.parametrize("schema,table", [
    ("public", "ordinary"), ("lab", "integer_metrics"), ("lab", "hourly"),
    ("lab", "metrics'; SELECT 1; --"),
])
async def test_ineligible_targets_refuse_planning(source: TimescaleSource, schema: str, table: str) -> None:
    with pytest.raises(ActionRefused):
        await inspect_age_policy(source.session(), RETENTION, schema, table)


async def test_reader_cannot_plan_an_owner_operation(source: TimescaleSource) -> None:
    reader = PostgresSession(source.options(user="fixture_reader"))
    with pytest.raises(ActionRefused):
        await inspect_age_policy(reader, RETENTION, "lab", "metrics")


async def test_plain_database_has_no_policy_vocabulary(source: TimescaleSource) -> None:
    session = source.session(database="plain_fixture")
    names = {item.name for item in await PostgresActions(session, PostgresCatalog(session)).all_actions()}
    assert not {SetRetentionPolicy.name, RemoveRetentionPolicy.name} & names
