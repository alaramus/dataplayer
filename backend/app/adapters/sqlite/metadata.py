"""What an editor may complete to, and statements about a node (D65).

One schema, `main` (D248): its relations, and a relation's columns when the
editor names it, as `main.table` or as `table`.
"""

from app.adapters.query import (
    ColumnSummary,
    GeneratedQuery,
    GenerateQueryRequest,
    QueryMetadata,
    QueryMetadataRequest,
    RelationSummary,
)
from app.adapters.sqlite import ids
from app.adapters.sqlite.inspection import SCHEMA, find_relation, list_relations
from app.adapters.sqlite.session import Reading, SqliteSession
from app.adapters.sqlite.sql import SQL, Identifier
from app.core.translation import say

MAX_RELATIONS = 2000
MAX_COLUMNS = 5000
GENERATED_LIMIT = 100
LINE = chr(10)

_COLUMNS = """
SELECT name, type FROM pragma_table_xinfo(?, 'main') WHERE hidden <> 1 ORDER BY cid LIMIT ?
"""

_KINDS = {"table": "table", "view": "view"}


def _unqualified(name: str) -> str:
    """`main.items` and `items` name the same relation."""
    prefix = SCHEMA + "."
    return name[len(prefix) :] if name.startswith(prefix) else name


class SqliteMetadata:
    def __init__(self, session: SqliteSession) -> None:
        self._session = session

    async def metadata(self, request: QueryMetadataRequest) -> QueryMetadata:
        def read(reading: Reading) -> QueryMetadata:
            rows = list_relations(reading)
            relations = [
                RelationSummary(
                    schema_name=SCHEMA,
                    name=str(row["name"]),
                    kind=_KINDS.get(str(row["type"]), "other"),  # type: ignore[arg-type]  # the table holds the union's members
                )
                for row in rows[:MAX_RELATIONS]
            ]
            known = {str(row["name"]) for row in rows}
            columns: dict[str, list[ColumnSummary]] = {}
            budget = MAX_COLUMNS
            for asked in request.relations:
                name = _unqualified(asked)
                if name not in known or budget <= 0:
                    continue
                found = reading.rows(_COLUMNS, (name, budget))
                budget -= len(found)
                columns[asked] = [
                    ColumnSummary(name=str(row["name"]), type_sql=str(row["type"] or ""))
                    for row in found
                ]
            return QueryMetadata(
                schemas=[SCHEMA],
                relations=relations,
                columns=columns,
                complete=len(rows) <= MAX_RELATIONS,
            )

        return await self._session.inspection(read)


class SqliteGeneration:
    """Statements the source writes about its own nodes, quoted by its dialect."""

    def __init__(self, session: SqliteSession) -> None:
        self._session = session

    async def generate(self, request: GenerateQueryRequest) -> GeneratedQuery:
        schema, relation = ids.parse(request.node_id)
        refused = say('"{node_id}" is not a relation of this source', node_id=request.node_id)
        if schema != SCHEMA or not relation:
            raise ValueError(refused)

        def read(reading: Reading) -> list[str] | None:
            if find_relation(reading, relation) is None:
                return None
            return [str(row["name"]) for row in reading.rows(_COLUMNS, (relation, MAX_COLUMNS))]

        names = await self._session.inspection(read)
        if not names:
            raise ValueError(refused)
        qualified = Identifier(SCHEMA, relation)
        listed = SQL(", ").join(Identifier(name) for name in names)
        if request.kind == "name":
            return GeneratedQuery(text=qualified.readable())
        if request.kind == "columns":
            return GeneratedQuery(text=listed.readable())
        statement = SQL("SELECT {}" + LINE + "FROM {}" + LINE + f"LIMIT {GENERATED_LIMIT}").format(
            listed, qualified
        )
        return GeneratedQuery(text=statement.readable())
