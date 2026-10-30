"""Creating a SQLite table with the rows it starts with (D45, D256).

The table and its rows in one transaction, as on PostgreSQL: SQLite's
structure changes are transactional (D253), so a table whose rows are refused
is never left behind. A column of the published types takes any value by its
affinity, so no value is refused for its type.
"""

import sqlite3

from app.adapters.catalog import CatalogNode, SchemaNode
from app.adapters.relation_changes import (
    CreateRelationRequest,
    CreateRelationResult,
    NewRelationOptions,
    RelationCreated,
)
from app.adapters.sqlite import ids
from app.adapters.sqlite.catalog import SqliteCatalog
from app.adapters.sqlite.inspection import SCHEMA
from app.adapters.sqlite.rows import written
from app.adapters.sqlite.session import SqliteSession
from app.adapters.sqlite.sql import SQL, Identifier
from app.adapters.sqlite.types import build_column_type
from app.adapters.sqlite.update import WRITING
from app.adapters.sqlite.vocabulary import SQLITE_COLUMN_TYPE_OPTIONS, column_type
from app.adapters.words import worded_titles
from app.core.translation import say


class SqliteRelationChanges:
    def __init__(self, session: SqliteSession, catalog: SqliteCatalog) -> None:
        self._session = session
        self._catalog = catalog

    async def new_relation_options(self, parent_node_id: str) -> NewRelationOptions:
        node = (await self._catalog.path_to(parent_node_id))[-1]
        if not isinstance(node, SchemaNode):
            return NewRelationOptions(supported=False, reason=say("A table is created in a schema"))
        return NewRelationOptions(
            supported=True,
            column_type_options=worded_titles(SQLITE_COLUMN_TYPE_OPTIONS),
            text_type="text",
        )

    async def create_relation(self, request: CreateRelationRequest) -> CreateRelationResult:
        options = await self.new_relation_options(request.parent_node_id)
        if not options.supported:
            raise ValueError(options.reason or say("This node cannot hold a relation"))
        if request.name.lower().startswith("sqlite_"):
            raise ValueError(say('A name starting "sqlite_" is SQLite\'s own'))
        if len({column.name.lower() for column in request.columns}) != len(request.columns):
            # SQLite compares column names without case.
            raise ValueError(say("A column may be named only once"))
        types = []
        for asked in request.columns:
            option = column_type(asked.type_code, strict=False)
            if option is None:
                raise ValueError(say('Unknown column type "{code}"', code=asked.type_code))
            types.append(build_column_type(option.sql))
        table = Identifier(SCHEMA, request.name)
        create = SQL("CREATE TABLE {} ({})").format(
            table,
            SQL(", ").join(
                SQL("{} " + type_.sql).format(Identifier(column.name))
                for column, type_ in zip(request.columns, types, strict=True)
            ),
        )
        insert = SQL("INSERT INTO {} ({}) VALUES ({})").format(
            table,
            SQL(", ").join(Identifier(column.name) for column in request.columns),
            SQL(", ").join(SQL("?") for _ in request.columns),
        )
        rows = [
            tuple(written(value, type_) for value, type_ in zip(row, types, strict=True))
            for row in request.rows
        ]

        def work(connection: sqlite3.Connection) -> None:
            connection.execute(create.text())
            if rows:
                connection.executemany(insert.text(), rows)

        await self._session.restructure(work, refusals=WRITING)
        return RelationCreated(node=await self._describe(request.name), inserted=len(rows))

    async def _describe(self, name: str) -> CatalogNode:
        return (await self._catalog.path_to(ids.relation_id(name)))[-1]
