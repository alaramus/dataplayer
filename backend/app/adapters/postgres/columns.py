"""Validated PostgreSQL column DDL."""

from psycopg import sql

from app.adapters.column_changes import (
    AddColumnRequest,
    ColumnChangeResult,
    DropColumnRequest,
)
from app.adapters.postgres.column_types import POSTGRES_COLUMN_TYPES
from app.adapters.postgres.relation import PostgresRelation
from app.adapters.postgres.session import PostgresSession
from app.adapters.relation import RelationModel


class PostgresColumns:
    def __init__(self, session: PostgresSession, relation: PostgresRelation) -> None:
        self._session = session
        self._relation = relation

    async def add_column(self, request: AddColumnRequest) -> ColumnChangeResult:
        model = await self._relation.relation_model(request.node_id)
        self._check_supported(model)
        if request.name in {column.name for column in model.columns}:
            raise ValueError(f'Relation already has a column "{request.name}"')
        if len(request.name.encode("utf-8")) > 63:
            raise ValueError("A PostgreSQL column name cannot exceed 63 bytes")
        type_sql = POSTGRES_COLUMN_TYPES.get(request.type_code)
        if type_sql is None:
            raise ValueError(f'Unknown column type "{request.type_code}"')
        statement = sql.SQL("ALTER TABLE {} ADD COLUMN {} {}").format(
            sql.Identifier(model.schema_name, model.name),
            sql.Identifier(request.name),
            type_sql,
        )
        if not request.nullable:
            statement += sql.SQL(" NOT NULL")
        await self._session.schema_change(statement.as_string())
        return ColumnChangeResult(name=request.name)

    async def drop_column(self, request: DropColumnRequest) -> ColumnChangeResult:
        model = await self._relation.relation_model(request.node_id)
        self._check_supported(model)
        if request.name not in {column.name for column in model.columns}:
            raise ValueError(f'Relation has no column "{request.name}"')
        statement = sql.SQL("ALTER TABLE {} DROP COLUMN {}").format(
            sql.Identifier(model.schema_name, model.name),
            sql.Identifier(request.name),
        )
        await self._session.schema_change(statement.as_string())
        return ColumnChangeResult(name=request.name)

    @staticmethod
    def _check_supported(model: RelationModel) -> None:
        if not model.column_changes_supported:
            raise ValueError(
                model.column_changes_reason or "This relation cannot change columns"
            )
