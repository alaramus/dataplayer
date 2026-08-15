from typing import Any

from psycopg import sql

from app.adapters.fetch import (
    NULLARY_OPS,
    FetchColumn,
    FetchRequest,
    FetchResult,
    Filter,
)
from app.adapters.postgres.session import PostgresSession
from app.adapters.protocol import AdapterError

# Every operator maps to a fixed SQL fragment. Nothing here is ever built from
# client input: the client chooses an operator from a closed set, and that is
# the whole of its influence on the shape of the statement.
_COMPARISONS: dict[str, str] = {
    "eq": "=",
    "ne": "<>",
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
}


class PostgresFetch:
    """Reading rows out of a relation.

    Statements are assembled with psycopg.sql composition: identifiers through
    Identifier, values through placeholders. The old application formatted them
    into a template string and accepted a raw SQL fragment from the client,
    which is injection by construction.
    """

    def __init__(self, session: PostgresSession) -> None:
        self._session = session

    async def fetch(self, request: FetchRequest) -> FetchResult:
        schema, _, table = request.node_id.partition(".")
        if not table:
            raise ValueError(
                f'"{request.node_id}" is not a relation: expected schema.table'
            )

        columns = await self._columns(schema, table)
        known = {column.name for column in columns}
        self._reject_unknown_columns(request, known)

        statement, params = self._build(schema, table, request)
        rows = await self._session.query(statement.as_string(), tuple(params))

        # One row beyond the page tells us whether another page exists, without
        # a COUNT(*) on every request.
        has_more = len(rows) > request.limit
        page = rows[: request.limit]
        order = [column.name for column in columns]
        return FetchResult(
            columns=columns,
            rows=[
                [self._encode_binary(row[name]) for name in order] for row in page
            ],
            has_more=has_more,
        )

    @staticmethod
    def _encode_binary(value: Any) -> Any:
        """Convert PostgreSQL binary values to the hex representation."""
        if isinstance(value, bytes | bytearray | memoryview):
            return f"0x{bytes(value).hex().upper()}"
        return value

    @staticmethod
    def _reject_unknown_columns(request: FetchRequest, known: set[str]) -> None:
        """Validate identifiers against the relation before building anything.

        This is what makes the composition below safe: by the time a name
        reaches Identifier it is known to be a real column.
        """
        used = [item.column for item in request.filters]
        used += [item.column for item in request.sort]
        for column in used:
            if column not in known:
                raise ValueError(f'Relation has no column "{column}"')

    async def _columns(self, schema: str, table: str) -> list[FetchColumn]:
        rows = await self._session.query(
            """
            SELECT a.attname AS name,
                   format_type(a.atttypid, a.atttypmod) AS data_type
            FROM pg_attribute a
            JOIN pg_class c ON c.oid = a.attrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = %s AND c.relname = %s
              AND a.attnum > 0 AND NOT a.attisdropped
            ORDER BY a.attnum
            """,
            (schema, table),
        )
        if not rows:
            raise AdapterError("config", f'Relation "{schema}.{table}" does not exist')
        return [
            FetchColumn(name=row["name"], data_type=row["data_type"]) for row in rows
        ]

    def _build(
        self, schema: str, table: str, request: FetchRequest
    ) -> tuple[sql.Composed, list[Any]]:
        params: list[Any] = []
        statement = sql.SQL("SELECT * FROM {}").format(
            sql.Identifier(schema, table)
        )

        conditions = [self._condition(f, params) for f in request.filters]
        if conditions:
            statement = statement + sql.SQL(" WHERE ") + sql.SQL(" AND ").join(
                conditions
            )

        if request.sort:
            ordering = [
                sql.SQL("{} {}").format(
                    sql.Identifier(item.column),
                    sql.SQL("DESC" if item.descending else "ASC"),
                )
                for item in request.sort
            ]
            statement = statement + sql.SQL(" ORDER BY ") + sql.SQL(", ").join(ordering)

        # limit + 1 so the extra row can answer has_more.
        statement = statement + sql.SQL(" LIMIT %s OFFSET %s")
        params.extend([request.limit + 1, request.offset])
        return statement, params

    @staticmethod
    def _condition(filter_: Filter, params: list[Any]) -> sql.Composed:
        column = sql.Identifier(filter_.column)

        if filter_.op in NULLARY_OPS:
            keyword = "IS NULL" if filter_.op == "is_null" else "IS NOT NULL"
            return sql.SQL("{} {}").format(column, sql.SQL(keyword))

        if filter_.op == "contains":
            params.append(f"%{filter_.value}%")
            return sql.SQL("{}::text ILIKE %s").format(column)

        if filter_.op == "starts_with":
            params.append(f"{filter_.value}%")
            return sql.SQL("{}::text ILIKE %s").format(column)

        if filter_.op == "in":
            values = filter_.value if isinstance(filter_.value, list) else [filter_.value]
            params.append(list(values))
            return sql.SQL("{} = ANY(%s)").format(column)

        params.append(filter_.value)
        return sql.SQL("{} {} %s").format(
            column, sql.SQL(_COMPARISONS[filter_.op])
        )
