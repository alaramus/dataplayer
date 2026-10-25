"""Creating a ClickHouse table with the rows it starts with (D45, D274).

PostgreSQL makes the table and puts its rows in one transaction; ClickHouse
has none, so the promise MySQL keeps without one is kept the same way: every
value is tried as its column's type before anything is made, and if the rows
are still refused once the table exists, the table this request made is
dropped again. The table is a MergeTree with no sorting key: rows from a page
have no order of their own to keep.
"""

from app.adapters.catalog import CatalogNode, SchemaNode
from app.adapters.clickhouse.catalog import ClickhouseCatalog
from app.adapters.clickhouse.columns import ALTERING, nullable_form
from app.adapters.clickhouse.session import ClickhouseSession
from app.adapters.clickhouse.sql import SQL, Identifier
from app.adapters.clickhouse.types import build_column_type
from app.adapters.clickhouse.update import ClickhouseUpdate, insert_json
from app.adapters.clickhouse.vocabulary import (
    CLICKHOUSE_COLUMN_TYPE_OPTIONS,
    COLUMN_TYPES,
)
from app.adapters.database_ids import parse, relation_id
from app.adapters.fetch import FetchColumn
from app.adapters.relation_changes import (
    CreateRelationRequest,
    CreateRelationResult,
    NewRelationOptions,
    RelationCreated,
)
from app.adapters.update import RejectedValue, ValuesRejected
from app.adapters.words import worded_titles
from app.core.translation import N_, say

CREATE_REFUSALS: dict[int, str] = {
    57: N_("Something with that name is already there"),
    15: N_("Two columns cannot have the same name"),
    497: N_("This connection may not create a table in that database"),
}


class ClickhouseRelationChanges:
    def __init__(
        self, session: ClickhouseSession, catalog: ClickhouseCatalog, update: ClickhouseUpdate
    ) -> None:
        self._session = session
        self._catalog = catalog
        self._update = update

    async def new_relation_options(self, parent_node_id: str) -> NewRelationOptions:
        node = (await self._catalog.path_to(parent_node_id))[-1]
        if not isinstance(node, SchemaNode):
            return NewRelationOptions(supported=False, reason=say("A table is created in a database"))
        if node.is_system:
            return NewRelationOptions(
                supported=False, reason=say('"{schema}" belongs to the server', schema=node.name)
            )
        return NewRelationOptions(
            supported=True, column_type_options=worded_titles(CLICKHOUSE_COLUMN_TYPE_OPTIONS)
        )

    async def create_relation(self, request: CreateRelationRequest) -> CreateRelationResult:
        options = await self.new_relation_options(request.parent_node_id)
        if not options.supported:
            raise ValueError(options.reason or say("This node cannot hold a relation"))
        schema, _ = parse(request.parent_node_id)
        columns: list[FetchColumn] = []
        for asked in request.columns:
            option = COLUMN_TYPES.get(asked.type_code)
            if option is None:
                raise ValueError(say('Unknown column type "{code}"', code=asked.type_code))
            # A cell of a page may be empty, so every column may hold NULL.
            columns.append(FetchColumn(name=asked.name, type=build_column_type(nullable_form(option.sql))))
        checked: list[tuple[str | None, FetchColumn]] = []
        places: list[tuple[int, str, str | None]] = []
        for index, row in enumerate(request.rows):
            for column, value in zip(columns, row, strict=True):
                checked.append((value, column))
                places.append((index, column.name, value))
        rejected = await self._update.unreadable(checked)
        if rejected:
            return ValuesRejected(
                cells=[
                    RejectedValue(row=row, column=column, value=None if value is None else value[:100])
                    for row, column, value in (places[at] for at in rejected[:200])
                ]
            )
        table = Identifier(schema, request.name)
        # Each type is the vocabulary's own text.
        create = (
            SQL("CREATE TABLE {} (").format(table)
            + SQL(", ").join(
                SQL("{} ").format(Identifier(column.name)) + SQL(column.type.sql) for column in columns
            )
            + SQL(") ENGINE = MergeTree ORDER BY tuple()")
        )
        await self._session.command(create.text(), {}, settings=ALTERING, refusals=CREATE_REFUSALS)
        try:
            if request.rows:
                await insert_json(self._session, schema, request.name, columns, request.rows)
        except BaseException:
            # The name was free a moment ago and this request made the table,
            # so the table dropped is this request's own.
            await self._session.command(
                SQL("DROP TABLE IF EXISTS {}").format(table).text(), {}, settings=ALTERING
            )
            raise
        return RelationCreated(node=await self._describe(schema, request.name), inserted=len(request.rows))

    async def _describe(self, schema: str, name: str) -> CatalogNode:
        return (await self._catalog.path_to(relation_id(schema, name)))[-1]
