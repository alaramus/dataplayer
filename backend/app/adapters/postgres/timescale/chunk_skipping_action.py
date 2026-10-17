"""Chunk skipping on one column, turned on or off as a reviewed change (D207, H7).

The model was to hold chunk skipping per column, but which columns record
their ranges is kept only in a private catalog (D121), so the editor could not
say what is set now and a design would be a guess. Each direction is an action
of its own instead, called with `if_not_exists` so that asking for what already
holds changes nothing.
"""

import asyncio
from collections.abc import Mapping
from typing import Any, ClassVar, Literal

import psycopg
from psycopg import sql
from pydantic import BaseModel, ConfigDict, Field

from app.adapters.actions import (
    Action,
    ActionPreview,
    ActionRefused,
    ActionResult,
    ActsOn,
    FieldChoice,
    FieldHints,
)
from app.adapters.catalog import NodeKind
from app.adapters.features import FeatureCode
from app.adapters.postgres.catalog import PostgresCatalog
from app.adapters.postgres.inspection import PostgresReader
from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.timescale.api import RoutineShape, extension_routine
from app.adapters.postgres.timescale.execution import run_reviewed
from app.adapters.postgres.timescale.names import TIMESCALE_MENU
from app.adapters.postgres.timescale.plans import ReviewedPlan
from app.adapters.postgres.timescale.profile import discover, require_available
from app.adapters.postgres.timescale.report_access import require_public_view
from app.adapters.postgres.timescale.reports import TIMESCALE_SECTION_ID
from app.adapters.postgres.timescale.targets import user_table
from app.adapters.protocol import AdapterError
from app.core.access import Access
from app.core.translation import N_, say

Direction = Literal["enable", "disable"]
_OID = r"^[1-9][0-9]{0,9}$"
# sql/ddl_api.sql from 2.16: regclass 2205, name 19, boolean 16; record 2249.
SHAPES: dict[Direction, RoutineShape] = {
    "enable": RoutineShape("enable_chunk_skipping", "f", "2205 19 16", 2249, returns_set=True),
    "disable": RoutineShape("disable_chunk_skipping", "f", "2205 19 16", 2249, returns_set=True),
}
# The types Timescale computes a range for ("Integer-like, timestamp-like").
_RANGED = frozenset({
    "smallint", "integer", "bigint", "date", "timestamp without time zone", "timestamp with time zone",
})

_TARGET = """
SELECT relation.oid::text AS relation_oid,
       pg_catalog.format_type(attribute.atttypid, NULL) AS column_type,
       COALESCE(pg_catalog.current_setting('timescaledb.enable_chunk_skipping', true), 'off') AS setting
FROM timescaledb_information.hypertables AS hypertable
JOIN pg_catalog.pg_namespace AS namespace ON namespace.nspname = hypertable.hypertable_schema
JOIN pg_catalog.pg_class AS relation
  ON relation.relnamespace = namespace.oid AND relation.relname = hypertable.hypertable_name
LEFT JOIN pg_catalog.pg_attribute AS attribute
  ON attribute.attrelid = relation.oid AND attribute.attname = %s
 AND attribute.attnum > 0 AND NOT attribute.attisdropped
WHERE hypertable.hypertable_schema = %s AND hypertable.hypertable_name = %s
  AND pg_catalog.pg_has_role(relation.relowner, 'USAGE')
"""


_COLUMNS = """
SELECT attribute.attname AS name, pg_catalog.format_type(attribute.atttypid, NULL) AS type
FROM pg_catalog.pg_attribute AS attribute
JOIN pg_catalog.pg_class AS relation ON relation.oid = attribute.attrelid
JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = relation.relnamespace
WHERE namespace.nspname = %s AND relation.relname = %s AND attribute.attnum > 0 AND NOT attribute.attisdropped
ORDER BY attribute.attnum
"""


class ChunkSkippingParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column: str = Field(
        min_length=1, max_length=63, title=N_("Column"),
        description=N_("An integer, date or timestamp column queries filter on"),
    )


