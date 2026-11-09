"""What an editor may complete to, asked of the server progressively (D65, D343).

A keyspace is a schema (D341): the schemas are the keyspaces, the relations are
those of the keyspace a document works in, and a relation's columns are read
when the editor names it as `keyspace.table`. A keyspace's name has no dot,
so the first dot divides.
"""

from app.adapters.cassandra.cql import SQL, Identifier
from app.adapters.cassandra.inspection import Inspector
from app.adapters.cassandra.session import CassandraSession
from app.adapters.database_ids import parse
from app.adapters.query import (
    ColumnSummary,
    GeneratedQuery,
    GenerateQueryRequest,
    QueryMetadata,
    QueryMetadataRequest,
    RelationSummary,
)
from app.core.translation import say

MAX_RELATIONS = 2000
MAX_COLUMNS = 5000
GENERATED_LIMIT = 100
LINE = chr(10)


class CassandraMetadata:
    def __init__(self, session: CassandraSession, inspector: Inspector) -> None:
        self._session = session
        self._inspector = inspector

    async def metadata(self, request: QueryMetadataRequest) -> QueryMetadata:
        places = dict(await self._inspector.keyspaces())
        asked = [name for name in request.search_path if name in places]
        own = self._session.keyspace()
        # One keyspace at a time: the first asked for, or the connection's own.
        current = asked[:1] or [name for name in [own] if name in places]
        relations: list[RelationSummary] = []
        complete = True
        for keyspace in current:
            found = await self._inspector.relations(
                keyspace, places[keyspace], structure=False
            )
            complete = len(found) <= MAX_RELATIONS
            relations += [
                RelationSummary(
                    schema_name=keyspace,
                    name=name,
                    kind="materialized_view" if facts.is_view else "table",
                )
                for name, facts in sorted(found.items())[:MAX_RELATIONS]
            ]
        return QueryMetadata(
            schemas=sorted(places),
            relations=relations,
            columns=await self._columns(request.relations, places),
            complete=complete,
        )

    async def _columns(
        self, relations: list[str], places: dict[str, bool]
    ) -> dict[str, list[ColumnSummary]]:
        found: dict[str, list[ColumnSummary]] = {}
        budget = MAX_COLUMNS
        for qualified in relations:
            keyspace, _, name = qualified.partition(".")
            if not name or keyspace not in places or budget <= 0:
                continue
            facts = (
                await self._inspector.relations(
                    keyspace, places[keyspace], names=[name]
                )
            ).get(name)
            if facts is None:
                continue
            columns = facts.columns[:budget]
            budget -= len(columns)
            found[qualified] = [
                ColumnSummary(name=column.name, type_sql=column.type_text)
                for column in columns
            ]
        return found


class CassandraGeneration:
    """Statements the source writes about its own nodes, quoted by CQL."""

    def __init__(self, inspector: Inspector) -> None:
        self._inspector = inspector

    async def generate(self, request: GenerateQueryRequest) -> GeneratedQuery:
        keyspace, relation = parse(request.node_id)
        refused = say(
            '"{node_id}" is not a relation of this source', node_id=request.node_id
        )
        if relation is None:
            raise ValueError(refused)
        facts = await self._inspector.relation(keyspace, relation)
        if facts is None:
            raise ValueError(refused)
        qualified = Identifier(keyspace, relation)
        names = SQL(", ").join(Identifier(column.name) for column in facts.columns)
        if request.kind == "name":
            return GeneratedQuery(text=qualified.readable())
        if request.kind == "columns":
            return GeneratedQuery(text=names.readable())
        statement = SQL(
            "SELECT {}" + LINE + "FROM {}" + LINE + f"LIMIT {GENERATED_LIMIT}"
        ).format(names, qualified)
        return GeneratedQuery(text=statement.readable())
