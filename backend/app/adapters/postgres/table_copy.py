"""PostgreSQL tables copied with their structure, at either end (D182).

The source reads each table from `pg_catalog` with nothing else on the search
path, so every type, sequence and function outside it is printed qualified and
means the same thing in another database. The destination composes the copy
from that description: tables and types first, then the rows through `COPY`,
then keys, indexes, links and sequences — all in one transaction.
"""

import re
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Any, Literal

from psycopg import sql

from app.adapters.postgres.catalog import is_system_schema
from app.adapters.postgres.names import NAME_LIMIT_BYTES
from app.adapters.postgres.relation_changes import PostgresRelationChanges
from app.adapters.postgres.session import PostgresSession, Snapshot
from app.adapters.protocol import NodeNotFound
from app.adapters.relation import RefAction
from app.adapters.table_copy import (
    MAX_COPIED_TABLES,
    Arrived,
    CopiedAttribute,
    CopiedColumn,
    CopiedConstraint,
    CopiedIndex,
    CopiedLink,
    CopiedTable,
    CopiedType,
    CopyLoad,
    CopyProblem,
    CopyStatement,
    RowsOf,
    TableCopyPlan,
    TableCopyRequest,
    TableCopyTarget,
    TableRows,
    TypeKind,
    is_one_fragment,
)
from app.core.translation import N_, say

DIALECT = "postgresql"

# What a refused copy means, by SQLSTATE. The text PostgreSQL writes beside
# these names tables and quotes rows, and none of it is passed on.
COPY_REFUSALS = {
    "42P07": N_("Something with one of these names is already there"),
    "42710": N_("A constraint, index or type with one of these names is already there"),
    "42704": N_("A type, collation or other object the tables use is not in this database"),
    "42883": N_("A default, check or index uses a function this database does not have"),
    "42P01": N_("A table a link points at is not in this database"),
    "42501": N_("This connection may not create tables here"),
    "3F000": N_("That schema is no longer there"),
    "55P03": N_("A table the copy needs is locked by somebody else"),
    "23505": N_("The copied rows repeat a value a unique key forbids"),
    "23503": N_("Some copied rows point at rows the copy does not have"),
    "23514": N_("Some copied rows break a check"),
    "23502": N_("Some copied rows leave a required column empty"),
    "22P02": N_("A copied value cannot be read by its column"),
    "42830": N_("A link needs a key on the table it points at"),
}

_REF_ACTIONS: dict[str, RefAction] = {
    "a": "no_action",
    "r": "restrict",
    "c": "cascade",
    "n": "set_null",
    "d": "set_default",
}
_REF_SQL: dict[RefAction, str] = {
    "no_action": "NO ACTION",
    "restrict": "RESTRICT",
    "cascade": "CASCADE",
    "set_null": "SET NULL",
    "set_default": "SET DEFAULT",
}
_SERIALS: dict[str, Literal["smallserial", "serial", "bigserial"]] = {
    "int2": "smallserial",
    "int4": "serial",
    "int8": "bigserial",
}
_CONSTRAINT_KINDS: dict[str, Literal["primary_key", "unique", "check", "exclude"]] = {
    "p": "primary_key",
    "u": "unique",
    "c": "check",
    "x": "exclude",
}
_IDENTITIES: dict[str, Literal["always", "by_default"]] = {
    "a": "always",
    "d": "by_default",
}
_CONSTRAINT_OPENING = {
    "primary_key": "PRIMARY KEY",
    "unique": "UNIQUE",
    "check": "CHECK",
    "exclude": "EXCLUDE",
}
_CONSTRAINT_TITLE = {
    "primary_key": N_("Primary key {name}"),
    "unique": N_("Unique key {name}"),
    "check": N_("Check {name}"),
    "exclude": N_("Exclusion constraint {name}"),
}

# A type as `format_type` spells one: a name, qualified or quoted or both, a
# modifier in parentheses, the words after it and the brackets of an array.
_TYPE_SPELLING = re.compile(
    r'^(?:"[^"]+"|[A-Za-z_][A-Za-z0-9_$]*)'
    r'(?:\.(?:"[^"]+"|[A-Za-z_][A-Za-z0-9_$]*))?'
    r"(?: [a-z]+)*(?:\([0-9, ]+\))?(?: [a-z]+)*(?:\[\])*$"
)
_METHOD_BODY = re.compile(r"^[a-z_][a-z0-9_]* \(")
_NEXTVAL = re.compile(r"^nextval\('((?:[^']|'')+)'::regclass\)$")

# Read with nothing but pg_catalog on the search path, so what lies outside
# it is printed qualified. Local to the snapshot's transaction.
_QUALIFIED = "SELECT set_config('search_path', 'pg_catalog', true)"

_TABLES = """
SELECT c.oid, n.nspname AS schema_name, c.relname AS name, c.relkind,
       c.relpersistence, c.relispartition, c.reltuples, c.relrowsecurity,
       obj_description(c.oid, 'pg_class') AS comment,
       (SELECT count(*) FROM pg_trigger t
         WHERE t.tgrelid = c.oid AND NOT t.tgisinternal) AS triggers,
       (SELECT count(*) FROM pg_policy p WHERE p.polrelid = c.oid) AS policies,
       (SELECT count(*) FROM pg_rewrite r
         WHERE r.ev_class = c.oid AND r.rulename <> '_RETURN') AS rules,
       (SELECT count(*) FROM pg_inherits i WHERE i.inhrelid = c.oid) AS parents
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE (n.nspname::text, c.relname::text)
      IN (SELECT * FROM unnest(%s::text[], %s::text[]))
"""

