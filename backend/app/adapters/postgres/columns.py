"""Validated PostgreSQL column DDL."""

from psycopg import sql

from app.adapters.column_changes import (
    AddColumnRequest,
    ColumnChangeResult,
    ColumnDefaultRequest,
    ColumnNullabilityRequest,
    ColumnNullabilityResult,
    ColumnTypeBlocked,
    ColumnTypeChanged,
    ColumnTypeChangeResult,
    ColumnTypeRequest,
    DropColumnRequest,
    NullabilityBlocked,
    NullabilityChanged,
    RenameColumnRequest,
)
from app.adapters.postgres.column_types import (
    POSTGRES_COLUMN_TYPE_OPTIONS,
    POSTGRES_COLUMN_TYPES,
)
from app.adapters.postgres.counting import (
    rows_the_type_cannot_read,
    rows_without_value,
)
from app.adapters.postgres.relation import PostgresRelation
from app.adapters.postgres.session import PostgresSession
from app.adapters.relation import Column, PrimaryKey, RelationModel

# What a refused type change means, by SQLSTATE. The code is safe to look at
# and the message beside it is not: PostgreSQL writes the offending value into
# the text of exactly these errors.
TYPE_CHANGE_REFUSALS = {
    # cannot_coerce: no conversion exists between the two types at all.
    "42846": "PostgreSQL has no conversion between these two types",
    # datatype_mismatch: the column's default cannot be cast to the new type.
    "42804": "Remove the column's default before changing its type",
    # feature_not_supported: a view or rule is built on this column.
    "0A000": "A view or rule uses this column, so its type cannot change",
    # invalid_text_representation.
    "22P02": "Some values cannot be read as the new type",
    # numeric_value_out_of_range.
    "22003": "Some values are out of range for the new type",
    # string_data_right_truncation.
    "22001": "Some values are too long for the new type",
}


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
            # Before the ALTER and outside its lock, so it is not what makes
            # the change safe: PostgreSQL rescans under ACCESS EXCLUSIVE and
            # remains the authority. It is what makes a refusal useful — the
            # driver's own message names the offending row.
            blocking, exact = await rows_without_value(
                self._session, model.schema_name, model.name, column.name
            )
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

    async def change_column_type(
        self, request: ColumnTypeRequest
    ) -> ColumnTypeChangeResult:
        model = await self._relation.relation_model(request.node_id)
        self._check_supported(model)
        column = next(
            (item for item in model.columns if item.name == request.name), None
        )
        if column is None:
            raise ValueError(f'Relation has no column "{request.name}"')
        if column.generated is not None:
            raise ValueError("A generated column takes its type from its expression")
        if column.identity is not None:
            raise ValueError("An identity column cannot change its type here")
        type_sql = POSTGRES_COLUMN_TYPES.get(request.type_code)
        option = next(
            (
                item
                for item in POSTGRES_COLUMN_TYPE_OPTIONS
                if item.code == request.type_code
            ),
            None,
        )
        if type_sql is None or option is None:
            raise ValueError(f'Unknown column type "{request.type_code}"')
        if column.type.sql == option.sql:
            raise ValueError(f'The column already has type "{option.sql}"')

        await self._check_conversion_exists(model, column.name, type_sql)
        blocking, exact = await self._rows_the_target_cannot_read(
            model, column, option.sql
        )
        if blocking > 0:
            return ColumnTypeBlocked(
                name=column.name, rows_not_convertible=blocking, exact=exact
            )

        # The conversion is composed here in full: the column through
        # Identifier, the type from the closed registry. USING is written
        # rather than left out because without it PostgreSQL uses assignment
        # casts only, and the change people actually ask for — a text column
        # that should be a number — would fail with advice to supply exactly
        # the expression this design refuses to accept from a client.
        statement = sql.SQL(
            "ALTER TABLE {} ALTER COLUMN {} TYPE {} USING {}::{}"
        ).format(
            sql.Identifier(model.schema_name, model.name),
            sql.Identifier(column.name),
            type_sql,
            sql.Identifier(column.name),
            type_sql,
        )
        await self._session.schema_change(
            statement.as_string(), refusals=TYPE_CHANGE_REFUSALS
        )
        return ColumnTypeChanged(name=column.name, type_sql=option.sql)

    async def _check_conversion_exists(
        self, model: RelationModel, name: str, type_sql: sql.SQL
    ) -> None:
        """Ask PostgreSQL whether these two types convert, reading no row.

        Restating the coercion rules here would be a second implementation of
        them, wrong the first time an extension adds a cast. `WHERE false`
        still parses and plans the expression, so the parser answers; no row is
        touched and no lock on the table is taken.
        """
        statement = sql.SQL("SELECT {}::{} FROM {} WHERE false").format(
            sql.Identifier(name),
            type_sql,
            sql.Identifier(model.schema_name, model.name),
        )
        await self._session.query(statement.as_string(), refusals=TYPE_CHANGE_REFUSALS)

    async def _rows_the_target_cannot_read(
        self, model: RelationModel, column: Column, type_name: str
    ) -> tuple[int, bool]:
        """Rows the new type cannot read — where the source can know without trying.

        Only for a string column, and that is not a shortcut: converting a
        string is PostgreSQL's own input function, which `pg_input_is_valid`
        asks without raising, so the count is exactly what the conversion will
        do. A cast function has no non-throwing form — there is no TRY_CAST —
        and running it to find out would be doing the thing being asked about.
        Elsewhere the count is zero and the failure is named by its SQLSTATE.
        """
        if column.type.category != "string":
            return 0, True
        return await rows_the_type_cannot_read(
            self._session,
            model.schema_name,
            model.name,
            column.name,
            type_name,
            TYPE_CHANGE_REFUSALS,
        )

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
