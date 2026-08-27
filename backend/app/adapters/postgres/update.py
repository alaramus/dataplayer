"""Optimistically locked updates of PostgreSQL rows."""

from typing import Any

from psycopg import sql

from app.adapters.postgres.fetch import (
    PostgresFetch,
    RelationFetchInfo,
    encode_cell,
    select_expression,
)
from app.adapters.postgres.row_handle import decode_row_handle, encode_row_handle
from app.adapters.postgres.session import PostgresSession
from app.adapters.update import (
    DeleteRowsRequest,
    DeleteRowsResult,
    InsertRowRequest,
    InsertRowResult,
    RowConflict,
    UpdateCellRequest,
    UpdateCellResult,
)


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
        if len(handle.keys) != len(info.primary_key):
            raise ValueError("The row handle is not valid for this relation")

        assignments = sql.SQL("{} = %s").format(sql.Identifier(request.column))
        conditions: list[sql.Composable] = [
            sql.SQL("{} = %s").format(sql.Identifier(name)) for name in info.primary_key
        ]
        conditions.append(sql.SQL("xmin::text = %s"))
        returning = sql.SQL(", ").join(
            select_expression(item) for item in info.columns
        ) + sql.SQL(", xmin::text AS __dp_xmin")
        statement = sql.SQL("UPDATE {} SET {} WHERE {} RETURNING {}").format(
            sql.Identifier(schema, table),
            assignments,
            sql.SQL(" AND ").join(conditions),
            returning,
        )
        params: list[object] = [request.value, *handle.keys, handle.version]
        rows = await self._session.change(statement.as_string(), tuple(params))
        if not rows:
            raise RowConflict
        values, row_handle = self._result(rows[0], info)
        if row_handle is None:
            raise RowConflict
        return UpdateCellResult(
            values=values,
            row_handle=row_handle,
        )

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

        returning = sql.SQL(", ").join(
            select_expression(column) for column in info.columns
        ) + sql.SQL(", xmin::text AS __dp_xmin")
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

    async def delete_rows(self, request: DeleteRowsRequest) -> DeleteRowsResult:
        schema, table = self._relation_name(request.node_id)
        info = await self._fetch.relation_info(schema, table)
        if not info.delete_supported:
            raise ValueError(info.delete_reason or "This relation cannot delete rows")

        handles = [decode_row_handle(value) for value in request.row_handles]
        for handle in handles:
            if len(handle.keys) != len(info.primary_key):
                raise ValueError("The row handle is not valid for this relation")
        identities = {(tuple(handle.keys), handle.version) for handle in handles}
        if len(identities) != len(handles):
            raise ValueError("A row may be deleted only once")

        one_row = sql.SQL(" AND ").join(
            [
                sql.SQL("{} = %s").format(sql.Identifier(name))
                for name in info.primary_key
            ]
            + [sql.SQL("xmin::text = %s")]
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
        if not info.primary_key:
            return values, None
        positions = {column.name: index for index, column in enumerate(info.columns)}
        keys = [values[positions[name]] for name in info.primary_key]
        if any(value is None for value in keys):
            return values, None
        return values, encode_row_handle(
            [value for value in keys if value is not None], str(row["__dp_xmin"])
        )