_COLUMNS = """
SELECT a.attrelid AS oid, a.attname AS name,
       format_type(a.atttypid, a.atttypmod) AS type_sql,
       t.typname AS base_type,
       a.attnotnull AS not_null, a.attidentity AS identity,
       a.attgenerated AS generated,
       pg_get_expr(ad.adbin, ad.adrelid) AS expression,
       CASE WHEN a.attcollation <> t.typcollation AND a.attcollation <> 0
            THEN cn.nspname END AS collation_schema,
       CASE WHEN a.attcollation <> t.typcollation AND a.attcollation <> 0
            THEN co.collname END AS collation_name,
       col_description(a.attrelid, a.attnum) AS comment,
       seq.sequence AS owned_sequence,
       s.seqstart, s.seqincrement,
       CASE WHEN t.typcategory = 'A' THEN t.typelem ELSE t.oid END AS type_oid
FROM pg_attribute a
JOIN pg_class c ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_type t ON t.oid = a.atttypid
LEFT JOIN pg_attrdef ad ON ad.adrelid = a.attrelid AND ad.adnum = a.attnum
LEFT JOIN pg_collation co ON co.oid = a.attcollation
LEFT JOIN pg_namespace cn ON cn.oid = co.collnamespace
LEFT JOIN LATERAL (
    SELECT pg_get_serial_sequence(format('%%I.%%I', n.nspname, c.relname), a.attname)
           AS sequence
) seq ON true
LEFT JOIN pg_sequence s ON s.seqrelid = to_regclass(seq.sequence)
WHERE a.attrelid = ANY(%s::oid[]) AND a.attnum > 0 AND NOT a.attisdropped
ORDER BY a.attrelid, a.attnum
"""

# Every type the columns use, and every type those are made of: a domain's
# base, a composite type's attributes. An array stands for its element.
_USER_TYPES = """
WITH RECURSIVE used(oid) AS (
    SELECT CASE WHEN t.typcategory = 'A' THEN t.typelem ELSE t.oid END
      FROM pg_attribute a JOIN pg_type t ON t.oid = a.atttypid
     WHERE a.attrelid = ANY(%s::oid[]) AND a.attnum > 0 AND NOT a.attisdropped
  UNION
    SELECT CASE WHEN d.typcategory = 'A' THEN d.typelem ELSE d.oid END
      FROM used u
      JOIN pg_type t ON t.oid = u.oid
      JOIN LATERAL (
          SELECT t.typbasetype AS dep WHERE t.typtype = 'd'
          UNION ALL
          SELECT a.atttypid FROM pg_attribute a
            JOIN pg_class r ON r.oid = a.attrelid
           WHERE a.attrelid = t.typrelid AND r.relkind = 'c'
             AND a.attnum > 0 AND NOT a.attisdropped
      ) deps ON true
      JOIN pg_type d ON d.oid = deps.dep
)
SELECT t.oid, n.nspname AS schema_name, t.typname AS name, t.typtype,
       format('%%I.%%I', n.nspname, t.typname) AS spelled,
       (SELECT r.relkind FROM pg_class r WHERE r.oid = t.typrelid) AS relkind,
       (SELECT e.extname FROM pg_depend dep
          JOIN pg_extension e ON e.oid = dep.refobjid
         WHERE dep.classid = 'pg_type'::regclass AND dep.objid = t.oid
           AND dep.deptype = 'e' LIMIT 1) AS extension,
       (SELECT array_agg(e.enumlabel ORDER BY e.enumsortorder)
          FROM pg_enum e WHERE e.enumtypid = t.oid) AS labels,
       CASE WHEN t.typtype = 'd' THEN format_type(t.typbasetype, t.typtypmod) END AS base,
       (SELECT CASE WHEN b.typcategory = 'A' THEN b.typelem ELSE b.oid END
          FROM pg_type b WHERE b.oid = t.typbasetype) AS base_oid,
       t.typnotnull AS not_null,
       pg_get_expr(t.typdefaultbin, 0) AS default_expression,
       (SELECT array_agg(pg_get_constraintdef(c.oid) ORDER BY c.conname)
          FROM pg_constraint c WHERE c.contypid = t.oid AND c.contype = 'c') AS checks,
       (SELECT array_agg(a.attname ORDER BY a.attnum) FROM pg_attribute a
         WHERE a.attrelid = t.typrelid AND a.attnum > 0 AND NOT a.attisdropped
       ) AS attribute_names,
       (SELECT array_agg(format_type(a.atttypid, a.atttypmod) ORDER BY a.attnum)
          FROM pg_attribute a
         WHERE a.attrelid = t.typrelid AND a.attnum > 0 AND NOT a.attisdropped
       ) AS attribute_types,
       (SELECT array_agg(CASE WHEN at.typcategory = 'A' THEN at.typelem ELSE at.oid END
                         ORDER BY a.attnum)
          FROM pg_attribute a JOIN pg_type at ON at.oid = a.atttypid
         WHERE a.attrelid = t.typrelid AND a.attnum > 0 AND NOT a.attisdropped
       ) AS attribute_oids
FROM used u
JOIN pg_type t ON t.oid = u.oid
JOIN pg_namespace n ON n.oid = t.typnamespace
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
"""

_CONSTRAINTS = """
SELECT con.conrelid AS oid, con.conname AS name, con.contype,
       pg_get_constraintdef(con.oid) AS definition,
       con.convalidated AS validated, con.condeferrable AS deferrable,
       con.condeferred AS deferred, con.confupdtype, con.confdeltype,
       con.confmatchtype, fn.nspname AS target_schema, fc.relname AS target_name,
       (SELECT array_agg(att.attname ORDER BY u.ord)
          FROM unnest(con.conkey) WITH ORDINALITY AS u(attnum, ord)
          JOIN pg_attribute att
            ON att.attrelid = con.conrelid AND att.attnum = u.attnum) AS columns,
       (SELECT array_agg(att.attname ORDER BY u.ord)
          FROM unnest(con.confkey) WITH ORDINALITY AS u(attnum, ord)
          JOIN pg_attribute att
            ON att.attrelid = con.confrelid AND att.attnum = u.attnum) AS target_columns
FROM pg_constraint con
LEFT JOIN pg_class fc ON fc.oid = con.confrelid
LEFT JOIN pg_namespace fn ON fn.oid = fc.relnamespace
WHERE con.conrelid = ANY(%s::oid[]) AND con.contype IN ('p', 'u', 'c', 'x', 'f')
ORDER BY con.conrelid, con.contype, con.conname
"""

