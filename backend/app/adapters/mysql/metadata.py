"""What an editor may complete to, asked of the server progressively (D65).

A MySQL database is a schema (D229), so the schemas are the databases, the
relations are those of the database a document works in, and a relation's
columns are read when the editor names it as `database.table`.
"""

from app.adapters.mysql import ids
from app.adapters.mysql.session import MysqlSession
from app.adapters.mysql.sql import SQL, Identifier
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

# The server's catalog databases are read by people writing SQL, as
# `pg_catalog` is, and so are listed; nothing is hidden.
_SCHEMAS = """
SELECT SCHEMA_NAME AS name
FROM information_schema.SCHEMATA
ORDER BY SCHEMA_NAME
LIMIT %s
"""

_RELATIONS = """
SELECT TABLE_SCHEMA AS schema_name, TABLE_NAME AS name, TABLE_TYPE AS table_type
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = %s
ORDER BY TABLE_NAME
LIMIT %s
"""

_COLUMNS = """
SELECT COLUMN_NAME AS name, COLUMN_TYPE AS type_sql
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
ORDER BY ORDINAL_POSITION
LIMIT %s
"""


def _split(qualified: str, schemas: set[str]) -> tuple[str, str] | None:
    """`database.table` as an editor writes it, or nothing when it is not one.

    A database's name may hold a dot (D229), so every dot is tried and the
    database is the part the server knows.
    """
    for index, character in enumerate(qualified):
        if character == "." and qualified[:index] in schemas and qualified[index + 1 :]:
            return qualified[:index], qualified[index + 1 :]
    return None


class MysqlMetadata:
    def __init__(self, session: MysqlSession) -> None:
        self._session = session

    async def metadata(self, request: QueryMetadataRequest) -> QueryMetadata:
        schemas = [
            str(row["name"])
            for row in await self._session.query(_SCHEMAS, (MAX_SCHEMAS,))
        ]
        known = set(schemas)
        asked = [name for name in request.search_path if name in known]
        # One default database, so the first asked for, or the connection's own.
        current = asked[:1] or [
            name for name in [self._session.database()] if name and name in known
        ]
        relations: list[RelationSummary] = []
        complete = True
        for schema in current:
            rows = await self._session.query(_RELATIONS, (schema, MAX_RELATIONS + 1))
            complete = len(rows) <= MAX_RELATIONS
            relations += [
                RelationSummary(
                    schema_name=str(row["schema_name"]),
                    name=str(row["name"]),
                    kind="view" if "VIEW" in str(row["table_type"]) else "table",
                )
                for row in rows[:MAX_RELATIONS]
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
            rows = await self._session.query(_COLUMNS, (*pair, budget))
            budget -= len(rows)
            if rows:
                found[qualified] = [
                    ColumnSummary(name=str(row["name"]), type_sql=str(row["type_sql"]))
                    for row in rows
                ]
        return found


class MysqlGeneration:
    """Statements the source writes about its own nodes, quoted by its dialect."""

    def __init__(self, session: MysqlSession, metadata: MysqlMetadata) -> None:
        self._session = session
        self._metadata = metadata

    async def generate(self, request: GenerateQueryRequest) -> GeneratedQuery:
        schema, relation = ids.parse(request.node_id)
        refused = say('"{node_id}" is not a relation of this source', node_id=request.node_id)
        if relation is None:
            raise ValueError(refused)
        rows = await self._session.query(_COLUMNS, (schema, relation, MAX_COLUMNS))
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
