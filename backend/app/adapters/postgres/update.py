"""Optimistically locked updates of PostgreSQL rows."""

from typing import Any

from psycopg import sql

from app.adapters.cells import encode_cell
from app.adapters.postgres.counting import VALUE_REFUSALS, unreadable_values
from app.adapters.postgres.fetch import (
    PostgresFetch,
    RelationFetchInfo,
    row_identity_values,
    row_match,
    select_expression,
)
from app.adapters.postgres.row_handle import decode_row_handle, encode_row_handle
from app.adapters.postgres.session import PostgresSession
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


def _returning(info: RelationFetchInfo) -> sql.Composed:
    """Everything a changed row has to say about itself afterwards.

    The identity is part of it: a physically identified row has a new place
    after every write, so the handle can only be built from what came back.
    """
    columns = sql.SQL(", ").join(
        select_expression(column) for column in info.columns
    ) + sql.SQL(", xmin::text AS __dp_xmin")
    if info.row_identity == "physical":
        columns = columns + sql.SQL(
            ", tableoid::text AS __dp_tableoid, ctid::text AS __dp_ctid"
        )
    return columns


class PostgresUpdate:
    def __init__(self, session: PostgresSession, fetch: PostgresFetch) -> None:
        self._session = session
        self._fetch = fetch

    async def update_cell(self, request: UpdateCellRequest) -> UpdateCellResult:
        schema, table = self._relation_name(request.node_id)
        info = await self._fetch.relation_info(schema, table)
        if not info.update_supported:
            raise ValueError(info.update_reason or "This relation cannot be edited")
        known = {column.name: column for column in info.columns}
        column = known.get(request.column)
        if column is None:
            raise ValueError(f'Relation has no column "{request.column}"')
        if not column.editable:
            raise ValueError(f'Column "{request.column}" cannot be edited')

        handle = decode_row_handle(request.row_handle)
        if len(handle.keys) != len(row_match(info)):
            raise ValueError("The row handle is not valid for this relation")

        assignments = sql.SQL("{} = %s").format(sql.Identifier(request.column))
        conditions: list[sql.Composable] = [*row_match(info), sql.SQL("xmin::text = %s")]
        returning = _returning(info)
        statement = sql.SQL("UPDATE {} SET {} WHERE {} RETURNING {}").format(
            sql.Identifier(schema, table),
            assignments,
            sql.SQL(" AND ").join(conditions),
            returning,
        )
        if request.value is not None:
            # The same check the block edit makes, so one cell is refused as
            # precisely as two thousand are.
            rejected = await unreadable_values(
                self._session, [(request.value, column.type.sql)]
            )
            if rejected:
                raise ValueError(
                    f'That value cannot be read as {column.type.sql}'
                )
        params: list[object] = [request.value, *handle.keys, handle.version]
        rows = await self._session.change(
            statement.as_string(), tuple(params), refusals=VALUE_REFUSALS
        )
        if not rows:
            raise RowConflict
        values, row_handle = self._result(rows[0], info)
        if row_handle is None:
            raise RowConflict
        return UpdateCellResult(
            values=values,
            row_handle=row_handle,
        )

    async def update_cells(self, request: UpdateCellsRequest) -> UpdateCellsResult:
        schema, table = self._relation_name(request.node_id)
        info = await self._fetch.relation_info(schema, table)
        if not info.update_supported:
            raise ValueError(info.update_reason or "This relation cannot be edited")
        known = {column.name: column for column in info.columns}

        handles = []
        checked: list[tuple[str, str]] = []
        places: list[tuple[int, str]] = []
        for index, row in enumerate(request.rows):
            handle = decode_row_handle(row.row_handle)
            if len(handle.keys) != len(row_match(info)):
                raise ValueError("The row handle is not valid for this relation")
            handles.append(handle)
            for cell in row.cells:
                column = known.get(cell.column)
                if column is None:
                    raise ValueError(f'Relation has no column "{cell.column}"')
                if not column.editable:
                    raise ValueError(f'Column "{cell.column}" cannot be edited')
                if cell.value is not None:
                    checked.append((cell.value, column.type.sql))
                    places.append((index, cell.column))

        # Everything unreadable is named before anything is written: a paste
        # that half lands is worse than one that does not, because the reader
        # cannot tell which half without comparing what they pasted.
        rejected = await unreadable_values(self._session, checked)
        if rejected:
            return CellsRejected(
                cells=[
                    RejectedCell(row=places[at][0], column=places[at][1])
                    for at in rejected
                ]
            )

        returning = _returning(info)
        conditions = [*row_match(info), sql.SQL("xmin::text = %s")]

        updated: list[UpdatedRow] = []
        async with self._session.transaction(refusals=VALUE_REFUSALS) as work:
            for row, handle in zip(request.rows, handles, strict=True):
                assignments = sql.SQL(", ").join(
                    sql.SQL("{} = %s").format(sql.Identifier(cell.column))
                    for cell in row.cells
                )
                statement = sql.SQL("UPDATE {} SET {} WHERE {} RETURNING {}").format(
                    sql.Identifier(schema, table),
                    assignments,
                    sql.SQL(" AND ").join(conditions),
                    returning,
                )
                params = (
                    *(cell.value for cell in row.cells),
                    *handle.keys,
                    handle.version,
                )
                answer = await work.change(statement.as_string(), params)
                if not answer:
                    # Leaving the block without committing: the rows that did
                    # change go back with it.
                    raise RowConflict
                values, row_handle = self._result(answer[0], info)
                if row_handle is None:
                    raise RowConflict
                updated.append(UpdatedRow(row_handle=row_handle, values=values))
        return CellsUpdated(rows=updated)

    async def insert_row(self, request: InsertRowRequest) -> InsertRowResult:
        schema, table = self._relation_name(request.node_id)
        info = await self._fetch.relation_info(schema, table)
        if not info.insert_supported:
            raise ValueError(info.insert_reason or "This relation cannot accept rows")

        known = {column.name: column for column in info.columns}
        supplied = {item.column for item in request.values}
        for item in request.values:
            column = known.get(item.column)
            if column is None:
                raise ValueError(f'Relation has no column "{item.column}"')
            if not column.insertable:
                raise ValueError(f'Column "{item.column}" cannot be inserted')
        missing = [
            column.name
            for column in info.columns
            if column.insert_required and column.name not in supplied
        ]
        if missing:
            raise ValueError(f"Required columns were not supplied: {', '.join(missing)}")

        returning = _returning(info)
        if request.values:
            names = sql.SQL(", ").join(
                sql.Identifier(item.column) for item in request.values
            )
            placeholders = sql.SQL(", ").join(
                sql.Placeholder() for _ in request.values
            )
            statement = sql.SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING {}").format(
                sql.Identifier(schema, table), names, placeholders, returning
            )
            params = tuple(item.value for item in request.values)
        else:
            statement = sql.SQL("INSERT INTO {} DEFAULT VALUES RETURNING {}").format(
                sql.Identifier(schema, table), returning
            )
            params = ()
        rows = await self._session.change(statement.as_string(), params)
        values, row_handle = self._result(rows[0], info)
        return InsertRowResult(values=values, row_handle=row_handle)

    async def insert_rows(self, request: InsertRowsRequest) -> InsertRowsResult:
        schema, table = self._relation_name(request.node_id)
        info = await self._fetch.relation_info(schema, table)
        if not info.insert_supported:
            raise ValueError(info.insert_reason or "This relation cannot accept rows")
        known = {column.name: column for column in info.columns}
        targets = []
        for name in request.columns:
            column = known.get(name)
            if column is None:
                raise ValueError(f'Relation has no column "{name}"')
            if not column.insertable:
                raise ValueError(f'Column "{name}" cannot be inserted')
            targets.append(column)

        # Everything unreadable is named before anything is written, so a move
        # that cannot arrive whole does not arrive at all.
        checked: list[tuple[str, str]] = []
        places: list[tuple[int, str, str]] = []
        for index, row in enumerate(request.rows):
            for column, value in zip(targets, row, strict=True):
                if value is None:
                    continue
                checked.append((value, column.type.sql))
                places.append((index, column.name, value))
        rejected = await unreadable_values(self._session, checked)
        if rejected:
            return ValuesRejected(
                cells=[
                    RejectedValue(
                        row=places[at][0],
                        column=places[at][1],
                        value=places[at][2][:100],
                    )
                    for at in rejected[:200]
                ]
            )

        statement = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
            sql.Identifier(schema, table),
            sql.SQL(", ").join(sql.Identifier(column.name) for column in targets),
            sql.SQL(", ").join(sql.Placeholder() for _ in targets),
        )
        async with self._session.transaction(refusals=VALUE_REFUSALS) as work:
            await work.change_many(
                statement.as_string(), [tuple(row) for row in request.rows]
            )
        return RowsInserted(inserted=len(request.rows))

    async def delete_rows(self, request: DeleteRowsRequest) -> DeleteRowsResult:
        schema, table = self._relation_name(request.node_id)
        info = await self._fetch.relation_info(schema, table)
        if not info.delete_supported:
            raise ValueError(info.delete_reason or "This relation cannot delete rows")

        handles = [decode_row_handle(value) for value in request.row_handles]
        for handle in handles:
            if len(handle.keys) != len(row_match(info)):
                raise ValueError("The row handle is not valid for this relation")
        identities = {(tuple(handle.keys), handle.version) for handle in handles}
        if len(identities) != len(handles):
            raise ValueError("A row may be deleted only once")

        one_row = sql.SQL(" AND ").join(
            [*row_match(info), sql.SQL("xmin::text = %s")]
        )
        matches = sql.SQL(" OR ").join(
            sql.SQL("({})").format(one_row) for _ in handles
        )
        statement = sql.SQL(
            "WITH eligible AS MATERIALIZED ("
            "SELECT count(*) = %s AS ok FROM {} WHERE {}"
            ") DELETE FROM {} USING eligible "
            "WHERE eligible.ok AND ({}) RETURNING 1"
        ).format(
            sql.Identifier(schema, table),
            matches,
            sql.Identifier(schema, table),
            matches,
        )
        values = [value for handle in handles for value in (*handle.keys, handle.version)]
        params: tuple[object, ...] = (len(handles), *values, *values)
        rows = await self._session.change(statement.as_string(), params)
        if len(rows) != len(handles):
            raise RowConflict
        return DeleteRowsResult(deleted=len(rows))

    @staticmethod
    def _relation_name(node_id: str) -> tuple[str, str]:
        schema, _, table = node_id.partition(".")
        if not table:
            raise ValueError(f'"{node_id}" is not a relation: expected schema.table')
        return schema, table

    @staticmethod
    def _result(
        row: dict[str, Any], info: RelationFetchInfo
    ) -> tuple[list[str | None], str | None]:
        values = [encode_cell(row[column.name], column.type) for column in info.columns]
        # From the same RETURNING that produced the values, so the handle names
        # the version that was just written rather than the one that was read.
        keys = row_identity_values(row, info, info.columns)
        if keys is None:
            return values, None
        return values, encode_row_handle(keys, str(row["__dp_xmin"]))