# An index a constraint owns is made with its constraint, so only the others.
_INDEXES = """
SELECT ix.indrelid AS oid, ic.relname AS name, ix.indisunique AS is_unique,
       pg_get_indexdef(ix.indexrelid) AS definition,
       format('CREATE %%sINDEX %%I ON %%I.%%I USING ',
              CASE WHEN ix.indisunique THEN 'UNIQUE ' ELSE '' END,
              ic.relname, n.nspname, c.relname) AS prefix
FROM pg_index ix
JOIN pg_class ic ON ic.oid = ix.indexrelid
JOIN pg_class c ON c.oid = ix.indrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE ix.indrelid = ANY(%s::oid[]) AND ix.indisvalid
  AND NOT EXISTS (
      SELECT 1 FROM pg_constraint k
       WHERE k.conindid = ix.indexrelid AND k.conrelid = ix.indrelid)
ORDER BY ix.indrelid, ic.relname
"""

# Only tables that could join the copy: a partition's key is its parent's,
# and a partitioned table is not copied.
_REFERENCED_BY = """
SELECT DISTINCT con.confrelid AS oid, n.nspname AS schema_name, c.relname AS name
FROM pg_constraint con
JOIN pg_class c ON c.oid = con.conrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE con.contype = 'f' AND con.confrelid = ANY(%s::oid[])
  AND con.conrelid <> con.confrelid
  AND c.relkind = 'r' AND NOT c.relispartition
ORDER BY 2, 3
"""

# A new table's name must not be taken by a relation or by a type: every
# table brings a type of its own name.
_TAKEN = """
SELECT c.relname AS name FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = %s
UNION
SELECT t.typname FROM pg_type t
JOIN pg_namespace n ON n.oid = t.typnamespace WHERE n.nspname = %s
"""

_TYPES = """
SELECT n.nspname AS schema_name, t.typname AS name, t.typtype AS kind,
       (SELECT array_agg(e.enumlabel ORDER BY e.enumsortorder)
          FROM pg_enum e WHERE e.enumtypid = t.oid) AS labels
FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
WHERE (n.nspname::text, t.typname::text)
      IN (SELECT * FROM unnest(%s::text[], %s::text[]))
"""

_SCHEMAS = "SELECT nspname AS name FROM pg_namespace WHERE nspname = ANY(%s::text[])"

_INSTALLED = """
SELECT e.extname AS name, n.nspname AS schema_name
FROM pg_extension e JOIN pg_namespace n ON n.oid = e.extnamespace
WHERE e.extname = ANY(%s::text[])
"""

_AVAILABLE = "SELECT name FROM pg_available_extensions WHERE name = ANY(%s::text[])"


class PostgresTableCopy:
    """Both ends of a copy of PostgreSQL tables."""

    table_copy_dialect = DIALECT

    def __init__(self, session: PostgresSession, relations: PostgresRelationChanges) -> None:
        self._session = session
        self._relations = relations

    @property
    def table_copy_database(self) -> str:
        return self._session.database()

    # The source's half.

    async def describe_for_copy(self, node_ids: list[str]) -> list[CopiedTable]:
        names = [_split(node_id) for node_id in node_ids]
        async with self._session.inspection() as reader:
            await reader.query(_QUALIFIED)
            tables = await reader.query(
                _TABLES, ([schema for schema, _ in names], [name for _, name in names])
            )
            found = {(str(row["schema_name"]), str(row["name"])): row for row in tables}
            oids = [int(row["oid"]) for row in tables]
            columns = await reader.query(_COLUMNS, (oids,))
            constraints = await reader.query(_CONSTRAINTS, (oids,))
            indexes = await reader.query(_INDEXES, (oids,))
            referencing = await reader.query(_REFERENCED_BY, (oids,))
            types = _types_of(await reader.query(_USER_TYPES, (oids,)))
        described: list[CopiedTable] = []
        for node_id, key in zip(node_ids, names, strict=True):
            row = found.get(key)
            if row is None:
                raise NodeNotFound(node_id)
            oid = int(row["oid"])
            described.append(
                _table(
                    node_id,
                    row,
                    [one for one in columns if int(one["oid"]) == oid],
                    [one for one in constraints if int(one["oid"]) == oid],
                    [one for one in indexes if int(one["oid"]) == oid],
                    [
                        f"{one['schema_name']}.{one['name']}"
                        for one in referencing
                        if int(one["oid"]) == oid
                    ],
                    types,
                )
            )
        return described

    @asynccontextmanager
    async def reading_tables(self) -> AsyncIterator[TableRows]:
        async with self._session.snapshot() as snapshot:
            yield _Rows(snapshot)

    # The destination's half.

    async def free_table_names(self, place_node_id: str, wanted: list[str]) -> list[str]:
        taken = await self._taken(place_node_id)
        free: list[str] = []
        for name in wanted:
            chosen = _free(name, taken)
            taken.add(chosen)
            free.append(chosen)
        return free

    async def plan_table_copy(self, request: TableCopyRequest) -> TableCopyPlan:
        return await _Planner(self, request).plan()

    async def carry_table_copy(
        self, request: TableCopyRequest, rows_of: RowsOf, arrived: Arrived
    ) -> None:
        plan = await self.plan_table_copy(request)
        if plan.problems:
            raise ValueError(plan.problems[0].message)
        step = say("Preparing the copy")
        try:
            async with self._session.transaction(refusals=COPY_REFUSALS) as work:
                # Links to the originals lock them; a busy one is a refusal
                # rather than a wait with no end.
                await work.schema_change("SET LOCAL lock_timeout = '10s'")
                for statement in plan.statements:
                    if statement.stage == "before":
                        step = statement.title
                        await work.schema_change(statement.sql)
                for load in plan.loads:
                    step = say("Rows of {table}", table=load.target_label)
                    await work.copy_in(
                        sql.SQL("COPY {} ({}) FROM STDIN")
                        .format(
                            sql.Identifier(load.schema_name, load.name),
                            sql.SQL(", ").join(sql.Identifier(one) for one in load.columns),
                        )
                        .as_string(),
                        _counted(load, rows_of(load), arrived),
                    )
                for statement in plan.statements:
                    if statement.stage == "after":
                        step = statement.title
                        await work.schema_change(statement.sql)
        except ValueError as refusal:
            said = str(refusal)
            # What the session says about a refusal no code above names.
            if said == say("The source rejected the change"):
                said = say("This database refused it")
            raise ValueError(f"{step}: {said[:1].lower()}{said[1:]}") from None

    async def _taken(self, schema: str) -> set[str]:
        rows = await self._session.query(_TAKEN, (schema, schema))
        return {str(row["name"]) for row in rows}


