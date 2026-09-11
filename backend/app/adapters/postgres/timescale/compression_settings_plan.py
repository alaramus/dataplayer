"""Plan a time hypertable's compression settings without changing them."""

import asyncio
import re
from collections.abc import Sequence

from psycopg import sql

from app.adapters.actions import ActionRefused
from app.adapters.postgres.inspection import PostgresReader
from app.adapters.postgres.timescale.age_policy_plan import TESTED_VERSIONS
from app.adapters.postgres.timescale.api import require_tested_server
from app.adapters.postgres.timescale.plans import (
    CompressionSettingsPlan,
    OrderColumn,
    TimeHypertable,
)
from app.adapters.postgres.timescale.profile import discover
from app.adapters.postgres.timescale.report_access import require_public_view
from app.adapters.postgres.timescale.targets import time_hypertable
from app.adapters.protocol import AdapterError

MAX_COLUMNS = 32
# A column name, then optional sort words; the name is checked against the table afterwards.
_ORDER_LINE = re.compile(
    r"^(?P<column>.+?)(?:\s+(?P<direction>asc|desc))?(?:\s+nulls\s+(?P<nulls>first|last))?$",
    re.IGNORECASE,
)

_VIEWS = {
    "hypertables": ("hypertable_schema", "hypertable_name", "compression_enabled"),
    "hypertable_compression_settings": ("hypertable", "segmentby", "orderby"),
    "chunks": ("hypertable_schema", "hypertable_name", "is_compressed"),
}

_COLUMNS = """
SELECT attname AS name FROM pg_catalog.pg_attribute
WHERE attrelid = %s::pg_catalog.oid AND attnum > 0 AND NOT attisdropped
ORDER BY attnum
"""

_ENABLED = """
SELECT compression_enabled FROM timescaledb_information.hypertables
WHERE hypertable_schema = %s AND hypertable_name = %s
"""

_CURRENT = """
SELECT segmentby, orderby FROM timescaledb_information.hypertable_compression_settings
WHERE hypertable = %s::pg_catalog.regclass
"""

_COMPRESSED = """
SELECT EXISTS (
    SELECT 1 FROM timescaledb_information.chunks
    WHERE hypertable_schema = %s AND hypertable_name = %s AND is_compressed
) AS any_compressed
"""

# Key columns only, as the source checks them; expression keys have no attribute.
_UNIQUE = """
SELECT DISTINCT attribute.attname AS name
FROM pg_catalog.pg_index AS unique_index
CROSS JOIN LATERAL pg_catalog.generate_series(0, unique_index.indnkeyatts - 1) AS position
JOIN pg_catalog.pg_attribute AS attribute
  ON attribute.attrelid = unique_index.indrelid AND attribute.attnum = unique_index.indkey[position]
WHERE unique_index.indrelid = %s::pg_catalog.oid
  AND unique_index.indisunique AND unique_index.indislive AND unique_index.indisvalid
  AND NOT unique_index.indisexclusion
ORDER BY 1
"""


def resolve_settings(
    segment_text: str, order_text: str, columns: Sequence[str],
) -> tuple[tuple[str, ...], tuple[OrderColumn, ...]]:
    """Each line names one existing column; nothing else from the form reaches the source."""
    known = set(columns)
    segment_by = tuple(_known(line, known) for line in _lines(segment_text, "segment-by"))
    order_by = tuple(_order_column(line, known) for line in _lines(order_text, "order-by"))
    named = [*segment_by, *(item.column for item in order_by)]
    repeated = next((name for name in named if named.count(name) > 1), None)
    if repeated is not None:
        raise ActionRefused("not_applicable", f'Column "{repeated}" is listed more than once')
    return segment_by, order_by


def _lines(text: str, label: str) -> list[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) > MAX_COLUMNS:
        raise ActionRefused("not_applicable", f"List at most {MAX_COLUMNS} {label} columns")
    if any(len(line) > 100 for line in lines):
        raise ActionRefused("not_applicable", "Each line names one column")
    return lines


def _known(name: str, known: set[str]) -> str:
    if name not in known:
        raise ActionRefused("not_applicable", f'This hypertable has no column "{name}"')
    return name


