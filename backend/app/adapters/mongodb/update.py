"""Changing, adding and deleting the documents of a MongoDB collection (D287).

A cell is a field of one document, named by its `_id` and the digest it was
read with; a write is matched against the whole document read, so a document
changed in between is not written. Several documents are changed one at a
time, each on its own all or nothing, as ClickHouse's rows are (D272).
"""

from collections.abc import Callable
from typing import Any

from pymongo.errors import BulkWriteError

from app.adapters.fetch import FetchColumn
from app.adapters.mongodb.fetch import columns_of
from app.adapters.mongodb.inspection import CollectionFacts
from app.adapters.mongodb.relation import MongodbRelation
from app.adapters.mongodb.rows import (
    digest,
    editable,
    editing_reason,
    handle_of,
    insertable,
    inserting_reason,
    read_handle,
    unchanged,
    written_value,
)
from app.adapters.mongodb.session import (
    DOCUMENT_VALIDATION_FAILURE,
    DUPLICATE_KEY,
    Client,
    MongodbSession,
)
from app.adapters.mongodb.values import Tag, read_cell
from app.adapters.update import (
    CellsRejected,
    CellsUpdated,
    DeleteRowsRequest,
    DeleteRowsResult,
    InsertRowRequest,
    InsertRowResult,
    InsertRowsRequest,
    InsertRowsResult,
    RejectedCell,
    RejectedValue,
    RowConflict,
    RowsInserted,
    UpdateCellRequest,
    UpdateCellResult,
    UpdateCellsRequest,
    UpdateCellsResult,
    UpdatedRow,
    ValuesRejected,
)
from app.core.translation import N_, say

_REFUSALS = {
    DUPLICATE_KEY: N_("Another document already has that value in a unique index"),
    DOCUMENT_VALIDATION_FAILURE: N_("The collection's validator refused the document"),
}


def values_of(document: dict[str, Any], columns: list[FetchColumn]) -> list[str | None]:
    return [read_cell(document.get(column.name)) for column in columns]