class _Rows:
    def __init__(self, snapshot: Snapshot) -> None:
        self._snapshot = snapshot

    def rows(self, node_id: str, columns: list[str]) -> AsyncIterator[bytes]:
        schema, name = _split(node_id)
        # A query rather than the table, so what the grid shows is what is
        # copied: a hypertable's rows live in its chunks.
        statement = sql.SQL("COPY (SELECT {} FROM {}) TO STDOUT").format(
            sql.SQL(", ").join(sql.Identifier(column) for column in columns),
            sql.Identifier(schema, name),
        )
        return self._snapshot.copy_out(statement.as_string())


async def _counted(
    load: CopyLoad, chunks: AsyncIterator[bytes], arrived: Arrived
) -> AsyncIterator[bytes]:
    """The chunks as they pass, with the rows in them counted: in COPY's text
    format a row is a line, and a newline inside a value is escaped."""
    rows = 0
    size = 0
    async for chunk in chunks:
        rows += chunk.count(b"\n")
        size += len(chunk)
        yield chunk
        await arrived(load, rows, size)


class _Planner:
    """One plan: the checks first, then the statements in the order they run."""

    def __init__(self, copy: PostgresTableCopy, request: TableCopyRequest) -> None:
        self._copy = copy
        self._request = request
        self._schema = request.place_node_id
        self._plan = TableCopyPlan()
        # Relation-level names in the schema: tables, indexes, sequences, types.
        self._taken: set[str] = set()
        # Types made in the place rather than where the source keeps them: the
        # source's spelling of each, and the new one.
        self._moves: dict[str, str] = {}
        # What follows the rows, in the order it must run: a link needs the
        # key it points at, whichever table that belongs to.
        self._keys: list[CopyStatement] = []
        self._links: list[CopyStatement] = []
        self._numbering: list[CopyStatement] = []

    async def plan(self) -> TableCopyPlan:
        request = self._request
        if request.dialect != DIALECT:
            self._problem(None, say("These tables are described in another dialect"))
            return self._plan
        if not await self._place_ok():
            return self._plan
        self._taken = await self._copy._taken(self._schema)
        self._names_ok()
        types = await self._types()
        if self._plan.problems:
            return self._plan
        self._plan.statements.extend(types)
        new_names = {target.table.node_id: target.name for target in request.tables}
        for target in request.tables:
            self._taken.add(target.name)
        for target in request.tables:
            self._table(target, new_names)
        self._plan.statements.extend(self._keys + self._links + self._numbering)
        return self._plan

    async def _place_ok(self) -> bool:
        try:
            options = await self._copy._relations.new_relation_options(self._schema)
        except NodeNotFound:
            self._problem(None, say("That schema is no longer there"))
            return False
        if not options.supported:
            self._problem(None, options.reason or say("Tables cannot be made here"))
            return False
        return True

    def _names_ok(self) -> None:
        seen: set[str] = set()
        for target in self._request.tables:
            table = target.table
            if table.refusal is not None:
                self._problem(table.node_id, f"{table.label}: {table.refusal}")
                continue
            name = target.name
            if name == "" or name != name.strip():
                self._problem(table.node_id, say("A table name cannot be empty or start or end with spaces"))
            elif len(name.encode("utf-8")) > NAME_LIMIT_BYTES:
                self._problem(table.node_id, say("{name} is longer than PostgreSQL allows", name=name))
            elif name in seen:
                self._problem(table.node_id, say("Two tables cannot both be called {name}", name=name))
            elif name in self._taken:
                self._problem(
                    table.node_id, say("{schema}.{name} is already there", schema=self._schema, name=name), kind="conflict"
                )
            seen.add(name)
        if len(self._request.tables) > MAX_COPIED_TABLES:
            self._problem(None, say("Copy at most {count} tables at a time", count=MAX_COPIED_TABLES))

    async def _types(self) -> list[CopyStatement]:
        """The types of the source's own that the columns use, made where missing.

        Within one database they are the same types. Elsewhere an enum is made
        again under its own qualified name, or in the place when its schema is
        not there — and then every text that names it is made to name the new
        one. Anything else must be there already.
        """
        if self._request.same_database:
            return []
        used: dict[str, tuple[CopiedType, str]] = {}
        for target in self._request.tables:
            for wanted in target.table.types:
                used.setdefault(wanted.spelled, (wanted, target.table.node_id))
        if not used:
            return []
        session = self._copy._session
        asked = [(one.schema_name, one.name) for one, _ in used.values()]
        asked += [(self._schema, name) for _, name in asked]
        rows = await session.query(
            _TYPES, ([schema for schema, _ in asked], [name for _, name in asked])
        )
        there = {(str(row["schema_name"]), str(row["name"])): row for row in rows}
        schemas = {
            str(row["name"])
            for row in await session.query(_SCHEMAS, (list({schema for schema, _ in asked}),))
        }
        extensions = list({one.extension for one, _ in used.values() if one.extension})
        installed = {
            str(row["name"]): str(row["schema_name"])
            for row in await session.query(_INSTALLED, (extensions,))
        }
        available = {
            str(row["name"]) for row in await session.query(_AVAILABLE, (extensions,))
        }
        made: list[CopyStatement] = []
        for wanted, node_id in used.values():
            # Where the source keeps it when that schema is here, or the place.
            schema = wanted.schema_name if wanted.schema_name in schemas else self._schema
            if wanted.kind == "extension" and wanted.extension is not None:
                extension = wanted.extension
                if extension not in installed:
                    if extension not in available:
                        self._problem(
                            node_id,
                            say("Type {schema_name}.{name} comes with the extension {extension}, which this server does not have", schema_name=wanted.schema_name, name=wanted.name, extension=extension),
                        )
                        continue
                    installed[extension] = schema
                    made.append(
                        CopyStatement(
                            title=say("Install the extension {extension}", extension=extension),
                            sql=sql.SQL("CREATE EXTENSION IF NOT EXISTS {} WITH SCHEMA {}")
                            .format(sql.Identifier(extension), sql.Identifier(schema))
                            .as_string(),
                        )
                    )
                schema = installed[extension]
                self._move(wanted, schema)
                continue
            self._move(wanted, schema)
            existing = there.get((schema, wanted.name))
            if existing is not None:
                if wanted.kind == "enum" and list(existing.get("labels") or []) != wanted.labels:
                    self._problem(
                        node_id, say("Type {schema}.{name} is here with other values", schema=schema, name=wanted.name)
                    )
                continue
            statement = self._made_type(wanted, schema, node_id)
            if statement is not None:
                made.append(statement)
        return made

    def _move(self, wanted: CopiedType, schema: str) -> None:
        if schema != wanted.schema_name:
            self._moves[wanted.spelled] = sql.Identifier(schema, wanted.name).as_string()

    def _made_type(self, wanted: CopiedType, schema: str, node_id: str) -> CopyStatement | None:
        """The statement that makes a type again, or None with the reason why not."""
        identifier = sql.Identifier(schema, wanted.name)
        label = f"{schema}.{wanted.name}"
        if wanted.kind == "enum":
            return CopyStatement(
                title=say("Create type {label}", label=label),
                sql=sql.SQL("CREATE TYPE {} AS ENUM ({})")
                .format(identifier, sql.SQL(", ").join(sql.Literal(one) for one in wanted.labels))
                .as_string(),
            )
        if wanted.kind == "composite":
            attributes: list[sql.Composable] = []
            for attribute in wanted.attributes:
                spelled = self._moved(attribute.type_sql)
                if not _TYPE_SPELLING.match(spelled):
                    self._problem(node_id, say("Type {label} could not be read", label=label))
                    return None
                attributes.append(
                    sql.SQL("{} {}").format(sql.Identifier(attribute.name), sql.SQL(spelled))
                )
            return CopyStatement(
                title=say("Create type {label}", label=label),
                sql=sql.SQL("CREATE TYPE {} AS ({})")
                .format(identifier, sql.SQL(", ").join(attributes))
                .as_string(),
            )
        if wanted.kind == "domain" and wanted.base is not None:
            base = self._moved(wanted.base)
            default = None if wanted.default is None else self._moved(wanted.default)
            checks = [self._moved(one) for one in wanted.checks]
            if (
                not _TYPE_SPELLING.match(base)
                or (default is not None and not is_one_fragment(default))
                or not all(is_one_fragment(one) and one.startswith("CHECK") for one in checks)
            ):
                self._problem(node_id, say("Domain {label} could not be read", label=label))
                return None
            parts: list[sql.Composable] = [
                sql.SQL("CREATE DOMAIN {} AS {}").format(identifier, sql.SQL(base))
            ]
            if default is not None:
                parts.append(sql.SQL("DEFAULT {}").format(sql.SQL(default)))
            if wanted.not_null:
                parts.append(sql.SQL("NOT NULL"))
            parts.extend(sql.SQL(one) for one in checks)
            return CopyStatement(
                title=say("Create domain {label}", label=label), sql=sql.SQL(" ").join(parts).as_string()
            )
        self._problem(node_id, say("Type {schema_name}.{name} is not in this database", schema_name=wanted.schema_name, name=wanted.name))
        return None

    def _table(self, target: TableCopyTarget, new_names: dict[str, str]) -> None:
        table = target.table
        node_id = table.node_id
        identifier = sql.Identifier(self._schema, target.name)
        label = f"{self._schema}.{target.name}"
        local: set[str] = set()
        definitions: list[sql.Composable] = []
        sequenced: list[str] = []
        for column in table.columns:
            composed = self._column(table, column)
            if composed is None:
                return
            definitions.append(composed)
            if column.identity is not None or column.serial is not None:
                sequenced.append(column.name)
        after: list[CopyStatement] = []
        for constraint in table.constraints:
            definition = self._moved(constraint.definition)
            if not is_one_fragment(definition) or not definition.startswith(
                _CONSTRAINT_OPENING[constraint.kind]
            ):
                self._warn(say("{label}: {name} could not be read, and is not copied", label=table.label, name=constraint.name))
                continue
            if constraint.kind == "check" and constraint.validated:
                # Checked as the rows arrive, which is what a check is for.
                name = _renamed(constraint.name, table.name, target.name, local)
                local.add(name)
                definitions.append(
                    sql.SQL("CONSTRAINT {} {}").format(sql.Identifier(name), sql.SQL(definition))
                )
                continue
            name = self._relation_name(constraint, table.name, target.name, local)
            after.append(
                CopyStatement(
                    node_id=node_id,
                    title=say(_CONSTRAINT_TITLE[constraint.kind], name=name),
                    sql=sql.SQL("ALTER TABLE {} ADD CONSTRAINT {} {}")
                    .format(identifier, sql.Identifier(name), sql.SQL(definition))
                    .as_string(),
                    stage="after",
                )
            )
        for index in table.indexes:
            body = self._moved(index.body)
            if not is_one_fragment(body) or not _METHOD_BODY.match(body):
                self._warn(say("{label}: index {name} could not be read, and is not copied", label=table.label, name=index.name))
                continue
            name = _free(_renamed(index.name, table.name, target.name, set()), self._taken)
            self._taken.add(name)
            after.append(
                CopyStatement(
                    node_id=node_id,
                    title=say("Index {name}", name=name),
                    sql=sql.SQL("CREATE {}INDEX {} ON {} USING {}")
                    .format(
                        sql.SQL("UNIQUE " if index.unique else ""),
                        sql.Identifier(name),
                        identifier,
                        sql.SQL(body),
                    )
                    .as_string(),
                    stage="after",
                )
            )
        for link in table.links:
            statement = self._link(table, target, link, new_names, local)
            if statement is not None:
                self._links.append(statement)
        if self._request.rows:
            for numbered in sequenced:
                self._numbering.append(
                    _continued(identifier, self._schema, target.name, numbered, node_id)
                )
        self._plan.statements.append(
            CopyStatement(
                node_id=node_id,
                title=say("Create table {label}", label=label),
                # A column to a line: the statement is reviewed before it runs.
                sql=sql.SQL("CREATE {}TABLE {} (\n    {}\n)")
                .format(
                    sql.SQL("UNLOGGED " if table.unlogged else ""),
                    identifier,
                    sql.SQL(",\n    ").join(definitions),
                )
                .as_string(),
            )
        )
        self._plan.statements.extend(_comments(node_id, identifier, label, table))
        self._keys.extend(after)
        if self._request.rows:
            self._plan.loads.append(
                CopyLoad(
                    node_id=node_id,
                    schema_name=self._schema,
                    name=target.name,
                    columns=[column.name for column in table.columns if column.generated is None],
                )
            )

    def _column(self, table: CopiedTable, column: CopiedColumn) -> sql.Composable | None:
        type_sql = self._moved(column.type_sql)
        if not _TYPE_SPELLING.match(type_sql):
            self._problem(
                table.node_id, say("{label}: the type of {name} could not be read", label=table.label, name=column.name)
            )
            return None
        parts: list[sql.Composable] = [
            sql.Identifier(column.name),
            sql.SQL(column.serial if column.serial is not None else type_sql),
        ]
        if column.collation_schema is not None and column.collation_name is not None:
            parts.append(
                sql.SQL("COLLATE {}").format(
                    sql.Identifier(column.collation_schema, column.collation_name)
                )
            )
        generated = None if column.generated is None else self._moved(column.generated)
        default = None if column.default is None else self._moved(column.default)
        if generated is not None:
            if is_one_fragment(generated):
                parts.append(sql.SQL("GENERATED ALWAYS AS ({}) STORED").format(sql.SQL(generated)))
            else:
                self._warn(
                    say("{label}: {name} is copied as a plain column, its generation could not be read", label=table.label, name=column.name)
                )
        elif column.identity is not None:
            parts.append(
                sql.SQL("GENERATED {} AS IDENTITY (START WITH {} INCREMENT BY {})").format(
                    sql.SQL("ALWAYS" if column.identity == "always" else "BY DEFAULT"),
                    sql.Literal(column.identity_start or 1),
                    sql.Literal(column.identity_increment or 1),
                )
            )
        elif default is not None and column.serial is None:
            if column.shared_sequence is not None and not self._request.same_database:
                self._warn(
                    say("{label}: {name} takes its default from {shared_sequence}, which is not copied; it has no default here", label=table.label, name=column.name, shared_sequence=column.shared_sequence)
                )
            elif is_one_fragment(default):
                parts.append(sql.SQL("DEFAULT {}").format(sql.SQL(default)))
            else:
                self._warn(say("{label}: the default of {name} could not be read, and is not copied", label=table.label, name=column.name))
        if column.not_null:
            parts.append(sql.SQL("NOT NULL"))
        return sql.SQL(" ").join(parts)

    def _link(
        self,
        table: CopiedTable,
        target: TableCopyTarget,
        link: CopiedLink,
        new_names: dict[str, str],
        local: set[str],
    ) -> CopyStatement | None:
        decision = target.links.get(link.name, "drop")
        if decision == "drop":
            return None
        if decision == "copy":
            copied = new_names.get(link.target_node_id)
            if copied is None:
                return None
            points_at = sql.Identifier(self._schema, copied)
            label = f"{self._schema}.{copied}"
        else:
            if not self._request.same_database:
                return None
            points_at = sql.Identifier(link.target_schema, link.target_name)
            label = f"{link.target_schema}.{link.target_name}"
        name = _renamed(link.name, table.name, target.name, local)
        local.add(name)
        clauses: list[sql.Composable] = [
            sql.SQL("FOREIGN KEY ({}) REFERENCES {} ({})").format(
                sql.SQL(", ").join(sql.Identifier(one) for one in link.columns),
                points_at,
                sql.SQL(", ").join(sql.Identifier(one) for one in link.target_columns),
            )
        ]
        if link.match == "full":
            clauses.append(sql.SQL("MATCH FULL"))
        clauses.append(sql.SQL("ON UPDATE " + _REF_SQL[link.on_update]))
        clauses.append(sql.SQL("ON DELETE " + _REF_SQL[link.on_delete]))
        if link.deferrable:
            clauses.append(
                sql.SQL("DEFERRABLE INITIALLY DEFERRED" if link.initially_deferred else "DEFERRABLE")
            )
        if not link.validated:
            clauses.append(sql.SQL("NOT VALID"))
        return CopyStatement(
            node_id=table.node_id,
            title=say("Link {name} to {label}", name=name, label=label),
            sql=sql.SQL("ALTER TABLE {} ADD CONSTRAINT {} {}")
            .format(
                sql.Identifier(self._schema, target.name),
                sql.Identifier(name),
                sql.SQL(" ").join(clauses),
            )
            .as_string(),
            stage="after",
        )

    def _relation_name(
        self, constraint: CopiedConstraint, old: str, new: str, local: set[str]
    ) -> str:
        """A constraint's name, free in the schema when an index carries it."""
        name = _renamed(constraint.name, old, new, local)
        if constraint.kind != "check":
            name = _free(name, self._taken)
            self._taken.add(name)
        local.add(name)
        return name

    def _moved(self, text: str) -> str:
        return _relocated(text, self._moves)

    def _problem(
        self,
        node_id: str | None,
        message: str,
        kind: Literal["invalid", "conflict"] = "invalid",
    ) -> None:
        self._plan.problems.append(CopyProblem(node_id=node_id, message=message, kind=kind))

    def _warn(self, message: str) -> None:
        self._plan.warnings.append(message)