class ChunkSkippingPlan(ReviewedPlan):
    operation: Literal["chunk_skipping"] = "chunk_skipping"
    direction: Direction
    schema_name: str = Field(min_length=1, max_length=63)
    table_name: str = Field(min_length=1, max_length=63)
    relation_oid: str = Field(pattern=_OID)
    column: str = Field(min_length=1, max_length=63)
    function_schema: str = Field(min_length=1, max_length=63)
    function_oid: str = Field(pattern=_OID)
    # The setting in this connection's sessions, which queries need on too.
    setting: str = Field(max_length=20)


async def inspect_skipping(reader: PostgresReader, direction: Direction) -> str:
    """The API's schema, refusing a release or a role without it; checked with no column yet."""
    version = require_available(await discover(reader))
    await require_public_view(reader, "hypertables", ("hypertable_schema", "hypertable_name"))
    return (await extension_routine(reader, version, SHAPES[direction])).schema_name


async def plan_skipping(
    reader: PostgresReader, direction: Direction, schema_name: str, table_name: str, column: str,
) -> ChunkSkippingPlan:
    try:
        async with asyncio.timeout(5):
            version = require_available(await discover(reader))
            await require_public_view(reader, "hypertables", ("hypertable_schema", "hypertable_name"))
            routine = await extension_routine(reader, version, SHAPES[direction])
            rows = await reader.query(_TARGET, (column, schema_name, table_name), inspection=True)
            if len(rows) != 1:
                raise ActionRefused("not_applicable", say("Choose an owned hypertable"))
            column_type = rows[0].get("column_type")
            if column_type is None:
                raise ActionRefused("not_applicable", say('This hypertable has no column "{column}"', column=column))
            if direction == "enable" and column_type not in _RANGED:
                raise ActionRefused("not_applicable", say(
                    'TimescaleDB keeps ranges only of integer, date and timestamp columns, not of "{column}" ({type})',
                    column=column, type=column_type,
                ))
            return ChunkSkippingPlan(
                direction=direction, schema_name=schema_name, table_name=table_name,
                relation_oid=rows[0]["relation_oid"], column=column,
                function_schema=routine.schema_name, function_oid=routine.oid, setting=str(rows[0]["setting"]),
            )
    except TimeoutError:
        raise ActionRefused("not_applicable", say("Planning chunk skipping timed out")) from None
    except (AdapterError, ValueError):
        raise ActionRefused("not_applicable", _unreadable()) from None


def _unreadable() -> str:
    return say("The hypertable could not be inspected safely")


async def skipping_admission(session: PostgresSession) -> dict[Direction, str | None]:
    """Whether this release and role have the API; the column is the form's to name."""
    reasons: dict[Direction, str | None] = {}
    try:
        async with session.inspection() as reader:
            for direction in SHAPES:
                try:
                    await inspect_skipping(reader, direction)
                except ActionRefused as exc:
                    reasons[direction] = exc.message
                else:
                    reasons[direction] = None
    except (AdapterError, ValueError, TimeoutError):
        return dict.fromkeys(SHAPES, _unreadable())
    return reasons


