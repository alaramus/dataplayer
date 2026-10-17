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
from app.core.translation import say

CHUNKS_REPORT_ID = next(report.node_id for report in REPORTS if report.key == "timescale.v1.chunks")
_KEY = ["chunk_schema", "chunk_name"]

# What each action is drawn as in the grid's toolbar. A split takes a point and
# an attach a table that is not a chunk, so neither is a set of picked chunks.
def _offered() -> tuple[tuple[type[MaintainChunks[Any]], str, str], ...]:
    # Each action's title with the ellipsis of a command that opens a form,
    # worded per request: a title is English until it is shown (D226).
    return (
        (DropChunks, "delete", say("Drop chunks…")),
        (MoveChunks, "drive_file_move", say("Move chunks to a tablespace…")),
        (ReorderChunks, "sort", say("Reorder chunks by an index…")),
        (DetachChunks, "link_off", say("Detach chunks…")),
        (MergeChunks, "merge", say("Merge chunks…")),
        (MergeChunksConcurrently, "call_merge", say("Merge chunks, reads going on…")),
    )

_OWNERS = """
SELECT chunk.hypertable_schema::text AS schema_name, chunk.hypertable_name::text AS table_name
FROM timescaledb_information.chunks AS chunk
WHERE (chunk.chunk_schema::text, chunk.chunk_name::text) IN (
    SELECT * FROM ROWS FROM (pg_catalog.unnest(%s::text[]), pg_catalog.unnest(%s::text[]))
)
"""


def picked_actions(node_id: str) -> list[PickedRowsAction]:
    if node_id != CHUNKS_REPORT_ID:
        return []
    return [
        PickedRowsAction(
            action=kind.name, title=title, icon=icon, destructive=kind.destructive,
            requires=kind.requires, identified_by=_KEY,
        )
        for kind, icon, title in _offered()
    ]


async def resolve(
    session: PostgresSession, catalog: PostgresCatalog, node_id: str, action: str, keys: Sequence[Sequence[str]],
) -> PickedRowsTarget:
    if node_id != CHUNKS_REPORT_ID or action not in {kind.name for kind, _, _ in _offered()}:
        raise ActionRefused("not_applicable", say("This is not offered over these rows"))
    if len(keys) > MAX_OPERATION_TARGETS:
        raise ActionRefused("too_large", say("Pick at most {count} chunks at a time", count=MAX_OPERATION_TARGETS))
    if any(len(key) != len(_KEY) for key in keys):
        raise ActionRefused("not_applicable", say("A chunk is named by its schema and its name"))
    picked = list(dict.fromkeys((key[0], key[1]) for key in keys))
    async with session.inspection() as reader:
        rows = await reader.query(
            _OWNERS, ([schema for schema, _ in picked], [name for _, name in picked]), inspection=True,
        )
    hypertables = {(str(row["schema_name"]), str(row["table_name"])) for row in rows}
    if len(hypertables) > 1:
        raise ActionRefused("not_applicable", say(
            "The picked chunks belong to {count} hypertables; pick chunks of one", count=len(hypertables),
        ))
    if len(rows) != len(picked):
        raise ActionRefused("conflict", say("Some picked rows are not chunks any more; read the report again"))
    ((schema_name, table_name),) = hypertables
    _, table = await user_table(catalog, f"{schema_name}.{table_name}")
    return PickedRowsTarget(
        node_id=table.id,
        node_label=f"{schema_name}.{table_name}",
        params={"chunks": [{"schema_name": schema, "name": name} for schema, name in picked]},
        replaces=["ends_by", "starts_from"],
    )