def _relocated(text: str, moves: dict[str, str]) -> str:
    """The text with every moved type named anew.

    Only outside literals, and only where the whole name stands: a value that
    happens to spell a type is a value, and `mood_level` is not `mood`.
    """
    if not moves:
        return text
    written: list[str] = []
    index = 0
    while index < len(text):
        if text[index] == "'":
            closing = text.find("'", index + 1)
            while closing != -1 and text[closing + 1 : closing + 2] == "'":
                closing = text.find("'", closing + 2)
            end = len(text) if closing == -1 else closing + 1
            written.append(text[index:end])
            index = end
            continue
        for old, new in moves.items():
            end = index + len(old)
            if text.startswith(old, index) and _stands_alone(text, index, end):
                written.append(new)
                index = end
                break
        else:
            written.append(text[index])
            index += 1
    return "".join(written)


def _stands_alone(text: str, start: int, end: int) -> bool:
    before = text[start - 1] if start > 0 else " "
    after = text[end] if end < len(text) else " "
    return not (before.isalnum() or before in '_$."') and not (after.isalnum() or after in "_$")


def _continued(
    identifier: sql.Identifier, schema: str, table: str, column: str, node_id: str
) -> CopyStatement:
    """The column's sequence set past its largest copied value."""
    return CopyStatement(
        node_id=node_id,
        title=say("Continue the numbering of {table}.{column}", table=table, column=column),
        sql=sql.SQL(
            "SELECT setval(pg_get_serial_sequence({}, {}), m) "
            "FROM (SELECT max({}) AS m FROM {}) AS copied WHERE m IS NOT NULL"
        )
        .format(
            sql.Literal(sql.Identifier(schema, table).as_string()),
            sql.Literal(column),
            sql.Identifier(column),
            identifier,
        )
        .as_string(),
        stage="after",
    )