class ChunkSkipping(Action[ChunkSkippingParams]):
    direction: ClassVar[Direction]
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"table"})
    acts_on: ClassVar[ActsOn] = "node"
    requires: ClassVar[Access] = "structure"
    feature_requirements: ClassVar[tuple[FeatureCode, ...]] = ("timescaledb",)
    menu_group: ClassVar[str | None] = TIMESCALE_MENU
    params_model = ChunkSkippingParams

    def __init__(self, session: PostgresSession, catalog: PostgresCatalog) -> None:
        self._session = session
        self._catalog = catalog

    def _items(self, plan: ChunkSkippingPlan) -> list[str]:
        column = sql.Identifier(plan.column).as_string()
        items = [
            say(
                "Chunks record the range of {column} as they are compressed, and a query filtering on it "
                "skips the chunks outside",
                column=column,
            )
            if plan.direction == "enable"
            else say("Chunks stop recording the range of {column}, if they did", column=column),
            say(
                "Changes nothing if it already holds: TimescaleDB keeps which columns record ranges where "
                "this application does not read"
            ),
        ]
        if plan.direction == "enable" and plan.setting != "on":
            items.append(say(
                "timescaledb.enable_chunk_skipping is off for this connection; queries use the ranges only "
                "in sessions that turn it on"
            ))
        return items

    async def field_hints(self, node_id: str | None) -> FieldHints:
        """The columns Timescale keeps a range of; which of them record one now is not readable."""
        schema, node = await user_table(self._catalog, node_id)
        async with self._session.inspection() as reader:
            rows = await reader.query(_COLUMNS, (schema.name, node.name), inspection=True)
        return FieldHints(choices={"column": [
            FieldChoice(value=str(row["name"]), label=f'{row["name"]} · {row["type"]}')
            for row in rows if row["type"] in _RANGED
        ]})

    async def preview(self, node_id: str | None, raw: Mapping[str, Any]) -> ActionPreview:
        params = self._validated(raw)
        schema, node = await user_table(self._catalog, node_id)
        try:
            async with self._session.inspection() as reader:
                plan = await plan_skipping(reader, self.direction, schema.name, node.name, params.column)
        except ActionRefused as exc:
            return ActionPreview(summary=exc.message, blocked=True)
        except (AdapterError, TimeoutError):
            return ActionPreview(summary=_unreadable(), blocked=True)
        target = sql.Identifier(schema.name, node.name).as_string()
        column = sql.Identifier(params.column).as_string()
        return ActionPreview(
            summary=(
                say("Skip chunks by {column} on {target}", column=column, target=target)
                if self.direction == "enable"
                else say("Stop skipping chunks by {column} on {target}", column=column, target=target)
            ),
            items=self._items(plan), fingerprint=plan.fingerprint(),
        )

    async def perform(self, node_id: str | None, raw: Mapping[str, Any]) -> ActionResult:
        raise ActionRefused("conflict", say("Review the chunk skipping plan before applying it"))

    async def perform_reviewed(
        self, node_id: str | None, raw: Mapping[str, Any], fingerprint: str,
    ) -> ActionResult:
        params = self._validated(raw)
        schema, node = await user_table(self._catalog, node_id)
        direction = self.direction

        async def replan(reader: PostgresReader) -> ChunkSkippingPlan:
            return await plan_skipping(reader, direction, schema.name, node.name, params.column)

        def locks(plan: ChunkSkippingPlan) -> list[sql.Composed]:
            return [sql.SQL("LOCK TABLE ONLY {} IN SHARE UPDATE EXCLUSIVE MODE").format(
                sql.Identifier(plan.schema_name, plan.table_name),
            )]

        async def apply(connection: psycopg.AsyncConnection[Any], plan: ChunkSkippingPlan) -> None:
            # The functions refuse to run unless the setting is on in this session.
            await connection.execute("SET LOCAL timescaledb.enable_chunk_skipping = on")
            await connection.execute(
                sql.SQL("SELECT {}(%s::pg_catalog.regclass, %s::pg_catalog.name, true)").format(
                    sql.Identifier(plan.function_schema, SHAPES[plan.direction].name),
                ),
                (plan.relation_oid, plan.column),
            )

        await run_reviewed(self._session, replan, locks, apply, fingerprint)
        return ActionResult(
            message=say("Chunk skipping turned on") if direction == "enable" else say("Chunk skipping turned off"),
            reload_node_ids=[schema.id, node.id, TIMESCALE_SECTION_ID],
        )


class EnableChunkSkipping(ChunkSkipping):
    name: ClassVar[str] = "timescale_enable_chunk_skipping"
    title: ClassVar[str] = N_("Skip chunks by a column")
    direction: ClassVar[Direction] = "enable"


class DisableChunkSkipping(ChunkSkipping):
    name: ClassVar[str] = "timescale_disable_chunk_skipping"
    title: ClassVar[str] = N_("Stop skipping chunks by a column")
    direction: ClassVar[Direction] = "disable"
