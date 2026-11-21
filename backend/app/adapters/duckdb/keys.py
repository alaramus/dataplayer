"""Indexes and constraints of a DuckDB table made and dropped (D39, D40, D396).

An index is DuckDB's own CREATE and DROP INDEX; a unique key is added in place.
What the rows already contradict is counted first and answered as a count.
DuckDB cannot add a foreign key or drop any constraint of an existing table,
and a rebuild would fail for the tables that keys and views depend on, so
those are refused with the reason.
"""

import duckdb

from app.adapters.constraints import (
    ConstraintCreated,
    ConstraintDropped,
    CreateConstraintRequest,
    CreateConstraintResult,
    DropConstraintRequest,
    ForeignKeySpec,
    RepeatingValues,
)
from app.adapters.duckdb.inspection import RelationFacts
from app.adapters.duckdb.relation import DuckdbRelation
from app.adapters.duckdb.session import DuckdbSession
from app.adapters.duckdb.sql import SQL, Composable, Identifier
from app.adapters.duckdb.structure import (
    bounded_count,
    restructure,
    structure_reason,
    table_of,
)
from app.adapters.indexes import (
    CreateIndexRequest,
    CreateIndexResult,
    DropIndexRequest,
    IndexBlocked,
    IndexCreated,
    IndexDropped,
)
from app.core.translation import say

# Long enough to read, short enough to stay a name.
_NAME_LIMIT = 60

TAKEN = """
SELECT lower(name) FROM (
  SELECT index_name AS name FROM duckdb_indexes()
  WHERE database_name = current_database() AND schema_name = ?
  UNION ALL
  SELECT table_name FROM duckdb_tables()
  WHERE database_name = current_database() AND schema_name = ?
  UNION ALL
  SELECT view_name FROM duckdb_views()
  WHERE database_name = current_database() AND schema_name = ?
  UNION ALL
  SELECT sequence_name FROM duckdb_sequences()
  WHERE database_name = current_database() AND schema_name = ?
)
"""


def derived(table: str, columns: list[str], suffix: str) -> str:
    """A name in PostgreSQL's pattern: table, columns, then what it is."""
    stem = "_".join([table, *columns])[: _NAME_LIMIT - len(suffix) - 1]
    return f"{stem}_{suffix}"


def free_name(connection: duckdb.DuckDBPyConnection, schema: str, wanted: str) -> str:
    """The name, numbered until nothing in the schema is called it."""
    taken = {str(row[0]) for row in connection.execute(TAKEN, [schema] * 4).fetchall()}
    candidate, at = wanted, 2
    while candidate.lower() in taken:
        candidate = f"{wanted}_{at}"
        at += 1
    return candidate


def repeating(facts: RelationFacts, columns: list[str]) -> Composable:
    """Every group of values the columns hold more than once, nulls left out."""
    names = [Identifier(column) for column in columns]
    return SQL("SELECT 1 FROM {} WHERE {} GROUP BY {} HAVING count(*) > 1").format(
        table_of(facts),
        SQL(" AND ").join(SQL("{} IS NOT NULL").format(name) for name in names),
        SQL(", ").join(names),
    )


class DuckdbKeys:
    def __init__(self, session: DuckdbSession, relation: DuckdbRelation) -> None:
        self._session = session
        self._relation = relation

    async def _table(self, node_id: str) -> RelationFacts:
        facts = await self._relation.facts(node_id)
        refused = structure_reason(facts)
        if refused is not None:
            raise ValueError(refused)
        return facts

    @staticmethod
    def _columns(facts: RelationFacts, names: list[str]) -> list[str]:
        known = {column.name for column in facts.columns}
        for name in names:
            if name not in known:
                raise ValueError(say('Relation has no column "{column}"', column=name))
        return names

    async def create_index(self, request: CreateIndexRequest) -> CreateIndexResult:
        facts = await self._table(request.node_id)
        columns = self._columns(facts, request.columns)
        if request.method != "art":
            raise ValueError(say('Unknown index method "{method}"', method=request.method))

        def work(connection: duckdb.DuckDBPyConnection) -> CreateIndexResult:
            if request.unique:
                found, exact = bounded_count(connection, repeating(facts, columns))
                if found:
                    return IndexBlocked(duplicate_groups=found, exact=exact)
            name = free_name(connection, facts.schema, derived(facts.name, columns, "idx"))
            statement = SQL("CREATE " + ("UNIQUE " if request.unique else "") + "INDEX {} ON {} ({})")
            connection.execute(
                statement.format(
                    Identifier(name),
                    table_of(facts),
                    SQL(", ").join(Identifier(column) for column in columns),
                ).text()
            )
            return IndexCreated(name=name)

        return await restructure(self._session, work)

    async def drop_index(self, request: DropIndexRequest) -> IndexDropped:
        facts = await self._table(request.node_id)
        index = next((index for index in facts.indexes if index.name == request.name), None)
        if index is None:
            raise ValueError(say('Relation has no index "{name}"', name=request.name))
        statement = SQL("DROP INDEX {}").format(Identifier(facts.schema, index.name))
        await restructure(self._session, lambda connection: connection.execute(statement.text()))
        return IndexDropped(name=index.name)

    async def create_constraint(self, request: CreateConstraintRequest) -> CreateConstraintResult:
        facts = await self._table(request.node_id)
        spec = request.constraint
        if isinstance(spec, ForeignKeySpec):
            raise ValueError(
                say(
                    "DuckDB cannot add a foreign key to a table that already exists; "
                    "copy it into a table designed with the key"
                )
            )
        columns = self._columns(facts, spec.columns)
        statement = SQL("ALTER TABLE {} ADD UNIQUE ({})").format(
            table_of(facts), SQL(", ").join(Identifier(column) for column in columns)
        )

        def work(connection: duckdb.DuckDBPyConnection) -> CreateConstraintResult:
            found, exact = bounded_count(connection, repeating(facts, columns))
            if found:
                return RepeatingValues(groups=found, exact=exact)
            connection.execute(statement.text())
            return ConstraintCreated(name=derived(facts.name, columns, "key"))

        return await restructure(self._session, work)

    async def drop_constraint(self, request: DropConstraintRequest) -> ConstraintDropped:
        raise ValueError(
            say(
                "DuckDB cannot drop a constraint of a table that already exists; "
                "copy it into a table designed without it"
            )
        )