def _comments(
    node_id: str, identifier: sql.Identifier, label: str, table: CopiedTable
) -> Iterator[CopyStatement]:
    if table.comment is not None:
        yield CopyStatement(
            node_id=node_id,
            title=say("Comment on {label}", label=label),
            sql=sql.SQL("COMMENT ON TABLE {} IS {}")
            .format(identifier, sql.Literal(table.comment))
            .as_string(),
        )
    for column in table.columns:
        if column.comment is not None:
            yield CopyStatement(
                node_id=node_id,
                title=say("Comment on {label}.{name}", label=label, name=column.name),
                sql=sql.SQL("COMMENT ON COLUMN {}.{} IS {}")
                .format(identifier, sql.Identifier(column.name), sql.Literal(column.comment))
                .as_string(),
            )


def _split(node_id: str) -> tuple[str, str]:
    schema, _, name = node_id.partition(".")
    if not schema or not name:
        raise ValueError(say('"{node_id}" is not a table: expected schema.table', node_id=node_id))
    return schema, name


def _clipped(name: str, room: int) -> str:
    """A name cut to fit `room` bytes, never through a character."""
    encoded = name.encode("utf-8")[:room]
    return encoded.decode("utf-8", errors="ignore")


def _free(name: str, taken: set[str]) -> str:
    """The name, or the first `…_copy`, `…_copy_2` nothing holds."""
    if name not in taken:
        return name
    number = 1
    while True:
        suffix = "_copy" if number == 1 else f"_copy_{number}"
        candidate = _clipped(name, NAME_LIMIT_BYTES - len(suffix.encode("utf-8"))) + suffix
        if candidate not in taken:
            return candidate
        number += 1


