"""Disposable mutation evidence for the reviewed empty-table conversion."""

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from psycopg import sql

from app.adapters.actions import ActionRefused
from app.adapters.postgres.actions import PostgresActions
from app.adapters.postgres.catalog import PostgresCatalog
from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.timescale.conversion_action import ConvertToHypertable
from app.adapters.postgres.timescale.conversion_plan import inspect_conversion
from app.adapters.postgres.timescale.interval_action import SetChunkInterval
from app.adapters.specializations import TimescaleHypertable
from compatibility.timescale.policy_tables import PolicyTable, registry, reviewed
from compatibility.timescale.source import TimescaleSource

WEEK: dict[str, object] = {"time_column": "observed_at", "amount": 7, "unit": "day"}
_DIMENSIONS = """
    SELECT column_name, time_interval::text AS time_interval FROM timescaledb_information.dimensions
    WHERE hypertable_schema = %s AND hypertable_name = %s
"""
_HYPERTABLE = """
    SELECT count(*) AS hypertables FROM timescaledb_information.hypertables
    WHERE hypertable_schema = %s AND hypertable_name = %s
"""
_TIME_COLUMN = """
    SELECT attribute.attnotnull AS not_null,
           (SELECT count(*) FROM pg_catalog.pg_index AS single
            WHERE single.indrelid = attribute.attrelid AND single.indnatts = 1
              AND single.indkey[0] = attribute.attnum) AS single_indexes
    FROM pg_catalog.pg_attribute AS attribute
    WHERE attribute.attrelid = %s::pg_catalog.regclass AND attribute.attname = 'observed_at'
"""


@pytest.fixture
async def schema(source: TimescaleSource) -> AsyncIterator[str]:
    name = f"conversion_{uuid.uuid4().hex[:12]}"
    session = source.session()
    await session.schema_change(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(name)).as_string())
    try:
        yield name
    finally:
        await session.schema_change(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(name)).as_string())


async def table(
    source: TimescaleSource, schema: str, name: str = 'readings"quoted',
    columns: str = "(observed_at timestamptz, value integer)", *, kind: str = "",
) -> PolicyTable:
    target = PolicyTable(schema, name)
    await source.session().schema_change(sql.SQL("CREATE {} TABLE {} {}").format(
        sql.SQL(kind), target.identifier, sql.SQL(columns),
    ).as_string())
    return target


def converter(source: TimescaleSource) -> ConvertToHypertable:
    action = registry(source).action(ConvertToHypertable.name)
    assert isinstance(action, ConvertToHypertable)
    return action


async def converted(source: TimescaleSource, target: PolicyTable) -> bool:
    found = await source.session().query(_HYPERTABLE, (target.schema, target.table))
    return int(found[0]["hypertables"]) == 1


async def time_column(source: TimescaleSource, target: PolicyTable) -> dict[str, Any]:
    return (await source.session().query(_TIME_COLUMN, (target.identifier.as_string(),)))[0]


async def blocked_reason(source: TimescaleSource, target: PolicyTable, params: dict[str, object] = WEEK) -> str:
    preview = await converter(source).preview(target.node_id, params)
    assert preview.blocked and preview.fingerprint is None
    return preview.summary


async def test_empty_table_becomes_a_hypertable_with_the_same_identity(
    source: TimescaleSource, schema: str,
) -> None:
    target = await table(source, schema)
    actions = registry(source)
    assert ConvertToHypertable.name in {item.name for item in (await actions.action_offers(target.node_id)).actions}
    preview = await converter(source).preview(target.node_id, WEEK)
    assert '"observed_at" becomes NOT NULL' in preview.items
    assert 'TimescaleDB adds an index on "observed_at", newest first' in preview.items
    assert preview.fingerprint is not None
    await converter(source).perform_reviewed(target.node_id, WEEK, preview.fingerprint)
    assert await source.session().query(_DIMENSIONS, (target.schema, target.table)) == [
        {"column_name": "observed_at", "time_interval": "7 days"},
    ]
    column = await time_column(source, target)
    assert column["not_null"] is True and int(column["single_indexes"]) == 1
    node = (await PostgresCatalog(source.session()).path_to(target.node_id))[-1]
    assert node.id == target.node_id
    assert isinstance(getattr(node, "specialization", None), TimescaleHypertable)
    offers = await registry(source).action_offers(target.node_id)
    assert SetChunkInterval.name in {item.name for item in offers.actions}
    assert offers.reason_for(ConvertToHypertable.name) is None
    assert ConvertToHypertable.name not in {item.name for item in offers.actions}


async def test_one_column_time_index_is_reused(source: TimescaleSource, schema: str) -> None:
    target = await table(source, schema, columns="(observed_at timestamptz NOT NULL, value integer)")
    await source.session().schema_change(sql.SQL("CREATE INDEX ON {} (observed_at)").format(
        target.identifier,
    ).as_string())
    preview = await converter(source).preview(target.node_id, WEEK)
    assert 'An index on "observed_at" alone already exists, so TimescaleDB adds none' in preview.items
    assert not any("NOT NULL" in item for item in preview.items)
    assert preview.fingerprint is not None
    await converter(source).perform_reviewed(target.node_id, WEEK, preview.fingerprint)
    assert int((await time_column(source, target))["single_indexes"]) == 1


