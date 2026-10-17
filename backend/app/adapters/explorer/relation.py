"""Describing a file that states its own columns.

Three nodes have an answer here: a Parquet file, a worksheet and an editable
delimited file (D51). The first two state their types. A delimited header can
be added to, renamed or reduced, while every one of its columns remains text.
A document has no columns at all; everything else is refused with that reason.

The relational vocabulary a file has no notion of — a schema, an owner, a
persistence class, a storage strategy — is left out rather than filled in.
"""

from pathlib import Path

from anyio import to_thread

from app.adapters.dataset import DatasetInfo, WorksheetDataset
from app.adapters.explorer import parquet, workbook
from app.adapters.explorer.formats import format_of
from app.adapters.explorer.members import ResolvedNode, resolve_node
from app.adapters.explorer.readers import CsvReader
from app.adapters.explorer.storage import Storage
from app.adapters.protocol import NodeNotFound
from app.adapters.relation import Column, ColumnTypeOption, RelationModel
from app.core.translation import N_, say

# One reason for all three gates: nothing about the shape of a file dataset is
# changed through this source, so the structure screen says so once per gate
# rather than offering a command that would be refused (D2d).
READ_ONLY = N_("This source reads a file dataset and cannot change its shape")


class ExplorerRelations:
    """The `relation-model` capability of a tree of files."""

    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    async def relation_model(self, node_id: str) -> RelationModel:
        return await to_thread.run_sync(self._describe, node_id)

    def _describe(self, node_id: str) -> RelationModel:
        resolved = resolve_node(self._storage, node_id)
        if resolved.entry is None:
            raise NodeNotFound(node_id)
        if resolved.member is not None:
            with self._storage.local_file(resolved.place) as path:
                return _worksheet_model(resolved, path, node_id)
        file_format = format_of(resolved.name)
        if file_format not in {"delimited", "parquet"}:
            raise ValueError(say("This node states no columns of its own"))
        with self._storage.local_file(resolved.place) as path:
            if file_format == "delimited":
                return _delimited_model(path, node_id)
            return _parquet_model(path, node_id)


def _parquet_model(path: Path, node_id: str) -> RelationModel:
    columns, dataset = parquet.describe(path)
    return _model(
        node_id=node_id,
        name=path.name,
        columns=columns,
        row_estimate=dataset.rows,
        size_bytes=dataset.size_bytes,
        dataset=dataset,
    )


def _delimited_model(path: Path, node_id: str) -> RelationModel:
    page = CsvReader().read(path, 1, 0)
    return RelationModel(
        node_id=node_id,
        name=path.name,
        kind="dataset",
        size_bytes=path.stat().st_size,
        columns=[
            Column(
                position=position,
                name=column.name,
                type=column.type,
                nullable=True,
            )
            for position, column in enumerate(page.columns, start=1)
        ],
        column_changes_supported=True,
        column_operations=["add", "drop", "rename"],
        column_type_options=[
            ColumnTypeOption(code="text", title=say("Text"), sql="text")
        ],
        index_changes_reason=say("A delimited file has no indexes"),
        constraint_changes_reason=say("A delimited file has no constraints"),
    )


def _worksheet_model(resolved: ResolvedNode, path: Path, node_id: str) -> RelationModel:
    member = resolved.member
    if member is None or not member.isdigit():
        raise NodeNotFound(node_id)
    names, facts, sheet_count = workbook.read_header(path, int(member))
    columns = [
        Column(position=position, name=name, type=workbook.TEXT, nullable=True)
        for position, name in enumerate(names, start=1)
    ]
    dataset = WorksheetDataset(
        workbook=resolved.name,
        sheet_name=facts.title,
        sheet_position=facts.position,
        sheet_count=sheet_count,
        hidden=facts.hidden,
        rows=facts.rows,
        columns=facts.columns,
    )
    return _model(
        node_id=node_id,
        name=facts.title,
        columns=columns,
        row_estimate=facts.rows,
        size_bytes=None,
        dataset=dataset,
    )


def _model(
    *,
    node_id: str,
    name: str,
    columns: list[Column],
    row_estimate: int | None,
    size_bytes: int | None,
    dataset: DatasetInfo,
) -> RelationModel:
    return RelationModel(
        node_id=node_id,
        name=name,
        kind="dataset",
        columns=columns,
        row_estimate=row_estimate,
        size_bytes=size_bytes,
        dataset=dataset,
        column_changes_reason=say(READ_ONLY),
        index_changes_reason=say(READ_ONLY),
        constraint_changes_reason=say(READ_ONLY),
    )
