"""Creating a MySQL table with the rows it starts with (D45, D236).

PostgreSQL makes the table and puts its rows in one transaction. MySQL commits
`CREATE TABLE` by itself (D233), so the same promise — a table that cannot take
its rows is not left behind — is kept differently: every value is checked
against the chosen types before anything is made, and if the rows are still
refused once the table exists, the table this request made is dropped again.
"""

from app.adapters.catalog import CatalogNode, SchemaNode
from app.adapters.fetch import FetchColumn
from app.adapters.mysql import ids
from app.adapters.mysql.catalog import MysqlCatalog
from app.adapters.mysql.session import MysqlSession
from app.adapters.mysql.sql import SQL, Identifier
from app.adapters.mysql.update import REFUSALS, unreadable
from app.adapters.mysql.vocabulary import COLUMN_TYPES, MYSQL_COLUMN_TYPE_OPTIONS
from app.adapters.relation import ColumnType, TypeCategory
from app.adapters.relation_changes import (
    CreateRelationRequest,
    CreateRelationResult,
    NewRelationOptions,
    RelationCreated,
)
from app.adapters.update import RejectedValue, ValuesRejected
from app.adapters.words import worded_titles
from app.core.translation import N_, say

NAME_LIMIT = 64

CREATE_REFUSALS: dict[int, str] = {
    **REFUSALS,
    1050: N_("Something with that name is already there"),
    1060: N_("Two columns cannot have the same name"),
    1142: N_("This connection may not create a table in that database"),
    1044: N_("This connection may not create a table in that database"),
}

_CATEGORIES: dict[str, TypeCategory] = {
    "text": "string",
    "long_text": "string",
    "uuid": "string",
    "integer": "number",
    "bigint": "number",
    "decimal": "number",
    "double": "number",
    "boolean": "number",
    "date": "datetime",
    "datetime": "datetime",
    "timestamp": "datetime",
    "json": "json",
}


class MysqlRelationChanges:
    def __init__(self, session: MysqlSession, catalog: MysqlCatalog) -> None:
        self._session = session
        self._catalog = catalog

    async def new_relation_options(self, parent_node_id: str) -> NewRelationOptions:
        node = (await self._catalog.path_to(parent_node_id))[-1]
        if not isinstance(node, SchemaNode):
            return NewRelationOptions(supported=False, reason=say("A table is created in a database"))
        if node.is_system:
            return NewRelationOptions(
                supported=False, reason=say('"{schema}" belongs to the server', schema=node.name)
            )
        return NewRelationOptions(
            supported=True,
            column_type_options=worded_titles(MYSQL_COLUMN_TYPE_OPTIONS),
            text_type="long_text",
        )

    async def create_relation(self, request: CreateRelationRequest) -> CreateRelationResult:
        options = await self.new_relation_options(request.parent_node_id)
        if not options.supported:
            raise ValueError(options.reason or say("This node cannot hold a relation"))
        schema, _ = ids.parse(request.parent_node_id)
        names = [request.name] + [column.name for column in request.columns]
        if any(len(name) > NAME_LIMIT for name in names):
            raise ValueError(say("A MySQL name cannot exceed {limit} characters", limit=NAME_LIMIT))
        if len({column.name.lower() for column in request.columns}) != len(request.columns):
            # MySQL compares column names without case.
            raise ValueError(say("A column may be named only once"))
        columns: list[FetchColumn] = []
        for asked in request.columns:
            option = COLUMN_TYPES.get(asked.type_code)
            if option is None:
                raise ValueError(say('Unknown column type "{code}"', code=asked.type_code))
            columns.append(
                FetchColumn(
                    name=asked.name,
                    type=ColumnType(sql=option.sql, category=_CATEGORIES.get(option.code, "other")),
                )
            )
        table = Identifier(schema, request.name)
        create = SQL("CREATE TABLE {} ({})").format(
            table,
            SQL(", ").join(
                SQL("{} " + column.type.sql).format(Identifier(column.name)) for column in columns
            ),
        )
        insert = SQL("INSERT INTO {} ({}) VALUES ({})").format(
            table,
            SQL(", ").join(Identifier(column.name) for column in columns),
            SQL(", ").join(SQL("%s") for _ in columns),
        )

        async with self._session.writing(refusals=CREATE_REFUSALS) as work:
            checked: list[tuple[str, FetchColumn]] = []
            places: list[tuple[int, str, str]] = []
            for index, row in enumerate(request.rows):
                for column, value in zip(columns, row, strict=True):
                    if value is not None:
                        checked.append((value, column))
                        places.append((index, column.name, value))
            rejected = await unreadable(work, schema, checked)
        if rejected:
            return ValuesRejected(
                cells=[
                    RejectedValue(row=places[at][0], column=places[at][1], value=places[at][2][:100])
                    for at in rejected[:200]
                ]
            )

        async with self._session.altering(refusals=CREATE_REFUSALS) as work:
            await work.execute(create.text())
        try:
            if request.rows:
                async with self._session.writing(refusals=CREATE_REFUSALS) as work:
                    await work.execute_many(insert.text(), [tuple(row) for row in request.rows])
        except BaseException:
            # The name was free a moment ago and this request made the table,
            # so the table dropped is this request's own.
            async with self._session.altering() as work:
                await work.execute(SQL("DROP TABLE IF EXISTS {}").format(table).text())
            raise
        return RelationCreated(
            node=await self._describe(schema, request.name), inserted=len(request.rows)
        )

    async def _describe(self, schema: str, name: str) -> CatalogNode:
        return (await self._catalog.path_to(ids.relation_id(schema, name)))[-1]