def _renamed(name: str, old: str, new: str, local: set[str]) -> str:
    """A constraint or index named after its table, named after the copy."""
    renamed = new + name[len(old) :] if name.startswith(old) and old != new else name
    renamed = _clipped(renamed, NAME_LIMIT_BYTES)
    number = 1
    candidate = renamed
    while candidate in local:
        suffix = f"_{number}"
        candidate = _clipped(renamed, NAME_LIMIT_BYTES - len(suffix)) + suffix
        number += 1
    return candidate


def _table(
    node_id: str,
    row: dict[str, Any],
    columns: list[dict[str, Any]],
    constraints: list[dict[str, Any]],
    indexes: list[dict[str, Any]],
    referenced_by: list[str],
    types: dict[int, tuple[CopiedType, list[int]]],
) -> CopiedTable:
    schema = str(row["schema_name"])
    name = str(row["name"])
    base = CopiedTable(node_id=node_id, schema_name=schema, name=name)
    refusal = _refusal(schema, row)
    if refusal is not None:
        return base.model_copy(update={"refusal": refusal})
    left_behind: list[str] = []
    triggers = int(row["triggers"])
    if triggers:
        left_behind.append(
            say("1 trigger") if triggers == 1 else say("{count} triggers", count=triggers)
        )
    if bool(row["relrowsecurity"]) or int(row["policies"]):
        policies = int(row["policies"])
        if policies == 0:
            left_behind.append(say("row security"))
        elif policies == 1:
            left_behind.append(say("row security and 1 policy"))
        else:
            left_behind.append(say("row security and {count} policies", count=policies))
    rules = int(row["rules"])
    if rules:
        left_behind.append(say("1 rule") if rules == 1 else say("{count} rules", count=rules))
    if int(row["parents"]):
        left_behind.append(say("inheritance from its parent table"))
    estimate = float(row["reltuples"])
    links = [_link_of(one) for one in constraints if one["contype"] == "f"]
    return base.model_copy(
        update={
            "comment": row.get("comment"),
            "unlogged": row["relpersistence"] == "u",
            "columns": [_column_of(one) for one in columns],
            "constraints": [
                CopiedConstraint(
                    name=str(one["name"]),
                    kind=_CONSTRAINT_KINDS[str(one["contype"])],
                    definition=str(one["definition"]),
                    validated=bool(one["validated"]),
                )
                for one in constraints
                if one["contype"] != "f"
            ],
            "indexes": [_index_of(one) for one in indexes],
            "links": links,
            "types": _closure([int(one["type_oid"]) for one in columns], types),
            "referenced_by": [one for one in referenced_by if one != node_id],
            "left_behind": left_behind,
            "row_estimate": None if estimate < 0 else int(estimate),
        }
    )


