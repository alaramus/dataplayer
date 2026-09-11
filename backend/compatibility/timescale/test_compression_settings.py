"""Disposable mutation evidence for the reviewed compression settings strategy."""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from psycopg import sql

from app.adapters.actions import ActionRefused
from app.adapters.postgres.timescale.age_policy_action import SetCompressionPolicy
from app.adapters.postgres.timescale.compression_settings_action import (
    ConfigureCompression,
)
from app.adapters.postgres.timescale.compression_settings_plan import (
    plan_compression_settings,
)
from app.adapters.postgres.timescale.plans import OrderColumn
from compatibility.timescale.policy_tables import (
    PolicyTable,
    disposable_hypertable,
    registry,
    reviewed,
    rows,
)
from compatibility.timescale.source import TimescaleSource

_STORED = """
    SELECT attname, segmentby_column_index, orderby_column_index, orderby_asc, orderby_nullsfirst
    FROM timescaledb_information.compression_settings
    WHERE hypertable_schema = %s AND hypertable_name = %s
"""
_CHUNK_SETTINGS = """
    SELECT chunk::text AS chunk, segmentby, orderby
    FROM timescaledb_information.chunk_compression_settings
    WHERE hypertable = %s::regclass ORDER BY 1
"""
_ENABLED = """
    SELECT compression_enabled FROM timescaledb_information.hypertables
    WHERE hypertable_schema = %s AND hypertable_name = %s
"""
TIME_DESC = OrderColumn(column="observed_at", descending=True, nulls_first=True)


@pytest.fixture
async def table(source: TimescaleSource) -> AsyncIterator[PolicyTable]:
    async with disposable_hypertable(source, "settings") as target:
        yield target


def setter(source: TimescaleSource) -> ConfigureCompression:
    action = registry(source).action(ConfigureCompression.name)
    assert isinstance(action, ConfigureCompression)
    return action


async def stored(source: TimescaleSource, target: PolicyTable) -> tuple[tuple[str, ...], tuple[OrderColumn, ...]]:
    found = await source.session().query(_STORED, (target.schema, target.table))
    segment = sorted((row for row in found if row["segmentby_column_index"] is not None),
                     key=lambda row: row["segmentby_column_index"])
    order = sorted((row for row in found if row["orderby_column_index"] is not None),
                   key=lambda row: row["orderby_column_index"])
    return tuple(row["attname"] for row in segment), tuple(
        OrderColumn(column=row["attname"], descending=not row["orderby_asc"], nulls_first=row["orderby_nullsfirst"])
        for row in order
    )


async def enabled(source: TimescaleSource, target: PolicyTable) -> bool:
    return bool((await source.session().query(_ENABLED, (target.schema, target.table)))[0]["compression_enabled"])


async def apply(source: TimescaleSource, target: PolicyTable, params: dict[str, object]) -> None:
    action = setter(source)
    await action.perform_reviewed(target.node_id, params, await reviewed(action, target.node_id, params))


async def compress_first_chunk(source: TimescaleSource, target: PolicyTable) -> list[dict[str, Any]]:
    chunk = (await source.session().query(
        "SELECT chunk_schema, chunk_name FROM timescaledb_information.chunks "
        "WHERE hypertable_schema = %s AND hypertable_name = %s ORDER BY range_start LIMIT 1",
        (target.schema, target.table),
    ))[0]
    identity = sql.Identifier(chunk["chunk_schema"], chunk["chunk_name"]).as_string()
    statement = (
        "CALL public.convert_to_columnstore({})" if source.version == "2.18.0" else "SELECT public.compress_chunk({})"
    )
    await source.session().schema_change(sql.SQL(statement).format(sql.Literal(identity)).as_string())
    return await source.session().query(_CHUNK_SETTINGS, (target.identifier.as_string(),))


async def test_enabling_leaves_exactly_the_reviewed_lists_at_the_source(
    source: TimescaleSource, table: PolicyTable,
) -> None:
    before = await rows(source, table)
    actions = registry(source)
    offers = await actions.action_offers(table.node_id)
    assert ConfigureCompression.name in {item.name for item in offers.actions}
    assert offers.reason_for(SetCompressionPolicy.name) == "Enable compression on this hypertable first"
    preview = await setter(source).preview(table.node_id, {"segment_by": "value", "order_by": ""})
    assert not preview.blocked
    assert "Compression is not enabled yet" in preview.items
    assert 'New order by: "observed_at" DESC NULLS FIRST' in preview.items
    assert preview.fingerprint is not None
    await setter(source).perform_reviewed(table.node_id, {"segment_by": "value", "order_by": ""}, preview.fingerprint)
    assert await enabled(source, table)
    assert await stored(source, table) == (("value",), (TIME_DESC,))
    assert SetCompressionPolicy.name in {item.name for item in (await actions.action_offers(table.node_id)).actions}
    assert await rows(source, table) == before


