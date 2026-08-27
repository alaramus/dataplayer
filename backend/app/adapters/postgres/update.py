"""Optimistically locked updates of PostgreSQL rows."""

from psycopg import sql

from app.adapters.postgres.fetch import PostgresFetch, encode_cell, select_expression
from app.adapters.postgres.row_handle import decode_row_handle, encode_row_handle
from app.adapters.postgres.session import PostgresSession
from app.adapters.update import RowConflict, UpdateCellRequest, UpdateCellResult


class PostgresUpdate:
    def __init__(self, session: PostgresSession, fetch: PostgresFetch) -> None:
        self._session = session
        self._fetch = fetch

    async def update_cell(self, request: UpdateCellRequest) -> UpdateCellResult:
        schema, _, table = request.node_id.partition(".")
        if not table:
            raise ValueError(
                f'"{request.node_id}" is not a relation: expected schema.table'
            )
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
        row = rows[0]
        values = [encode_cell(row[item.name], item.type) for item in info.columns]
        key_values = [
            values[next(i for i, item in enumerate(info.columns) if item.name == name)]
            for name in info.primary_key
        ]
        if any(value is None for value in key_values):
            raise RowConflict
        return UpdateCellResult(
            values=values,
            row_handle=encode_row_handle(
                [value for value in key_values if value is not None],
                str(row["__dp_xmin"]),
            ),
        )