class MongodbUpdate:
    def __init__(self, session: MongodbSession, relation: MongodbRelation) -> None:
        self._session = session
        self._relation = relation

    async def _target(
        self, node_id: str, reason: Callable[[CollectionFacts], str | None]
    ) -> tuple[CollectionFacts, list[FetchColumn], dict[str, Tag]]:
        facts = await self._relation.facts(node_id, structure=False)
        refused = reason(facts)
        if refused is not None:
            raise ValueError(refused)
        columns, tags = columns_of(facts)
        return facts, columns, tags

    @staticmethod
    def _column(columns: list[FetchColumn], name: str, *, editing: bool) -> FetchColumn:
        for column in columns:
            if column.name == name:
                if editing and not editable(column):
                    raise ValueError(say('Column "{column}" cannot be edited', column=name))
                if not editing and not insertable(column):
                    raise ValueError(say('Column "{column}" cannot be inserted', column=name))
                return column
        raise ValueError(say('Relation has no column "{column}"', column=name))

    async def _changed(
        self,
        client: Client,
        facts: CollectionFacts,
        columns: list[FetchColumn],
        handle: str,
        fields: dict[str, Any],
    ) -> UpdatedRow:
        """One document changed if it is still the one read, and read back."""
        key, version = read_handle(handle)
        collection = client[facts.database][facts.name]
        document = await collection.find_one({"_id": key})
        if document is None or digest(document) != version:
            raise RowConflict()
        with self._session.failures(_REFUSALS):
            answer = await collection.update_one(unchanged(document), {"$set": fields})
        if answer.matched_count == 0:
            raise RowConflict()
        now = await collection.find_one({"_id": key})
        if now is None:
            raise RowConflict()
        return UpdatedRow(row_handle=handle_of(now) or handle, values=values_of(now, columns))

    async def update_cell(self, request: UpdateCellRequest) -> UpdateCellResult:
        facts, columns, tags = await self._target(request.node_id, editing_reason)
        column = self._column(columns, request.column, editing=True)
        read_handle(request.row_handle)
        try:
            value = written_value(request.value, tags[column.name])
        except ValueError:
            raise ValueError(
                say("That value cannot be read as {sql}", sql=column.type.sql)
            ) from None
        async with self._session.client() as client:
            with self._session.failures(_REFUSALS):
                row = await self._changed(
                    client, facts, columns, request.row_handle, {column.name: value}
                )
        return UpdateCellResult(values=row.values, row_handle=row.row_handle)

    async def update_cells(self, request: UpdateCellsRequest) -> UpdateCellsResult:
        facts, columns, tags = await self._target(request.node_id, editing_reason)
        edits: list[dict[str, Any]] = []
        rejected: list[RejectedCell] = []
        for index, row in enumerate(request.rows):
            read_handle(row.row_handle)
            fields: dict[str, Any] = {}
            for cell in row.cells:
                column = self._column(columns, cell.column, editing=True)
                try:
                    fields[column.name] = written_value(cell.value, tags[column.name])
                except ValueError:
                    rejected.append(RejectedCell(row=index, column=column.name))
            edits.append(fields)
        if rejected:
            return CellsRejected(cells=rejected)
        async with self._session.client() as client:
            with self._session.failures(_REFUSALS):
                updated = [
                    await self._changed(client, facts, columns, row.row_handle, fields)
                    for row, fields in zip(request.rows, edits, strict=True)
                ]
        return CellsUpdated(rows=updated)

    def _documents(
        self,
        columns: list[FetchColumn],
        tags: dict[str, Tag],
        names: list[str],
        rows: list[list[str | None]],
    ) -> tuple[list[dict[str, Any]], list[RejectedValue]]:
        """New documents of the values given; a value left empty is no field.

        Nothing given at all is a document of its `_id` alone, which the
        driver makes.
        """
        named = [self._column(columns, name, editing=False) for name in names]
        documents: list[dict[str, Any]] = []
        rejected: list[RejectedValue] = []
        for index, row in enumerate(rows):
            document: dict[str, Any] = {}
            for column, text in zip(named, row, strict=True):
                if text is None:
                    continue
                try:
                    document[column.name] = written_value(text, tags[column.name])
                except ValueError:
                    rejected.append(RejectedValue(row=index, column=column.name, value=text[:200]))
            documents.append(document)
        return documents, rejected

    async def insert_row(self, request: InsertRowRequest) -> InsertRowResult:
        facts, columns, tags = await self._target(request.node_id, inserting_reason)
        [document], rejected = self._documents(
            columns,
            tags,
            [item.column for item in request.values],
            [[item.value for item in request.values]],
        )
        if rejected:
            column = self._column(columns, rejected[0].column, editing=False)
            raise ValueError(say("That value cannot be read as {sql}", sql=column.type.sql))
        async with self._session.client() as client:
            collection = client[facts.database][facts.name]
            with self._session.failures(_REFUSALS):
                answer = await collection.insert_one(document)
                stored = await collection.find_one({"_id": answer.inserted_id})
        if stored is None:
            return InsertRowResult(values=values_of(document, columns), row_handle=None)
        return InsertRowResult(values=values_of(stored, columns), row_handle=handle_of(stored))

    async def insert_rows(self, request: InsertRowsRequest) -> InsertRowsResult:
        facts, columns, tags = await self._target(request.node_id, inserting_reason)
        documents, rejected = self._documents(columns, tags, request.columns, request.rows)
        if rejected:
            return ValuesRejected(cells=rejected)
        async with self._session.client() as client:
            collection = client[facts.database][facts.name]
            with self._session.failures(_REFUSALS):
                try:
                    await collection.insert_many(documents, ordered=True)
                except BulkWriteError as failure:
                    # A server alone has no transaction to undo the block
                    # with, so the documents it took before refusing one are
                    # taken out again: the block goes in whole or not at all.
                    taken = int(failure.details.get("nInserted", 0))
                    if taken:
                        await collection.delete_many(
                            {"_id": {"$in": [document["_id"] for document in documents[:taken]]}}
                        )
                    raise
        return RowsInserted(inserted=len(documents))

    async def delete_rows(self, request: DeleteRowsRequest) -> DeleteRowsResult:
        facts, _, _ = await self._target(request.node_id, editing_reason)
        named = [read_handle(handle) for handle in request.row_handles]
        deleted = 0
        async with self._session.client() as client:
            collection = client[facts.database][facts.name]
            with self._session.failures():
                for key, version in named:
                    document = await collection.find_one({"_id": key})
                    if document is None or digest(document) != version:
                        raise RowConflict()
                    answer = await collection.delete_one(unchanged(document))
                    if answer.deleted_count == 0:
                        raise RowConflict()
                    deleted += 1
        return DeleteRowsResult(deleted=deleted)