async def test_change_after_compression_keeps_the_compressed_chunks_settings(
    source: TimescaleSource, table: PolicyTable,
) -> None:
    await apply(source, table, {"segment_by": "", "order_by": ""})
    chunk_settings = await compress_first_chunk(source, table)
    assert len(chunk_settings) == 1
    params = {"segment_by": "value", "order_by": "observed_at asc"}
    preview = await setter(source).preview(table.node_id, params)
    assert "Already compressed chunks keep the settings they were compressed with" in preview.items
    assert preview.fingerprint is not None
    await setter(source).perform_reviewed(table.node_id, params, preview.fingerprint)
    assert await stored(source, table) == (
        ("value",), (OrderColumn(column="observed_at", descending=False, nulls_first=False),),
    )
    assert await source.session().query(_CHUNK_SETTINGS, (table.identifier.as_string(),)) == chunk_settings


@pytest.mark.parametrize("params,message", [
    ({"segment_by": "missing", "order_by": ""}, 'no column "missing"'),
    ({"segment_by": "", "order_by": "value; DROP TABLE x"}, "no column"),
    ({"segment_by": "value", "order_by": "value desc"}, "more than once"),
])
async def test_lines_that_are_not_columns_are_refused_at_review(
    source: TimescaleSource, table: PolicyTable, params: dict[str, object], message: str,
) -> None:
    preview = await setter(source).preview(table.node_id, params)
    assert preview.blocked and message in preview.summary
    assert not await enabled(source, table)


async def test_external_change_after_review_requires_new_review(
    source: TimescaleSource, table: PolicyTable,
) -> None:
    await apply(source, table, {"segment_by": "", "order_by": ""})
    params = {"segment_by": "", "order_by": "value desc"}
    fingerprint = await reviewed(setter(source), table.node_id, params)
    await source.session().schema_change(sql.SQL(
        "ALTER TABLE {} SET (timescaledb.compress_segmentby = 'value')"
    ).format(table.identifier).as_string())
    with pytest.raises(ActionRefused, match="review it again"):
        await setter(source).perform_reviewed(table.node_id, params, fingerprint)
    assert (await stored(source, table))[0] == ("value",)


async def test_open_reader_makes_execution_refuse_instead_of_waiting(
    source: TimescaleSource, table: PolicyTable,
) -> None:
    params = {"segment_by": "", "order_by": ""}
    fingerprint = await reviewed(setter(source), table.node_id, params)
    async with source.session().acquire() as reader:
        async with reader.transaction():
            await reader.execute(sql.SQL("SELECT count(*) FROM {}").format(table.identifier))
            with pytest.raises(ActionRefused, match="busy"):
                await setter(source).perform_reviewed(table.node_id, params, fingerprint)
    assert not await enabled(source, table)


async def test_unsegmented_unique_column_is_disclosed_on_first_enabling(
    source: TimescaleSource, table: PolicyTable,
) -> None:
    await source.session().schema_change(sql.SQL("CREATE UNIQUE INDEX ON {} (value, observed_at)").format(
        table.identifier,
    ).as_string())
    preview = await setter(source).preview(table.node_id, {"segment_by": "", "order_by": ""})
    assert 'TimescaleDB recommends segmenting or ordering by the unique column "value"' in preview.items
    segmented = await setter(source).preview(table.node_id, {"segment_by": "value", "order_by": ""})
    assert not any("unique column" in item for item in segmented.items)


async def test_fixture_settings_are_planned_without_change(source: TimescaleSource) -> None:
    before = await source.session().query(_STORED, ("lab", "metrics"))
    planned = await plan_compression_settings(source.session(), "lab", "metrics", "", "")
    assert planned.enabled and planned.any_compressed
    assert planned.current_order_by is not None and "observed_at" in planned.current_order_by
    assert planned.strategy.extension_version == source.version
    assert await source.session().query(_STORED, ("lab", "metrics")) == before


@pytest.mark.parametrize("schema,name", [("public", "ordinary"), ("lab", "integer_metrics"), ("lab", "hourly")])
async def test_ineligible_targets_refuse_planning(source: TimescaleSource, schema: str, name: str) -> None:
    with pytest.raises(ActionRefused):
        await plan_compression_settings(source.session(), schema, name, "", "")
