"""Indexes and constraints of a SQLite table made and dropped (D39, D40, D255).

An index is SQLite's own CREATE and DROP INDEX. A unique key or a foreign key
is a clause of the table's definition, so adding or dropping one is a rebuild
(`restructure`). What the rows already contradict is counted first and
answered as a count, as on PostgreSQL.
"""

import sqlite3

from app.adapters.constraints import (
    ConstraintCreated,
    ConstraintDropped,
    CreateConstraintRequest,
    CreateConstraintResult,
    DropConstraintRequest,
    ForeignKeySpec,
    RepeatingValues,
    UnmatchedRows,
)
from app.adapters.indexes import (
    CreateIndexRequest,
    CreateIndexResult,
    DropIndexRequest,
    IndexBlocked,
    IndexCreated,
    IndexDropped,
)
from app.adapters.protocol import NodeNotFound
from app.adapters.relation import RefAction
from app.adapters.sqlite import ids
from app.adapters.sqlite.columns import bounded_count
from app.adapters.sqlite.definition import TableText, read_table
from app.adapters.sqlite.inspection import SCHEMA, RelationFacts
from app.adapters.sqlite.relation import SqliteRelation, model_of, structure_reason
from app.adapters.sqlite.restructure import (
    appended,
    constraint_names,
    edited,
    free_name,
    rebuild,
    without_clause,
)
from app.adapters.sqlite.session import SqliteSession
from app.adapters.sqlite.sql import SQL, Composable, Identifier, quoted_name
from app.core.translation import say

_ACTIONS: dict[RefAction, str] = {
    "no_action": "NO ACTION",
    "restrict": "RESTRICT",
    "cascade": "CASCADE",
    "set_null": "SET NULL",
    "set_default": "SET DEFAULT",
}
# Long enough to read, short enough to stay a name.
_NAME_LIMIT = 60


def _derived(table: str, columns: list[str], suffix: str) -> str:
    """A name in PostgreSQL's pattern: table, columns, then what it is."""
    stem = "_".join([table, *columns])[: _NAME_LIMIT - len(suffix) - 1]
    return f"{stem}_{suffix}"


def _repeating(table: str, columns: list[str]) -> Composable:
    """Every group of values the columns hold more than once, nulls left out.

    Two nulls do not collide in a SQLite unique key, as in PostgreSQL's.
    """
    names = [Identifier(column) for column in columns]
    return SQL("SELECT 1 FROM {} WHERE {} GROUP BY {} HAVING count(*) > 1").format(
        Identifier(SCHEMA, table),
        SQL(" AND ").join(SQL("{} IS NOT NULL").format(name) for name in names),
        SQL(", ").join(names),
    )