def _order_column(line: str, known: set[str]) -> OrderColumn:
    # A column whose own name ends in a sort word is taken whole.
    if line in known:
        return OrderColumn(column=line, descending=False, nulls_first=False)
    match = _ORDER_LINE.match(line)
    if match is None:
        raise ActionRefused("not_applicable", "Each line names one column")
    descending = (match["direction"] or "asc").lower() == "desc"
    # PostgreSQL's defaults: NULLS LAST ascending, NULLS FIRST descending.
    nulls_first = descending if match["nulls"] is None else match["nulls"].lower() == "first"
    return OrderColumn(column=_known(match["column"], known), descending=descending, nulls_first=nulls_first)


def effective_order_by(
    target: TimeHypertable, segment_by: Sequence[str], order_by: Sequence[OrderColumn],
) -> tuple[OrderColumn, ...]:
    # The rule of add_time_to_order_by_if_not_included (tsl/src/compression/create.c, 2.17.2 and
    # 2.18.0). Execution passes the result, so the source never has to apply it.
    if target.column_name in segment_by or any(item.column == target.column_name for item in order_by):
        return tuple(order_by)
    return (*order_by, OrderColumn(column=target.column_name, descending=True, nulls_first=True))


def segment_option(segment_by: Sequence[str]) -> str:
    return ", ".join(sql.Identifier(name).as_string() for name in segment_by)


def order_option(order_by: Sequence[OrderColumn]) -> str:
    return ", ".join(
        sql.Identifier(item.column).as_string()
        + (" DESC" if item.descending else " ASC")
        + (" NULLS FIRST" if item.nulls_first else " NULLS LAST")
        for item in order_by
    )


async def plan_compression_settings(
    reader: PostgresReader, schema_name: str, table_name: str, segment_text: str, order_text: str,
) -> CompressionSettingsPlan:
    try:
        async with asyncio.timeout(5):
            profile = await discover(reader)
            version = profile.feature.installed_version
            if not profile.available or version is None or version not in TESTED_VERSIONS:
                raise ActionRefused("not_applicable", "No supported TimescaleDB compression settings API")
            await require_tested_server(reader)
            target = await time_hypertable(reader, schema_name, table_name)
            for view, columns in _VIEWS.items():
                await require_public_view(reader, view, columns)
            names = await reader.query(_COLUMNS, (target.relation_oid,), inspection=True)
            segment_by, order_by = resolve_settings(segment_text, order_text, [row["name"] for row in names])
            identity = (target.schema_name, target.table_name)
            enabled = await _flag(reader, _ENABLED, identity, "compression_enabled")
            current = await reader.query(_CURRENT, (target.relation_oid,), inspection=True)
            if len(current) != 1:
                raise ActionRefused("not_applicable", "The current compression settings could not be read")
            any_compressed = await _flag(reader, _COMPRESSED, identity, "any_compressed")
            effective = effective_order_by(target, segment_by, order_by)
            listed = {*segment_by, *(item.column for item in effective)}
            unique = await reader.query(_UNIQUE, (target.relation_oid,), inspection=True)
            return CompressionSettingsPlan.model_validate({
                "target": target,
                "enabled": enabled,
                "current_segment_by": current[0].get("segmentby"),
                "current_order_by": current[0].get("orderby"),
                "segment_by": segment_by,
                "order_by": effective,
                "any_compressed": any_compressed,
                "unsegmented_unique": () if enabled else tuple(
                    row["name"] for row in unique if row["name"] not in listed
                ),
                "strategy": {"extension_version": version},
            })
    except TimeoutError:
        raise ActionRefused("not_applicable", "TimescaleDB compression settings planning timed out") from None
    except (AdapterError, ValueError):
        raise ActionRefused(
            "not_applicable", "TimescaleDB compression settings could not be inspected safely",
        ) from None


async def _flag(reader: PostgresReader, statement: str, params: tuple[str, str], column: str) -> bool:
    rows = await reader.query(statement, params, inspection=True)
    value = rows[0].get(column) if len(rows) == 1 else None
    if not isinstance(value, bool):
        raise ActionRefused("not_applicable", "The current compression settings could not be read")
    return value
