"""Creating a PostgreSQL relation from validated parts, with its first rows."""

from typing import Literal

from psycopg import sql

from app.adapters.catalog import CatalogNode
from app.adapters.postgres.catalog import PostgresCatalog
from app.adapters.postgres.column_types import (
    POSTGRES_COLUMN_TYPE_OPTIONS,
    POSTGRES_COLUMN_TYPES,
)
from app.adapters.postgres.counting import unreadable_values
from app.adapters.postgres.session import PostgresSession
from app.adapters.relation import ColumnTypeOption
from app.adapters.relation_changes import (
    CreateRelationRequest,
    CreateRelationResult,
    NewRelationOptions,
    RelationCreated,
)
from app.adapters.update import RejectedValue, ValuesRejected
from app.adapters.words import worded_titles
from app.core.translation import N_, say

# What a refused creation means, by SQLSTATE. The code is safe to look at and
# the message beside it is not: PostgreSQL writes the schema and the statement
# into the text of these.
CREATE_REFUSALS = {
    # duplicate_table: the name is taken by a table, view, index or sequence.
    "42P07": N_("Something with that name is already there"),
    # duplicate_column: two columns of one relation cannot share a name.
    "42701": N_("Two columns cannot have the same name"),
    # insufficient_privilege.
    "42501": N_("This connection may not create a relation in that schema"),
    # invalid_schema_name: the schema went away between the check and the DDL.
    "3F000": N_("That schema is no longer there"),
    # too_many_columns.
    "54011": N_("That is more columns than the source accepts"),
}

# The longest identifier PostgreSQL stores. A longer one is not refused by the
# server: it is truncated with a notice, so a column would quietly end up
# under a name nobody chose.
MAX_IDENTIFIER_BYTES = 63


class PostgresRelationChanges:
    """Creating a relation in a schema.

    Built on the catalog rather than on the session alone: what a container is,
    whether it exists and how the new relation is described afterwards are all
    questions the catalog already answers, and answering them a second time
    here would let the two disagree about what a node id means.
    """

    def __init__(self, session: PostgresSession, catalog: PostgresCatalog) -> None:
        self._session = session
        self._catalog = catalog

    async def new_relation_options(self, parent_node_id: str) -> NewRelationOptions:
        node = await self._container(parent_node_id)
        if node.kind != "schema":
            return NewRelationOptions(
                supported=False, reason=say("A table is created in a schema")
            )
        if node.is_system:
            return NewRelationOptions(
                supported=False,
                reason=say('"{schema}" belongs to the server', schema=node.name),
            )
        reason = await self._catalog.schema_action_reason(
            node.name, include_relations=False
        )
        if reason is not None:
            return NewRelationOptions(supported=False, reason=reason)
        return NewRelationOptions(
            supported=True,
            column_type_options=worded_titles(POSTGRES_COLUMN_TYPE_OPTIONS),
            text_type="text",
        )

    async def create_relation(
        self, request: CreateRelationRequest
    ) -> CreateRelationResult:
        options = await self.new_relation_options(request.parent_node_id)
        if not options.supported:
            raise ValueError(options.reason or say("This node cannot hold a relation"))
        schema = request.parent_node_id
        _check_identifier(request.name, "relation")
        chosen: list[tuple[sql.SQL, ColumnTypeOption]] = []
        for column in request.columns:
            _check_identifier(column.name, "column")
            type_sql = POSTGRES_COLUMN_TYPES.get(column.type_code)
            option = next(
                (
                    item
                    for item in POSTGRES_COLUMN_TYPE_OPTIONS
                    if item.code == column.type_code
                ),
                None,
            )
            if type_sql is None or option is None:
                raise ValueError(
                    say('Unknown column type "{code}"', code=column.type_code)
                )
            chosen.append((type_sql, option))

        rejected = await self._unreadable(request, [option for _, option in chosen])
        if rejected is not None:
            return rejected

        create = sql.SQL("CREATE TABLE {} ({})").format(
            sql.Identifier(schema, request.name),
            sql.SQL(", ").join(
                sql.SQL("{} {}").format(sql.Identifier(column.name), type_sql)
                for column, (type_sql, _) in zip(request.columns, chosen, strict=True)
            ),
        )
        insert = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
            sql.Identifier(schema, request.name),
            sql.SQL(", ").join(
                sql.Identifier(column.name) for column in request.columns
            ),
            sql.SQL(", ").join(sql.Placeholder() for _ in request.columns),
        )
        # One transaction over both, which is the whole point: PostgreSQL rolls
        # DDL back with everything else, so a row the relation cannot take
        # leaves no relation behind either.
        async with self._session.transaction(refusals=CREATE_REFUSALS) as work:
            await work.schema_change(create.as_string())
            if request.rows:
                await work.change_many(
                    insert.as_string(), [tuple(row) for row in request.rows]
                )
        return RelationCreated(
            node=await self._describe(schema, request.name),
            inserted=len(request.rows),
        )

    async def _container(self, parent_node_id: str) -> CatalogNode:
        """The node a relation would be created in, confirmed against the server.

        Through `path_to`, so an id means here exactly what it means when the
        catalog is walked, and a node that is gone answers the way it does
        everywhere else. Its last element is the node itself.
        """
        path = await self._catalog.path_to(parent_node_id)
        return path[-1]

    async def _describe(self, schema: str, name: str) -> CatalogNode:
        path = await self._catalog.path_to(f"{schema}.{name}")
        return path[-1]

    async def _unreadable(
        self, request: CreateRelationRequest, options: list[ColumnTypeOption]
    ) -> ValuesRejected | None:
        """Every value the chosen types cannot read, named before anything is made.

        The same `pg_input_is_valid` pass an insert makes, asked before the
        relation exists: the types are being chosen here, and "row 12, column
        price" arrives while the reader can still choose another one.
        """
        checked: list[tuple[str, str]] = []
        places: list[tuple[int, str, str]] = []
        pairs = list(zip(request.columns, options, strict=True))
        for index, row in enumerate(request.rows):
            for (column, option), value in zip(pairs, row, strict=True):
                if value is None:
                    continue
                checked.append((value, option.sql))
                places.append((index, column.name, value))
        rejected = await unreadable_values(self._session, checked)
        if not rejected:
            return None
        return ValuesRejected(
            cells=[
                RejectedValue(
                    row=places[at][0], column=places[at][1], value=places[at][2][:100]
                )
                for at in rejected[:200]
            ]
        )


def _check_identifier(name: str, what: Literal["relation", "column"]) -> None:
    if len(name.encode("utf-8")) > MAX_IDENTIFIER_BYTES:
        raise ValueError(
            say(
                "A PostgreSQL relation name cannot exceed {limit} bytes",
                limit=MAX_IDENTIFIER_BYTES,
            )
            if what == "relation"
            else say(
                "A PostgreSQL column name cannot exceed {limit} bytes",
                limit=MAX_IDENTIFIER_BYTES,
            )
        )
