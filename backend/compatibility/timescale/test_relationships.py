import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
from psycopg import sql

from app.adapters.actions import ActionRefused
from app.adapters.fetch import FetchRequest, Sort
from app.adapters.postgres.dependencies import dependency_scope
from app.adapters.postgres.relation_context import PostgresRelationContext
from app.adapters.references import (
    FollowReferenceRequest,
    ReferencedRows,
    ReferenceValue,
)
from compatibility.timescale.source import TimescaleSource


@dataclass(frozen=True)
class RelatedTables:
    ordinary_schema: str
    timescale_schema: str

    @property
    def devices(self) -> str:
        return f"{self.ordinary_schema}.devices"

    @property
    def readings(self) -> str:
        return f"{self.timescale_schema}.readings"


@pytest.fixture
async def related_tables(source: TimescaleSource) -> AsyncIterator[RelatedTables]:
    suffix = uuid.uuid4().hex[:12]
    tables = RelatedTables(f"refs_{suffix}", f"metrics_{suffix}")
    session = source.session()
    devices = sql.Identifier(tables.ordinary_schema, "devices")
    readings = sql.Identifier(tables.timescale_schema, "readings")
    try:
        for schema in (tables.ordinary_schema, tables.timescale_schema):
            await session.schema_change(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)).as_string())
        await session.schema_change(sql.SQL(
            "CREATE TABLE {} (id integer PRIMARY KEY, label text NOT NULL)"
        ).format(devices).as_string())
        await session.schema_change(sql.SQL(
            "CREATE TABLE {} (observed_at timestamptz NOT NULL, device_id integer NOT NULL, "
            "CONSTRAINT readings_device_fkey FOREIGN KEY (device_id) REFERENCES {} (id))"
        ).format(readings, devices).as_string())
        await session.query(
            "SELECT public.create_hypertable(%s::regclass, 'observed_at', "
            "chunk_time_interval => INTERVAL '1 day')", (tables.readings,),
        )
        await session.schema_change(sql.SQL(
            "INSERT INTO {} VALUES (1, 'north'), (2, 'south')"
        ).format(devices).as_string())
        await session.schema_change(sql.SQL(
            "INSERT INTO {} VALUES ('2026-01-01 00:00:00+00', 1), "
            "('2026-01-02 00:00:00+00', 1), ('2026-01-03 00:00:00+00', 2)"
        ).format(readings).as_string())
        yield tables
    finally:
        for schema in (tables.timescale_schema, tables.ordinary_schema):
            await session.schema_change(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                sql.Identifier(schema),
            ).as_string())


async def test_ordinary_parent_cascade_refuses_cross_schema_hypertable_dependencies(
    source: TimescaleSource, related_tables: RelatedTables,
) -> None:
    tables = related_tables
    session = source.session()
    scope = await dependency_scope(session, tables.ordinary_schema, "devices")
    assert scope.complete
    assert (tables.timescale_schema, "readings") in scope.relations
    assert await PostgresRelationContext(session).cascade_reason(
        tables.ordinary_schema, "devices",
    ) is not None
    adapter = source.adapter()
    before = await adapter.relation_model(tables.readings)
    for action_name, node_id in (
        ("drop_relation", tables.devices), ("drop_schema", tables.ordinary_schema),
    ):
        action = adapter.action(action_name)
        with pytest.raises(ActionRefused, match="TimescaleDB"):
            await action.preview(node_id, {"cascade": True})
        with pytest.raises(ActionRefused, match="TimescaleDB"):
            await action.perform(node_id, {"cascade": True})
    assert await adapter.relation_model(tables.readings) == before
    assert len((await adapter.fetch(FetchRequest(node_id=tables.devices))).rows) == 2
    assert len((await adapter.fetch(FetchRequest(node_id=tables.readings))).rows) == 3


async def test_references_round_trip_to_the_logical_hypertable_after_reopening(
    source: TimescaleSource, related_tables: RelatedTables,
) -> None:
    tables = related_tables
    adapter = source.adapter()
    page = await adapter.fetch(FetchRequest(node_id=tables.readings))
    reference = next(item for item in page.references if item.name == "readings_device_fkey")
    target = await adapter.follow_reference(FollowReferenceRequest(
        node_id=tables.readings, reference=reference.name,
        values=[ReferenceValue(column="device_id", value="1")],
    ))
    assert isinstance(target, ReferencedRows)
    assert target.node.id == tables.devices
    devices = await adapter.fetch(FetchRequest(node_id=target.node.id, filters=target.filters))
    assert len(devices.rows) == 1
    incoming = await adapter.arriving_references(tables.devices)
    arriving = next(item for item in incoming if item.source_title == tables.readings)
    back = await adapter.follow_reference(FollowReferenceRequest(
        node_id=tables.devices, reference=arriving.name, direction="incoming",
        values=[ReferenceValue(column="id", value="1")],
    ))
    assert isinstance(back, ReferencedRows)
    assert back.node.id == tables.readings
    assert back.node.kind == "table"
    assert back.node.specialization is not None
    assert back.node.specialization.kind == "timescale_hypertable"
    request = FetchRequest(
        node_id=back.node.id, filters=back.filters, sort=[Sort(column="observed_at")],
    )
    expected = await adapter.fetch(request)
    assert len(expected.rows) == 2
    reopened = source.adapter()
    restored = FetchRequest.model_validate_json(request.model_dump_json())
    actual = await reopened.fetch(restored)
    assert actual.rows == expected.rows
    assert not actual.update_supported
    assert (await reopened.path_to(restored.node_id))[-1] == back.node
