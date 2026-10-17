"""Validated PostgreSQL index DDL."""

from psycopg import sql

from app.adapters.indexes import (
    CreateIndexRequest,
    CreateIndexResult,
    DropIndexRequest,
    IndexBlocked,
    IndexCreated,
    IndexDropped,
)
from app.adapters.postgres.counting import repeating_groups
from app.adapters.postgres.index_methods import POSTGRES_INDEX_METHOD_SQL
from app.adapters.postgres.relation import PostgresRelation, qualified, schema_of
from app.adapters.postgres.session import PostgresSession
from app.adapters.relation import Index, PrimaryKey, RelationModel, UniqueConstraint
from app.core.translation import N_, say

# What a refused index command means, by SQLSTATE. The message beside the code
# is not safe to pass on: PostgreSQL writes the duplicated key value into it.
INDEX_REFUSALS = {
    # undefined_object: no default operator class for this type and method.
    "42704": N_("That index method does not fit the type of these columns"),
    # unique_violation: values repeat, found by the build rather than the count.
    "23505": N_("Some values repeat, so a unique index cannot be built"),
    # feature_not_supported. Whether a method can be unique or cover several
    # columns is checked from the published flags before the statement, so the
    # case that reaches here is the partitioned one.
    "0A000": N_("A unique index on a partitioned table must include its partition key"),
    # dependent_objects_still_exist.
    "2BP01": N_("Something else depends on this index"),
    # duplicate_table: a name clash the server resolves for us, normally.
    "42P07": N_("An index of that name already exists"),
}


class PostgresIndexes:
    def __init__(self, session: PostgresSession, relation: PostgresRelation) -> None:
        self._session = session
        self._relation = relation

    async def create_index(self, request: CreateIndexRequest) -> CreateIndexResult:
        model = await self._relation.relation_model(request.node_id)
        self._check_supported(model)
        known = {column.name for column in model.columns}
        for column in request.columns:
            if column not in known:
                raise ValueError(say('Relation has no column "{column}"', column=column))

        method = next(
            (item for item in model.index_methods if item.code == request.method), None
        )
        method_sql = POSTGRES_INDEX_METHOD_SQL.get(request.method)
        if method is None or method_sql is None:
            raise ValueError(say('Unknown index method "{method}"', method=request.method))
        # Both limits came from the server with the method, so refusing here
        # says the same thing the server would, one round trip earlier.
        if request.unique and not method.unique_supported:
            raise ValueError(say("{title} cannot build a unique index", title=method.title))
        if len(request.columns) > 1 and not method.multi_column_supported:
            raise ValueError(say("{title} cannot index more than one column", title=method.title))

        if request.unique:
            groups, exact = await repeating_groups(
                self._session, schema_of(model), model.name, request.columns
            )
            if groups > 0:
                # Nothing was built and nothing was locked: the count is the
                # whole answer, and the caller decides what to do about it.
                return IndexBlocked(duplicate_groups=groups, exact=exact)

        before = {index.name for index in model.indexes}
        # No name in the statement: PostgreSQL derives one from the relation
        # and the columns and makes it unique against the schema, which no
        # client could do without reading the catalog.
        statement = sql.SQL("CREATE {}INDEX ON {} USING {} ({})").format(
            sql.SQL("UNIQUE ") if request.unique else sql.SQL(""),
            qualified(model),
            method_sql,
            sql.SQL(", ").join(sql.Identifier(name) for name in request.columns),
        )
        await self._session.schema_change(
            statement.as_string(), refusals=INDEX_REFUSALS
        )
        return IndexCreated(
            name=await self._created_name(request, before, method.sql)
        )

    async def drop_index(self, request: DropIndexRequest) -> IndexDropped:
        model = await self._relation.relation_model(request.node_id)
        self._check_supported(model)
        index = next(
            (item for item in model.indexes if item.name == request.name), None
        )
        if index is None:
            raise ValueError(say('Relation has no index "{name}"', name=request.name))
        self._check_free_of_constraints(model, index)
        # No CASCADE, the rule D27 set for a column: an outside dependency
        # stops the operation instead of disappearing under it.
        statement = sql.SQL("DROP INDEX {}").format(
            sql.Identifier(schema_of(model), index.name)
        )
        await self._session.schema_change(
            statement.as_string(), refusals=INDEX_REFUSALS
        )
        return IndexDropped(name=index.name)

    async def _created_name(
        self, request: CreateIndexRequest, before: set[str], method_name: str
    ) -> str:
        """Which index was just made, since CREATE INDEX reports nothing.

        The relation is read again and the answer is the index that was not
        there before and covers exactly what was asked for. Two identical
        indexes appearing at the same instant is the only ambiguity, and then
        the first by name is taken rather than designed for.
        """
        model = await self._relation.relation_model(request.node_id)
        made = [
            index.name
            for index in sorted(model.indexes, key=lambda item: item.name)
            if index.name not in before
            and index.columns == request.columns
            and index.unique == request.unique
            and index.method == method_name
        ]
        return made[0] if made else ""

    @staticmethod
    def _check_supported(model: RelationModel) -> None:
        if not model.index_changes_supported:
            raise ValueError(
                model.index_changes_reason or say("This relation cannot change indexes")
            )

    @staticmethod
    def _check_free_of_constraints(model: RelationModel, index: Index) -> None:
        """An index a constraint stands on is dropped through the constraint.

        PostgreSQL refuses this itself, but it can only be told which
        constraint by a message that is not safe to relay. The relation model
        already holds the constraints, so the answer is composed from what was
        read rather than from what the driver said.
        """
        if index.primary:
            raise ValueError(
                say('Index "{name}" belongs to the primary key; drop that instead', name=index.name)
            )
        owner = next(
            (
                constraint
                for constraint in model.constraints
                if isinstance(constraint, PrimaryKey | UniqueConstraint)
                and constraint.name == index.name
            ),
            None,
        )
        if owner is not None:
            raise ValueError(
                say(
                    'Index "{name}" belongs to constraint "{constraint}"; drop that instead',
                    name=index.name,
                    constraint=owner.name,
                )
            )
