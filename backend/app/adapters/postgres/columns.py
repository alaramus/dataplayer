"""Validated PostgreSQL column DDL."""

from psycopg import sql

from app.adapters.column_changes import (
    AddColumnRequest,
    ColumnChangeResult,
    ColumnDefaultRequest,
    ColumnNullabilityRequest,
    ColumnNullabilityResult,
    DropColumnRequest,
    NullabilityBlocked,
    NullabilityChanged,
    RenameColumnRequest,
)
from app.adapters.postgres.column_types import POSTGRES_COLUMN_TYPES
from app.adapters.postgres.relation import PostgresRelation
from app.adapters.postgres.session import PostgresSession
from app.adapters.relation import PrimaryKey, RelationModel

# How far a search for rows without a value goes before it stops counting.
# Past this the answer is "a lot", which is all the next decision needs, and
# an unbounded scan is not run here any more than it is for a page of rows.
NULL_COUNT_CEILING = 1000


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

    async def rename_column(self, request: RenameColumnRequest) -> ColumnChangeResult:
        model = await self._relation.relation_model(request.node_id)
        self._check_supported(model)
        names = {column.name for column in model.columns}
        if request.name not in names:
            raise ValueError(f'Relation has no column "{request.name}"')
        if request.new_name in names:
            raise ValueError(f'Relation already has a column "{request.new_name}"')
        if len(request.new_name.encode("utf-8")) > 63:
            raise ValueError("A PostgreSQL column name cannot exceed 63 bytes")
        statement = sql.SQL("ALTER TABLE {} RENAME COLUMN {} TO {}").format(
            sql.Identifier(model.schema_name, model.name),
            sql.Identifier(request.name),
            sql.Identifier(request.new_name),
        )
        await self._session.schema_change(statement.as_string())
        return ColumnChangeResult(name=request.new_name)

    async def change_column_default(
        self, request: ColumnDefaultRequest
    ) -> ColumnChangeResult:
        model = await self._relation.relation_model(request.node_id)
        self._check_supported(model)
        column = next((item for item in model.columns if item.name == request.name), None)
        if column is None:
            raise ValueError(f'Relation has no column "{request.name}"')
        if column.generated is not None:
            raise ValueError("A generated column cannot have a default")
        if request.value is not None and "\x00" in request.value:
            # Composing the literal is what would fail, and it fails with a
            # driver error rather than with a rejected value. Said here, it is
            # a bad request like any other unusable default.
            raise ValueError("A default value cannot contain a NUL character")
        statement = sql.SQL("ALTER TABLE {} ALTER COLUMN {} ").format(
            sql.Identifier(model.schema_name, model.name),
            sql.Identifier(request.name),
        )
        if request.action == "drop":
            statement += sql.SQL("DROP DEFAULT")
        else:
            # A quoted string literal is deliberately not an SQL expression.
            # PostgreSQL coerces it using the target column's own type.
            statement += sql.SQL("SET DEFAULT {}").format(sql.Literal(request.value))
        await self._session.schema_change(statement.as_string())
        return ColumnChangeResult(name=request.name)

    async def change_column_nullability(
        self, request: ColumnNullabilityRequest
    ) -> ColumnNullabilityResult:
        model = await self._relation.relation_model(request.node_id)
        self._check_supported(model)
        column = next(
            (item for item in model.columns if item.name == request.name), None
        )
        if column is None:
            raise ValueError(f'Relation has no column "{request.name}"')
        if column.nullable == request.nullable:
            raise ValueError(
                "The column already accepts rows with no value"
                if request.nullable
                else "The column already requires a value in every row"
            )
        if request.nullable:
            self._check_may_stop_requiring(model, column.name, column.identity)
        else:
            blocking, exact = await self._rows_without_value(model, column.name)
            if blocking > 0:
                # Nothing has been locked and nothing has been altered: the
                # count is the whole answer, and the caller decides what to do
                # about the rows.
                return NullabilityBlocked(
                    name=column.name, rows_without_value=blocking, exact=exact
                )
        statement = sql.SQL("ALTER TABLE {} ALTER COLUMN {} {} NOT NULL").format(
            sql.Identifier(model.schema_name, model.name),
            sql.Identifier(column.name),
            sql.SQL("DROP") if request.nullable else sql.SQL("SET"),
        )
        await self._session.schema_change(statement.as_string())
        return NullabilityChanged(name=column.name, nullable=request.nullable)

    async def _rows_without_value(
        self, model: RelationModel, name: str
    ) -> tuple[int, bool]:
        """How many rows hold no value in this column, counted to a ceiling.

        Runs before the ALTER and outside its lock, so it is not what makes the
        change safe: PostgreSQL rescans under ACCESS EXCLUSIVE and remains the
        authority. It is what makes a refusal useful — the driver's own message
        names the offending row and therefore cannot be passed on.
        """
        statement = sql.SQL(
            "SELECT count(*) AS found FROM "
            "(SELECT 1 FROM {} WHERE {} IS NULL LIMIT {}) AS sample"
        ).format(
            sql.Identifier(model.schema_name, model.name),
            sql.Identifier(name),
            sql.Literal(NULL_COUNT_CEILING + 1),
        )
        # No parameters at all rather than an empty tuple: psycopg reads a
        # literal % as a placeholder as soon as any are supplied.
        rows = await self._session.query(statement.as_string())
        found = int(rows[0]["found"])
        return min(found, NULL_COUNT_CEILING), found <= NULL_COUNT_CEILING

    @staticmethod
    def _check_may_stop_requiring(
        model: RelationModel, name: str, identity: str | None
    ) -> None:
        """Two shapes always have a value, and PostgreSQL says so as a failure.

        Both are already in the model that was read to validate the request, so
        they are named here instead of being sent to the server to come back as
        an unattributable rejection.
        """
        if identity is not None:
            raise ValueError("An identity column always has a value")
        key = next(
            (
                constraint
                for constraint in model.constraints
                if isinstance(constraint, PrimaryKey) and name in constraint.columns
            ),
            None,
        )
        if key is not None:
            raise ValueError(f'Column "{name}" is part of primary key "{key.name}"')

    @staticmethod
    def _check_supported(model: RelationModel) -> None:
        if not model.column_changes_supported:
            raise ValueError(
                model.column_changes_reason or "This relation cannot change columns"
            )
