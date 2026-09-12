"""Disposable mutation evidence for the reviewed compression policy strategy."""

from collections.abc import AsyncIterator

import pytest
from psycopg import sql

from app.adapters.actions import ActionRefused
from app.adapters.postgres.timescale.age_policy_action import (
    RemoveCompressionPolicy,
    SetCompressionPolicy,
    SetRetentionPolicy,
)
from app.adapters.postgres.timescale.age_policy_plan import (
    COMPRESSION,
    AgePolicyState,
    inspect_age_policy,
    plan_age_policy,
)
from app.adapters.postgres.timescale.plans import TimeDuration
from compatibility.timescale.policy_tables import (
    DISCOVERED,
    PolicyTable,
    create_hypertable,
    disposable_hypertable,
    jobs,
    registry,
    reviewed,
    rows,
)
from compatibility.timescale.source import TimescaleSource

TEN_YEARS = {"amount": 10, "unit": "year"}
TWENTY_YEARS = {"amount": 20, "unit": "year"}
_COMPRESSED_CHUNKS = """
    SELECT count(*) FILTER (WHERE is_compressed) AS compressed
    FROM timescaledb_information.chunks WHERE hypertable_schema = %s AND hypertable_name = %s
"""


@pytest.fixture
async def compressed_table(source: TimescaleSource) -> AsyncIterator[PolicyTable]:
    async with disposable_hypertable(source, "compression", compressed=True) as target:
        yield target


async def policies(source: TimescaleSource, target: PolicyTable) -> list[dict[str, object]]:
    return await jobs(source, target, "policy_compression")


async def state(source: TimescaleSource, target: PolicyTable) -> AgePolicyState:
    return await inspect_age_policy(source.session(), COMPRESSION, target.schema, target.table)


async def compressed_chunks(source: TimescaleSource, target: PolicyTable) -> int:
    found = await source.session().query(_COMPRESSED_CHUNKS, (target.schema, target.table))
    return int(found[0]["compressed"])


async def test_set_replace_and_remove_through_registered_actions(
    source: TimescaleSource, compressed_table: PolicyTable,
) -> None:
    target = compressed_table
    actions = registry(source)
    before = await rows(source, target)
    offers = await actions.action_offers(target.node_id)
    assert SetCompressionPolicy.name in {item.name for item in offers.actions}
    assert offers.reason_for(RemoveCompressionPolicy.name) == "This hypertable has no compression policy"
    setter = actions.action(SetCompressionPolicy.name)
    remover = actions.action(RemoveCompressionPolicy.name)
    assert isinstance(setter, SetCompressionPolicy) and isinstance(remover, RemoveCompressionPolicy)

    preview = await setter.preview(target.node_id, TEN_YEARS)
    assert "No compression policy exists yet" in preview.items
    assert preview.fingerprint is not None
    await setter.perform_reviewed(target.node_id, TEN_YEARS, preview.fingerprint)
    first = await policies(source, target)
    assert len(first) == 1 and first[0]["scheduled"] is True
    current = (await state(source, target)).existing
    assert current is not None and current.older_than == "10 years"

    await setter.perform_reviewed(target.node_id, TWENTY_YEARS, await reviewed(setter, target.node_id, TWENTY_YEARS))
    second = await policies(source, target)
    assert len(second) == 1 and second[0]["job_id"] != first[0]["job_id"]
    current = (await state(source, target)).existing
    assert current is not None and current.older_than == "20 years"

    await remover.perform_reviewed(target.node_id, {}, await reviewed(remover, target.node_id, {}))
    assert await policies(source, target) == []
    assert await compressed_chunks(source, target) == 0
    assert await rows(source, target) == before


async def test_hypertable_without_compression_refuses_both_actions(
    source: TimescaleSource, compressed_table: PolicyTable,
) -> None:
    plain = PolicyTable(compressed_table.schema, "uncompressed")
    await create_hypertable(source, plain, compressed=False)
    actions = registry(source)
    offers = await actions.action_offers(plain.node_id)
    for name in (SetCompressionPolicy.name, RemoveCompressionPolicy.name):
        assert offers.reason_for(name) == "Enable compression on this hypertable first"
    assert SetRetentionPolicy.name in {item.name for item in offers.actions}
    setter = actions.action(SetCompressionPolicy.name)
    assert isinstance(setter, SetCompressionPolicy)
    preview = await setter.preview(plain.node_id, TEN_YEARS)
    assert preview.blocked and preview.fingerprint is None
    assert await policies(source, plain) == []


async def test_policy_added_externally_after_review_requires_new_review(
    source: TimescaleSource, compressed_table: PolicyTable,
) -> None:
    target = compressed_table
    setter = registry(source).action(SetCompressionPolicy.name)
    assert isinstance(setter, SetCompressionPolicy)
    fingerprint = await reviewed(setter, target.node_id, TEN_YEARS)
    plan = await plan_age_policy(
        source.session(), COMPRESSION, target.schema, target.table, TimeDuration(amount=10, unit="year"),
    )
    await source.session().query(sql.SQL("SELECT {}(%s::regclass, %s::interval)").format(
        sql.Identifier(plan.strategy.function_schema, "add_compression_policy"),
    ).as_string(), (plan.target.relation_oid, "30 days"))
    with pytest.raises(ActionRefused, match="review it again"):
        await setter.perform_reviewed(target.node_id, TEN_YEARS, fingerprint)
    current = (await state(source, target)).existing
    assert current is not None and current.older_than == "30 days"


async def test_refused_replacement_keeps_the_existing_policy(
    source: TimescaleSource, compressed_table: PolicyTable,
) -> None:
    target = compressed_table
    setter = registry(source).action(SetCompressionPolicy.name)
    assert isinstance(setter, SetCompressionPolicy)
    await setter.perform_reviewed(target.node_id, TEN_YEARS, await reviewed(setter, target.node_id, TEN_YEARS))
    before = await policies(source, target)
    overflowing = {"amount": 2_147_483_647, "unit": "year"}
    fingerprint = await reviewed(setter, target.node_id, overflowing)
    with pytest.raises(ActionRefused):
        await setter.perform_reviewed(target.node_id, overflowing, fingerprint)
    assert await policies(source, target) == before


async def test_strategy_verifies_the_installed_versions_add_shape(
    source: TimescaleSource, compressed_table: PolicyTable,
) -> None:
    target = compressed_table
    plan = await plan_age_policy(
        source.session(), COMPRESSION, target.schema, target.table, TimeDuration(amount=10, unit="year"),
    )
    assert plan.strategy.extension_version == source.version
    # 2.18 and 2.19 append hypercore_use_access_method and later releases drop it
    # again, so only the three leading arguments the strategy passes are fixed.
    found = await source.session().query(DISCOVERED, (plan.strategy.add_function_oid,))
    assert len(found) == 1
    assert found[0]["proname"] == "add_compression_policy"
    assert str(found[0]["arguments"]).startswith("2205 2276 16")
    assert found[0]["required"] <= 3


async def test_fixture_compressed_hypertable_is_read_without_change(source: TimescaleSource) -> None:
    before = await source.session().query(_COMPRESSED_CHUNKS, ("lab", "metrics"))
    inspected = await inspect_age_policy(source.session(), COMPRESSION, "lab", "metrics")
    assert inspected.existing is None
    assert inspected.strategy.kind == "compression"
    assert await source.session().query(_COMPRESSED_CHUNKS, ("lab", "metrics")) == before
