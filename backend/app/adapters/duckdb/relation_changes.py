"""Creating a DuckDB table with the rows it starts with (D45, D397).

The table and its rows in one transaction, as on PostgreSQL: DuckDB's
structure changes are transactional (D393), so a table whose rows are refused
is never left behind. A value is bound as text and DuckDB converts it by the
column's type (D395).
"""

import duckdb

from app.adapters import database_ids as ids
from app.adapters.catalog import CatalogNode, SchemaNode
from app.adapters.duckdb.catalog import DuckdbCatalog
from app.adapters.duckdb.rows import written
from app.adapters.duckdb.session import DuckdbSession
from app.adapters.duckdb.sql import SQL, Identifier
from app.adapters.duckdb.structure import restructure
from app.adapters.duckdb.types import build_column_type
from app.adapters.duckdb.vocabulary import COLUMN_TYPE_OPTIONS, column_type
from app.adapters.relation_changes import (
    CreateRelationRequest,
    CreateRelationResult,
    NewRelationOptions,
    RelationCreated,
)
from app.adapters.words import worded_titles
from app.core.translation import say


class DuckdbRelationChanges:
    def __init__(self, session: DuckdbSession, catalog: DuckdbCatalog) -> None:
        self._session = session
        self._catalog = catalog

    async def _schema(self, node_id: str) -> SchemaNode | None:
        node = (await self._catalog.path_to(node_id))[-1]
        return node if isinstance(node, SchemaNode) else None

    async def new_relation_options(self, parent_node_id: str) -> NewRelationOptions:
        if await self._schema(parent_node_id) is None:
            return NewRelationOptions(supported=False, reason=say("A table is created in a schema"))
        return NewRelationOptions(
            supported=True,
            column_type_options=worded_titles(COLUMN_TYPE_OPTIONS),
            text_type="text",
        )

    async def create_relation(self, request: CreateRelationRequest) -> CreateRelationResult:
        schema = await self._schema(request.parent_node_id)
        if schema is None:
            raise ValueError(say("A table is created in a schema"))
        if len({column.name.lower() for column in request.columns}) != len(request.columns):
            # DuckDB compares column names without case.
            raise ValueError(say("A column may be named only once"))
        types = []
        for asked in request.columns:
            option = column_type(asked.type_code)
            if option is None:
                raise ValueError(say('Unknown column type "{code}"', code=asked.type_code))
            types.append(build_column_type(option.sql))
        table = Identifier(schema.name, request.name)
        create = SQL("CREATE TABLE {} ({})").format(
            table,
            SQL(", ").join(
                # A type of the vocabulary, written by this package.
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
            [written(value, type_) for value, type_ in zip(row, types, strict=True)]
            for row in request.rows
        ]

        def work(connection: duckdb.DuckDBPyConnection) -> None:
            connection.execute(create.text())
            for row in rows:
                connection.execute(insert.text(), row)

        await restructure(self._session, work)
        return RelationCreated(node=await self._describe(schema.name, request.name), inserted=len(rows))

    async def _describe(self, schema: str, name: str) -> CatalogNode:
        return (await self._catalog.path_to(ids.relation_id(schema, name)))[-1]