def _refusal(schema: str, row: dict[str, Any]) -> str | None:
    if is_system_schema(schema):
        return say('"{schema}" belongs to the server', schema=schema)
    if row["relkind"] == "p":
        return say("partitioned tables are not copied yet")
    if bool(row["relispartition"]):
        return say("partitions are not copied yet")
    if row["relkind"] != "r":
        return say("only tables are copied with their structure")
    if row["relpersistence"] == "t":
        return say("a temporary table lives only in its own session")
    return None


def _column_of(row: dict[str, Any]) -> CopiedColumn:
    expression = row.get("expression")
    generated = row.get("generated") == "s"
    identity = _IDENTITIES.get(str(row.get("identity") or ""))
    owned = row.get("owned_sequence")
    default = None if generated else expression
    serial = None
    shared = None
    if default is not None and identity is None:
        drawn = _NEXTVAL.match(default)
        if drawn is not None:
            sequence = drawn.group(1).replace("''", "'")
            if owned is not None and sequence == owned:
                serial = _SERIALS.get(str(row["base_type"]))
            else:
                shared = sequence
    return CopiedColumn(
        name=str(row["name"]),
        type_sql=str(row["type_sql"]),
        not_null=bool(row["not_null"]),
        default=default if serial is None else None,
        identity=identity,
        identity_start=int(row["seqstart"]) if identity and row.get("seqstart") is not None else None,
        identity_increment=(
            int(row["seqincrement"]) if identity and row.get("seqincrement") is not None else None
        ),
        generated=expression if generated else None,
        collation_schema=row.get("collation_schema"),
        collation_name=row.get("collation_name"),
        comment=row.get("comment"),
        serial=serial,
        shared_sequence=shared,
    )


def _types_of(rows: list[dict[str, Any]]) -> dict[int, tuple[CopiedType, list[int]]]:
    """Each type by its oid, with the oids of the types it is made of."""
    found: dict[int, tuple[CopiedType, list[int]]] = {}
    for row in rows:
        kind: TypeKind
        if row.get("extension") is not None:
            kind = "extension"
        elif row["typtype"] == "e":
            kind = "enum"
        elif row["typtype"] == "d":
            kind = "domain"
        elif row["typtype"] == "c" and row.get("relkind") == "c":
            kind = "composite"
        else:
            kind = "other"
        names = [str(one) for one in row.get("attribute_names") or []]
        spelled = [str(one) for one in row.get("attribute_types") or []]
        made_of = [int(one) for one in row.get("attribute_oids") or []]
        if row.get("base_oid") is not None and kind == "domain":
            made_of.append(int(row["base_oid"]))
        found[int(row["oid"])] = (
            CopiedType(
                schema_name=str(row["schema_name"]),
                name=str(row["name"]),
                spelled=str(row["spelled"]),
                kind=kind,
                labels=[str(one) for one in row.get("labels") or []],
                extension=row.get("extension"),
                base=row.get("base"),
                not_null=bool(row.get("not_null")),
                default=row.get("default_expression"),
                checks=[str(one) for one in row.get("checks") or []],
                attributes=[
                    CopiedAttribute(name=name, type_sql=type_sql)
                    for name, type_sql in zip(names, spelled, strict=False)
                ],
            ),
            [] if kind == "extension" else made_of,
        )
    return found


def _closure(
    direct: list[int], types: dict[int, tuple[CopiedType, list[int]]]
) -> list[CopiedType]:
    """The types reached from `direct`, each after the ones it is made of."""
    ordered: list[CopiedType] = []
    seen: set[int] = set()

    def visit(oid: int) -> None:
        if oid in seen or oid not in types:
            return
        seen.add(oid)
        wanted, made_of = types[oid]
        for part in made_of:
            visit(part)
        ordered.append(wanted)

    for oid in direct:
        visit(oid)
    return ordered


def _index_of(row: dict[str, Any]) -> CopiedIndex:
    definition = str(row["definition"])
    prefix = str(row["prefix"])
    # Anything but the expected opening leaves nothing to compose from.
    body = definition[len(prefix) :] if definition.startswith(prefix) else ""
    return CopiedIndex(name=str(row["name"]), unique=bool(row["is_unique"]), body=body)


def _link_of(row: dict[str, Any]) -> CopiedLink:
    match: Literal["simple", "full"] = "full" if row.get("confmatchtype") == "f" else "simple"
    return CopiedLink(
        name=str(row["name"]),
        columns=[str(one) for one in row.get("columns") or []],
        target_node_id=f"{row['target_schema']}.{row['target_name']}",
        target_schema=str(row["target_schema"]),
        target_name=str(row["target_name"]),
        target_columns=[str(one) for one in row.get("target_columns") or []],
        on_update=_REF_ACTIONS.get(str(row["confupdtype"]), "no_action"),
        on_delete=_REF_ACTIONS.get(str(row["confdeltype"]), "no_action"),
        match=match,
        deferrable=bool(row["deferrable"]),
        initially_deferred=bool(row["deferred"]),
        validated=bool(row["validated"]),
    )
