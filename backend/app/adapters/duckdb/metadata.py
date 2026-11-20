"""What an editor may complete to, and statements about a node (D65).

Every schema of the file and its relations; a relation's columns when the
editor names it, as `schema.relation` or as a name found along the search
path, `main` when none is given.
"""

from app.adapters import database_ids as ids
from app.adapters.duckdb.inspection import find_relation, list_relations, list_schemas
from app.adapters.duckdb.session import DuckdbSession, Reading
from app.adapters.duckdb.sql import SQL, Identifier
from app.adapters.duckdb.statements import DEFAULT_SCHEMA
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

_COLUMNS = """
SELECT column_name, data_type FROM duckdb_columns()
WHERE database_name = current_database() AND schema_name = ? AND table_name = ?
ORDER BY column_index LIMIT ?
"""


def _resolved(
    asked: str, known: set[tuple[str, str]], search_path: list[str]
) -> tuple[str, str] | None:
    """The relation a name means: qualified as written, or the first along the path."""
    schema, dot, name = asked.partition(".")
    if dot and (schema, name) in known:
        return schema, name
    for place in [*search_path, DEFAULT_SCHEMA]:
        if (place, asked) in known:
            return place, asked
    return None


class DuckdbMetadata:
    def __init__(self, session: DuckdbSession) -> None:
        self._session = session

    async def metadata(self, request: QueryMetadataRequest) -> QueryMetadata:
        def read(reading: Reading) -> QueryMetadata:
            rows = list_relations(reading)
            relations = [
                RelationSummary(
                    schema_name=str(row["schema_name"]),
                    name=str(row["name"]),
                    kind="view" if row["type"] == "view" else "table",
                )
                for row in rows[:MAX_RELATIONS]
            ]
            known = {(str(row["schema_name"]), str(row["name"])) for row in rows}
            columns: dict[str, list[ColumnSummary]] = {}
            budget = MAX_COLUMNS
            for asked in request.relations:
                found = _resolved(asked, known, request.search_path)
                if found is None or budget <= 0:
                    continue
                listed = reading.rows(_COLUMNS, [found[0], found[1], budget])
                budget -= len(listed)
                columns[asked] = [
                    ColumnSummary(name=str(row["column_name"]), type_sql=str(row["data_type"]))
                    for row in listed
                ]
            return QueryMetadata(
                schemas=list_schemas(reading),
                relations=relations,
                columns=columns,
                complete=len(rows) <= MAX_RELATIONS,
            )

        return await self._session.inspection(read)


class DuckdbGeneration:
    """Statements the source writes about its own nodes, quoted by its dialect."""

    def __init__(self, session: DuckdbSession) -> None:
        self._session = session

    async def generate(self, request: GenerateQueryRequest) -> GeneratedQuery:
        schema, relation = ids.parse(request.node_id)
        refused = say('"{node_id}" is not a relation of this source', node_id=request.node_id)
        if not relation:
            raise ValueError(refused)

        def read(reading: Reading) -> list[str] | None:
            if find_relation(reading, schema, relation) is None:
                return None
            return [
                str(row["column_name"])
                for row in reading.rows(_COLUMNS, [schema, relation, MAX_COLUMNS])
            ]

        names = await self._session.inspection(read)
        if not names:
            raise ValueError(refused)
        qualified = Identifier(schema, relation)
        listed = SQL(", ").join(Identifier(name) for name in names)
        if request.kind == "name":
            return GeneratedQuery(text=qualified.readable())
        if request.kind == "columns":
            return GeneratedQuery(text=listed.readable())
        statement = SQL("SELECT {}" + LINE + "FROM {}" + LINE + f"LIMIT {GENERATED_LIMIT}").format(
            listed, qualified
        )
        return GeneratedQuery(text=statement.readable())
