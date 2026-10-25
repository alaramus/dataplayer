"""What an editor may complete to, asked of the server progressively (D65).

A ClickHouse database is a schema (D267), so the schemas are the databases,
the relations are those of the database a document works in, and a
relation's columns are read when the editor names it as `database.table`.
"""

from typing import Literal

from app.adapters.clickhouse.catalog import is_inner_table
from app.adapters.clickhouse.session import ClickhouseSession
from app.adapters.clickhouse.sql import SQL, Identifier
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

MAX_SCHEMAS = 200
MAX_RELATIONS = 2000
MAX_COLUMNS = 5000
GENERATED_LIMIT = 100
LINE = chr(10)

# The server's own databases are read by people writing SQL — system.parts,
# system.query_log — and so are listed; nothing is hidden.
_SCHEMAS = "SELECT name FROM system.databases ORDER BY name LIMIT {limit:UInt32}"

_RELATIONS = """
SELECT database, name, engine
FROM system.tables
WHERE database = {database:String} AND NOT is_temporary
ORDER BY name
LIMIT {limit:UInt32}
"""

_COLUMNS = """
SELECT name, type
FROM system.columns
WHERE database = {database:String} AND table = {table:String}
ORDER BY position
LIMIT {limit:UInt32}
"""


def _split(qualified: str, schemas: set[str]) -> tuple[str, str] | None:
    """`database.table` as an editor writes it; a database may hold a dot."""
    for index, character in enumerate(qualified):
        if character == "." and qualified[:index] in schemas and qualified[index + 1 :]:
            return qualified[:index], qualified[index + 1 :]
    return None


def _kind(engine: str) -> Literal["table", "view", "materialized_view"]:
    if engine == "MaterializedView":
        return "materialized_view"
    return "view" if engine in ("View", "LiveView", "WindowView") else "table"


class ClickhouseMetadata:
    def __init__(self, session: ClickhouseSession) -> None:
        self._session = session

    async def metadata(self, request: QueryMetadataRequest) -> QueryMetadata:
        schemas = [
            str(row["name"])
            for row in await self._session.query(_SCHEMAS, {"limit": str(MAX_SCHEMAS)})
        ]
        known = set(schemas)
        asked = [name for name in request.search_path if name in known]
        # One default database: the first asked for, or the connection's own.
        own = self._session.database() or "default"
        current = asked[:1] or [name for name in [own] if name in known]
        relations: list[RelationSummary] = []
        complete = True
        for schema in current:
            rows = await self._session.query(
                _RELATIONS, {"database": schema, "limit": str(MAX_RELATIONS + 1)}
            )
            complete = len(rows) <= MAX_RELATIONS
            relations += [
                RelationSummary(
                    schema_name=str(row["database"]),
                    name=str(row["name"]),
                    kind=_kind(str(row["engine"])),
                )
                for row in rows[:MAX_RELATIONS]
                if not is_inner_table(str(row["name"]))
            ]
        return QueryMetadata(
            schemas=schemas,
            relations=relations,
            columns=await self._columns(request.relations, known),
            complete=complete,
        )

    async def _columns(
        self, relations: list[str], schemas: set[str]
    ) -> dict[str, list[ColumnSummary]]:
        found: dict[str, list[ColumnSummary]] = {}
        budget = MAX_COLUMNS
        for qualified in relations:
            pair = _split(qualified, schemas)
            if pair is None or budget <= 0:
                continue
            rows = await self._session.query(
                _COLUMNS, {"database": pair[0], "table": pair[1], "limit": str(budget)}
            )
            budget -= len(rows)
            if rows:
                found[qualified] = [
                    ColumnSummary(name=str(row["name"]), type_sql=str(row["type"]))
                    for row in rows
                ]
        return found


class ClickhouseGeneration:
    """Statements the source writes about its own nodes, quoted by its dialect."""

    def __init__(self, session: ClickhouseSession) -> None:
        self._session = session

    async def generate(self, request: GenerateQueryRequest) -> GeneratedQuery:
        schema, relation = parse(request.node_id)
        refused = say('"{node_id}" is not a relation of this source', node_id=request.node_id)
        if relation is None:
            raise ValueError(refused)
        rows = await self._session.query(
            _COLUMNS, {"database": schema, "table": relation, "limit": str(MAX_COLUMNS)}
        )
        if not rows:
            raise ValueError(refused)
        qualified = Identifier(schema, relation)
        names = SQL(", ").join(Identifier(str(row["name"])) for row in rows)
        if request.kind == "name":
            return GeneratedQuery(text=qualified.readable())
        if request.kind == "columns":
            return GeneratedQuery(text=names.readable())
        statement = SQL("SELECT {}" + LINE + "FROM {}" + LINE + f"LIMIT {GENERATED_LIMIT}").format(
            names, qualified
        )
        return GeneratedQuery(text=statement.readable())
