"""Describing a file that states its own columns.

Only two nodes have an answer here: a Parquet file and a worksheet (D51). A
delimited file reads its column names off a line of text and gives them no
type, which is a header rather than a structure, and a document has no columns
at all. Everything else is refused with that as the reason.

The relational vocabulary a file has no notion of — a schema, an owner, a
persistence class, a storage strategy — is left out rather than filled in.
"""

from pathlib import Path

from anyio import to_thread

from app.adapters.dataset import DatasetInfo, WorksheetDataset
from app.adapters.file import parquet, workbook
from app.adapters.file.formats import format_of
from app.adapters.file.members import ResolvedNode, resolve_node
from app.adapters.file.session import FileSession
from app.adapters.protocol import NodeNotFound
from app.adapters.relation import Column, RelationModel

# One reason for all three gates: nothing about the shape of a file dataset is
# changed through this source, so the structure screen says so once per gate
# rather than offering a command that would be refused (D2d).
READ_ONLY = "This source reads a file dataset and cannot change its shape"


class FileRelations:
    """The `relation-model` capability of the file source."""

    def __init__(self, session: FileSession) -> None:
        self._session = session

    async def relation_model(self, node_id: str) -> RelationModel:
        return await to_thread.run_sync(self._describe, node_id)

    def _describe(self, node_id: str) -> RelationModel:
        resolved = resolve_node(self._session, node_id)
        if not resolved.path.exists():
            raise NodeNotFound(node_id)
        if resolved.member is not None:
            return _worksheet_model(resolved, node_id)
        if format_of(resolved.path.name) != "parquet":
            raise ValueError("This node states no columns of its own")
        return _parquet_model(resolved.path, node_id)


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


def _worksheet_model(resolved: ResolvedNode, node_id: str) -> RelationModel:
    member = resolved.member
    if member is None or not member.isdigit():
        raise NodeNotFound(node_id)
    names, facts, sheet_count = workbook.read_header(resolved.path, int(member))
    columns = [
        Column(position=position, name=name, type=workbook.TEXT, nullable=True)
        for position, name in enumerate(names, start=1)
    ]
    dataset = WorksheetDataset(
        workbook=resolved.path.name,
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
        column_changes_reason=READ_ONLY,
        index_changes_reason=READ_ONLY,
        constraint_changes_reason=READ_ONLY,
    )