class SqliteKeys:
    def __init__(self, session: SqliteSession, relation: SqliteRelation) -> None:
        self._session = session
        self._relation = relation

    async def _changeable(self, node_id: str) -> tuple[RelationFacts, TableText]:
        facts = await self._relation.facts(node_id)
        refused = structure_reason(facts)
        if refused is not None:
            raise ValueError(refused)
        return facts, read_table(facts.text)

    @staticmethod
    def _columns(facts: RelationFacts, names: list[str]) -> list[str]:
        known = {column.name for column in facts.columns}
        for name in names:
            if name not in known:
                raise ValueError(say('Relation has no column "{column}"', column=name))
        return names

    async def create_index(self, request: CreateIndexRequest) -> CreateIndexResult:
        facts, _ = await self._changeable(request.node_id)
        columns = self._columns(facts, request.columns)
        if request.method != "btree":
            raise ValueError(say('Unknown index method "{method}"', method=request.method))

        def work(connection: sqlite3.Connection) -> CreateIndexResult:
            if request.unique:
                found, exact = bounded_count(connection, _repeating(facts.name, columns))
                if found:
                    return IndexBlocked(duplicate_groups=found, exact=exact)
            name = free_name(connection, _derived(facts.name, columns, "idx"))
            statement = SQL("CREATE " + ("UNIQUE " if request.unique else "") + "INDEX {} ON {} ({})")
            connection.execute(
                statement.format(
                    Identifier(SCHEMA, name),
                    Identifier(facts.name),
                    SQL(", ").join(Identifier(column) for column in columns),
                ).text()
            )
            return IndexCreated(name=name)

        return await self._session.write(work)

    async def drop_index(self, request: DropIndexRequest) -> IndexDropped:
        facts, _ = await self._changeable(request.node_id)
        index = next((index for index in facts.indexes if index.name == request.name), None)
        if index is None:
            raise ValueError(say('Relation has no index "{name}"', name=request.name))
        if index.origin == "pk":
            raise ValueError(
                say('Index "{name}" belongs to the primary key; drop that instead', name=index.name)
            )
        if index.origin == "u":
            owner = next(
                (key.name for key in facts.keys if key.kind == "UNIQUE" and key.columns == index.columns),
                index.name,
            )
            raise ValueError(
                say(
                    'Index "{name}" belongs to constraint "{constraint}"; drop that instead',
                    name=index.name,
                    constraint=owner,
                )
            )
        statement = SQL("DROP INDEX {}").format(Identifier(SCHEMA, index.name)).text()
        await self._session.write(lambda connection: connection.execute(statement))
        return IndexDropped(name=index.name)

    async def create_constraint(self, request: CreateConstraintRequest) -> CreateConstraintResult:
        facts, table = await self._changeable(request.node_id)
        spec = request.constraint
        columns = self._columns(facts, spec.columns)
        taken = set(constraint_names(table))
        stored = [column.name for column in facts.columns if column.generated is None]
        listed = ", ".join(quoted_name(column) for column in columns)
        if isinstance(spec, ForeignKeySpec):
            return await self._foreign(facts, table, spec, taken, stored)
        name = _derived(facts.name, columns, "key")
        if name in taken:
            raise ValueError(say("A constraint of that name already exists"))
        text = edited(table.text, [appended(table, f"CONSTRAINT {quoted_name(name)} UNIQUE ({listed})")])

        def work(connection: sqlite3.Connection) -> CreateConstraintResult:
            found, exact = bounded_count(connection, _repeating(facts.name, columns))
            if found:
                return RepeatingValues(groups=found, exact=exact)
            rebuild(connection, facts.name, text, stored)
            return ConstraintCreated(name=name)

        return await self._session.restructure(work)

    async def _foreign(
        self,
        facts: RelationFacts,
        table: TableText,
        spec: ForeignKeySpec,
        taken: set[str],
        stored: list[str],
    ) -> CreateConstraintResult:
        schema, target = ids.parse(spec.target_node_id)
        if schema != SCHEMA or not target:
            raise NodeNotFound(spec.target_node_id)
        referenced = model_of(spec.target_node_id, await self._relation.facts(spec.target_node_id))
        if not any(key.columns == spec.target_columns for key in referenced.candidate_keys):
            raise ValueError(say("The target relation has no unique key over those columns"))
        name = _derived(facts.name, spec.columns, "fkey")
        if name in taken:
            raise ValueError(say("A constraint of that name already exists"))
        clause = (
            f"CONSTRAINT {quoted_name(name)} FOREIGN KEY "
            f"({', '.join(quoted_name(column) for column in spec.columns)}) "
            f"REFERENCES {quoted_name(referenced.name)} "
            f"({', '.join(quoted_name(column) for column in spec.target_columns)}) "
            f"ON UPDATE {_ACTIONS[spec.on_update]} ON DELETE {_ACTIONS[spec.on_delete]}"
        )
        text = edited(table.text, [appended(table, clause)])
        here = [Identifier("s", column) for column in spec.columns]
        there = [Identifier("t", column) for column in spec.target_columns]
        # MATCH SIMPLE, as SQLite applies it: a row with a null in the key
        # points at nothing and breaks nothing.
        unmatched = SQL("SELECT 1 FROM {} AS s WHERE {} AND NOT EXISTS (SELECT 1 FROM {} AS t WHERE {})").format(
            Identifier(SCHEMA, facts.name),
            SQL(" AND ").join(SQL("{} IS NOT NULL").format(column) for column in here),
            Identifier(SCHEMA, referenced.name),
            SQL(" AND ").join(SQL("{} = {}").format(a, b) for a, b in zip(there, here, strict=True)),
        )

        def work(connection: sqlite3.Connection) -> CreateConstraintResult:
            found, exact = bounded_count(connection, unmatched)
            if found:
                return UnmatchedRows(rows=found, exact=exact)
            rebuild(connection, facts.name, text, stored)
            return ConstraintCreated(name=name)

        return await self._session.restructure(work)

    async def drop_constraint(self, request: DropConstraintRequest) -> ConstraintDropped:
        facts, table = await self._changeable(request.node_id)
        clause = constraint_names(table).get(request.name)
        if clause is None:
            raise ValueError(say('Relation has no constraint "{name}"', name=request.name))
        if clause.kind == "primary" and facts.without_rowid:
            raise ValueError(say("A table WITHOUT ROWID must keep its primary key"))
        text = edited(table.text, [without_clause(table, clause)])
        stored = [column.name for column in facts.columns if column.generated is None]
        await self._session.restructure(
            lambda connection: rebuild(connection, facts.name, text, stored)
        )
        return ConstraintDropped(name=request.name)
