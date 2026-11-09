"""Changing a Cassandra table's columns and secondary indexes (D346).

What CQL's `ALTER TABLE` does, and nothing it does not: a column is added or
dropped, a column of the primary key renamed, and a secondary index made on
one column or dropped. A refusal the server gives — a column an index or a
view reads — is passed on in its own words.
"""

from app.adapters.cassandra.cql import SQL, Identifier
from app.adapters.cassandra.inspection import ColumnFacts, Inspector, RelationFacts
from app.adapters.cassandra.relation import CassandraRelation, structure_reason
from app.adapters.cassandra.session import CassandraSession
from app.adapters.cassandra.vocabulary import COLUMN_TYPES, index_methods
from app.adapters.column_changes import (
    AddColumnRequest,
    ColumnChangeResult,
    DropColumnRequest,
    RenameColumnRequest,
)
from app.adapters.indexes import (
    CreateIndexRequest,
    CreateIndexResult,
    DropIndexRequest,
    IndexCreated,
    IndexDropped,
)
from app.core.translation import say

_INDEX_NAMES = "SELECT index_name FROM system_schema.indexes WHERE keyspace_name = ?"
# CQL's limit on a name, which an index's name made up here keeps to.
_NAME_LIMIT = 48


class CassandraStructure:
    def __init__(
        self,
        session: CassandraSession,
        relation: CassandraRelation,
        inspector: Inspector,
    ) -> None:
        self._session = session
        self._relation = relation
        self._inspector = inspector

    async def _changeable(self, node_id: str) -> RelationFacts:
        facts = await self._relation.facts(node_id)
        refused = structure_reason(facts)
        if refused is not None:
            raise ValueError(refused)
        return facts

    @staticmethod
    def _column(facts: RelationFacts, name: str) -> ColumnFacts:
        found = next((column for column in facts.columns if column.name == name), None)
        if found is None:
            raise ValueError(say('Relation has no column "{column}"', column=name))
        return found

    async def _alter(
        self, facts: RelationFacts, change: SQL, *parts: Identifier
    ) -> None:
        statement = SQL("ALTER TABLE {} ").format(
            Identifier(facts.keyspace, facts.name)
        )
        await self._session.page(
            (statement + change.format(*parts)).text(), wait_seconds=60
        )

    async def add_column(self, request: AddColumnRequest) -> ColumnChangeResult:
        facts = await self._changeable(request.node_id)
        option = COLUMN_TYPES.get(request.type_code)
        if option is None:
            raise ValueError(say("Unknown column type: {code}", code=request.type_code))
        if not request.nullable:
            raise ValueError(say("Only a column of the primary key always has a value"))
        if any(column.name == request.name for column in facts.columns):
            raise ValueError(
                say('Column "{column}" already exists', column=request.name)
            )
        await self._alter(facts, SQL("ADD {} " + option.sql), Identifier(request.name))
        return ColumnChangeResult(name=request.name)

    async def drop_column(self, request: DropColumnRequest) -> ColumnChangeResult:
        facts = await self._changeable(request.node_id)
        column = self._column(facts, request.name)
        if column.in_key:
            raise ValueError(say("A column of the primary key cannot be dropped"))
        await self._alter(facts, SQL("DROP {}"), Identifier(column.name))
        return ColumnChangeResult(name=column.name)

    async def rename_column(self, request: RenameColumnRequest) -> ColumnChangeResult:
        facts = await self._changeable(request.node_id)
        column = self._column(facts, request.name)
        if not column.in_key:
            raise ValueError(say("Cassandra renames only a column of the primary key"))
        await self._alter(
            facts,
            SQL("RENAME {} TO {}"),
            Identifier(column.name),
            Identifier(request.new_name),
        )
        return ColumnChangeResult(name=request.new_name)

    async def _free_index_name(self, facts: RelationFacts, column: str) -> str:
        taken = {
            str(row["index_name"])
            for row in await self._session.query(_INDEX_NAMES, [facts.keyspace])
        }
        stem = "".join(
            char if char.isalnum() or char == "_" else "_"
            for char in f"{facts.name}_{column}"
        )
        stem = stem[: _NAME_LIMIT - 8].strip("_") or "index"
        name = f"{stem}_idx"
        number = 2
        while name in taken:
            name = f"{stem}_idx{number}"
            number += 1
        return name

    async def create_index(self, request: CreateIndexRequest) -> CreateIndexResult:
        facts = await self._changeable(request.node_id)
        if request.unique:
            raise ValueError(say("A Cassandra index cannot be unique"))
        if len(request.columns) != 1:
            raise ValueError(say("A Cassandra index covers one column"))
        column = self._column(facts, request.columns[0])
        profile = await self._inspector.profile()
        method = next(
            (
                option
                for option in index_methods(profile.scylla, profile.version)
                if option.code == request.method
            ),
            None,
        )
        if method is None:
            raise ValueError(
                say("Unknown index method: {method}", method=request.method)
            )
        name = await self._free_index_name(facts, column.name)
        statement = SQL("CREATE INDEX {} ON {} ({})").format(
            Identifier(name),
            Identifier(facts.keyspace, facts.name),
            Identifier(column.name),
        )
        if method.sql:
            statement += SQL(" USING '" + method.sql + "'")
        await self._session.page(statement.text(), wait_seconds=120)
        return IndexCreated(name=name)

    async def drop_index(self, request: DropIndexRequest) -> IndexDropped:
        facts = await self._changeable(request.node_id)
        if not any(index.name == request.name for index in facts.indexes):
            raise ValueError(say('Relation has no index "{name}"', name=request.name))
        await self._session.page(
            SQL("DROP INDEX {}")
            .format(Identifier(facts.keyspace, request.name))
            .text(),
            wait_seconds=60,
        )
        return IndexDropped(name=request.name)
