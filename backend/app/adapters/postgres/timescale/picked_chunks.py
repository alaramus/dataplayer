"""Chunk maintenance over rows picked in the Chunks report (D209, D208).

The report is about the whole database, and its rows belong to many
hypertables; an action is about one of them. So the picked rows are read
again here, and the answer is the hypertable they all belong to and exactly
those chunks. Nothing is done: the action's own window plans and runs it.
"""

from collections.abc import Sequence
from typing import Any

from app.adapters.actions import ActionRefused
from app.adapters.operations import MAX_OPERATION_TARGETS
from app.adapters.postgres.catalog import PostgresCatalog
from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.timescale.chunk_maintenance_action import (
    DetachChunks,
    DropChunks,
    MaintainChunks,
    MergeChunks,
    MergeChunksConcurrently,
    MoveChunks,
    ReorderChunks,
)
from app.adapters.postgres.timescale.reports import REPORTS
from app.adapters.postgres.timescale.targets import user_table
from app.adapters.row_commands import PickedRowsAction, PickedRowsTarget

CHUNKS_REPORT_ID = next(report.node_id for report in REPORTS if report.key == "timescale.v1.chunks")
_KEY = ["chunk_schema", "chunk_name"]

# What each action is drawn as in the grid's toolbar. A split takes a point and
# an attach a table that is not a chunk, so neither is a set of picked chunks.
_OFFERED: tuple[tuple[type[MaintainChunks[Any]], str], ...] = (
    (DropChunks, "delete"),
    (MoveChunks, "drive_file_move"),
    (ReorderChunks, "sort"),
    (DetachChunks, "link_off"),
    (MergeChunks, "merge"),
    (MergeChunksConcurrently, "call_merge"),
)
PICKED_ACTIONS: tuple[PickedRowsAction, ...] = tuple(
    PickedRowsAction(
        action=kind.name, title=f"{kind.title}…", icon=icon, destructive=kind.destructive,
        requires=kind.requires, identified_by=_KEY,
    )
    for kind, icon in _OFFERED
)

_OWNERS = """
SELECT chunk.hypertable_schema::text AS schema_name, chunk.hypertable_name::text AS table_name
FROM timescaledb_information.chunks AS chunk
WHERE (chunk.chunk_schema::text, chunk.chunk_name::text) IN (
    SELECT * FROM ROWS FROM (pg_catalog.unnest(%s::text[]), pg_catalog.unnest(%s::text[]))
)
"""


def picked_actions(node_id: str) -> list[PickedRowsAction]:
    return list(PICKED_ACTIONS) if node_id == CHUNKS_REPORT_ID else []


async def resolve(
    session: PostgresSession, catalog: PostgresCatalog, node_id: str, action: str, keys: Sequence[Sequence[str]],
) -> PickedRowsTarget:
    if action not in {offered.action for offered in picked_actions(node_id)}:
        raise ActionRefused("not_applicable", "This is not offered over these rows")
    if len(keys) > MAX_OPERATION_TARGETS:
        raise ActionRefused("too_large", f"Pick at most {MAX_OPERATION_TARGETS} chunks at a time")
    if any(len(key) != len(_KEY) for key in keys):
        raise ActionRefused("not_applicable", "A chunk is named by its schema and its name")
    picked = list(dict.fromkeys((key[0], key[1]) for key in keys))
    async with session.inspection() as reader:
        rows = await reader.query(
            _OWNERS, ([schema for schema, _ in picked], [name for _, name in picked]), inspection=True,
        )
    hypertables = {(str(row["schema_name"]), str(row["table_name"])) for row in rows}
    if len(hypertables) > 1:
        raise ActionRefused(
            "not_applicable", f"The picked chunks belong to {len(hypertables)} hypertables; pick chunks of one",
        )
    if len(rows) != len(picked):
        raise ActionRefused("conflict", "Some picked rows are not chunks any more; read the report again")
    ((schema_name, table_name),) = hypertables
    _, table = await user_table(catalog, f"{schema_name}.{table_name}")
    return PickedRowsTarget(
        node_id=table.id,
        node_label=f"{schema_name}.{table_name}",
        params={"chunks": [{"schema_name": schema, "name": name} for schema, name in picked]},
        replaces=["ends_by", "starts_from"],
    )