async def test_rows_refuse_before_and_after_review(source: TimescaleSource, schema: str) -> None:
    target = await table(source, schema)
    fingerprint = await reviewed(converter(source), target.node_id, WEEK)
    await source.session().schema_change(sql.SQL(
        "INSERT INTO {} (observed_at, value) VALUES ('2026-01-01 00:00:00+00', 1)"
    ).format(target.identifier).as_string())
    with pytest.raises(ActionRefused, match="not empty"):
        await converter(source).perform_reviewed(target.node_id, WEEK, fingerprint)
    assert not await converted(source, target)
    assert "not empty" in await blocked_reason(source, target)


async def test_unique_index_must_name_the_time_column(source: TimescaleSource, schema: str) -> None:
    refused = await table(source, schema, "refused", "(observed_at timestamptz NOT NULL, value integer UNIQUE)")
    assert 'must include "observed_at"' in await blocked_reason(source, refused)
    admitted = await table(
        source, schema, "admitted", "(observed_at timestamptz NOT NULL, value integer, UNIQUE (value, observed_at))",
    )
    await converter(source).perform_reviewed(
        admitted.node_id, WEEK, await reviewed(converter(source), admitted.node_id, WEEK),
    )
    assert await converted(source, admitted)
    assert not await converted(source, refused)


async def test_no_inherit_check_is_refused_but_keys_are_not(source: TimescaleSource, schema: str) -> None:
    checked = await table(
        source, schema, "checked", "(observed_at timestamptz NOT NULL, value integer CHECK (value > 0) NO INHERIT)",
    )
    assert "NO INHERIT" in await blocked_reason(source, checked)
    keyed = await table(
        source, schema, "keyed", "(observed_at timestamptz NOT NULL, id integer, PRIMARY KEY (id, observed_at))",
    )
    await converter(source).perform_reviewed(keyed.node_id, WEEK, await reviewed(converter(source), keyed.node_id, WEEK))
    assert await converted(source, keyed)


async def test_unlogged_table_is_refused(source: TimescaleSource, schema: str) -> None:
    target = await table(source, schema, kind="UNLOGGED")
    assert "logged" in await blocked_reason(source, target)


async def test_table_with_a_rule_is_refused(source: TimescaleSource, schema: str) -> None:
    target = await table(source, schema)
    await source.session().schema_change(sql.SQL(
        "CREATE RULE ignore_inserts AS ON INSERT TO {} DO INSTEAD NOTHING"
    ).format(target.identifier).as_string())
    assert "rules" in await blocked_reason(source, target)


async def test_inheriting_table_is_refused(source: TimescaleSource, schema: str) -> None:
    parent = await table(source, schema, "parent")
    child = PolicyTable(schema, "child")
    await source.session().schema_change(sql.SQL("CREATE TABLE {} () INHERITS ({})").format(
        child.identifier, parent.identifier,
    ).as_string())
    assert "inheritance" in await blocked_reason(source, child)
    assert "inheritance" in await blocked_reason(source, parent)


async def test_table_without_a_time_column_is_refused(source: TimescaleSource, schema: str) -> None:
    target = await table(source, schema, columns="(value integer)")
    assert "no timestamp or date column" in await blocked_reason(source, target)


async def test_wrong_column_names_the_choices(source: TimescaleSource, schema: str) -> None:
    target = await table(source, schema, columns="(observed_at timestamptz, day date, value integer)")
    reason = await blocked_reason(source, target, {**WEEK, "time_column": "value"})
    assert reason.endswith("observed_at, day")


async def test_table_a_hypertable_references_is_refused(source: TimescaleSource, schema: str) -> None:
    devices = await table(source, schema, "devices", "(id integer PRIMARY KEY, observed_at timestamptz)")
    readings = PolicyTable(schema, "readings")
    await source.session().schema_change(sql.SQL(
        "CREATE TABLE {} (observed_at timestamptz NOT NULL, device integer REFERENCES {} (id))"
    ).format(readings.identifier, devices.identifier).as_string())
    await source.session().query(
        "SELECT public.create_hypertable(%s::regclass, 'observed_at')", (readings.identifier.as_string(),),
    )
    assert "Foreign keys between this table and a hypertable" in await blocked_reason(source, devices)


async def test_owner_populated_fixture_and_plain_database_boundaries(source: TimescaleSource) -> None:
    with pytest.raises(ActionRefused, match="owner"):
        await inspect_conversion(PostgresSession(source.options(user="fixture_reader")), "public", "ordinary")
    offers = await registry(source).action_offers("public.ordinary")
    assert offers.reason_for(ConvertToHypertable.name) == "This table has no timestamp or date column to partition by"
    hypertable = await registry(source).action_offers("lab.metrics")
    assert hypertable.reason_for(ConvertToHypertable.name) is None
    plain = source.session(database="plain_fixture")
    actions = PostgresActions(plain, PostgresCatalog(plain))
    assert ConvertToHypertable.name not in {item.name for item in await actions.all_actions()}
    plain_offers = await actions.action_offers("public.ordinary")
    assert ConvertToHypertable.name not in {item.name for item in plain_offers.actions}
    assert plain_offers.reason_for(ConvertToHypertable.name) is None
