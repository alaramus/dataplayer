"""Planning and creating one designed SQLite table (D117, D256).

The plan a person reviews and the statements that run come from one composer,
as PostgreSQL's do: a `CREATE TABLE`, then one `CREATE INDEX` per index, run in
one transaction, since SQLite's structure changes are transactional (D253).

What SQLite does not have is a problem next to the object that asks for it —
an unlogged or partitioned table, a deferrable unique key, MATCH FULL, NULLS
FIRST, INCLUDE, operator classes, an identity that is ALWAYS or steps by more
than one — rather than a statement refused after the person has reviewed it.
"""

import hashlib
import json
import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Literal

from app.adapters.catalog import CatalogNode, SchemaNode
from app.adapters.expressions import (
    Arithmetic,
    BooleanGroup,
    Cast,
    ColumnReference,
    Comparison,
    Expression,
    ExpressionContext,
    FunctionCall,
    LiteralValue,
    Membership,
    Negation,
    NullTest,
    referenced_columns,
    too_large,
)
from app.adapters.protocol import NodeNotFound
from app.adapters.relation import IndexMethodOption, RefAction
from app.adapters.sqlite import ids
from app.adapters.sqlite.catalog import SqliteCatalog
from app.adapters.sqlite.columns import literal as default_literal
from app.adapters.sqlite.inspection import SCHEMA
from app.adapters.sqlite.relation import SqliteRelation
from app.adapters.sqlite.session import Reading, SqliteSession
from app.adapters.sqlite.sql import quoted_name
from app.adapters.sqlite.types import build_column_type
from app.adapters.table_design import (
    DesignAbilities,
    DesignChoice,
    DesignColumn,
    DesignColumnType,
    DesignForeignKey,
    DesignIndex,
    DesignLimits,
    DesignRefused,
    DesignTypeCategory,
    DesignTypeOption,
    DesignTypeParameter,
    ExpressionDefault,
    FunctionOption,
    HypertableOffer,
    IdentityGeneration,
    IndexColumnKey,
    LiteralDefault,
    NoGeneration,
    PlannedStatement,
    PlanProblem,
    StoredGeneration,
    TableDefinition,
    TableDesignOptions,
    TablePlan,
    TablePlanRequest,
)
from app.adapters.words import worded_titles
from app.core.translation import N_, say

# SQLite sets no limit on a name; this keeps one readable on every screen.
NAME_LIMIT = 128


@dataclass(frozen=True)
class _Type:
    option: DesignTypeOption
    base: str


def _type(
    code: str,
    title: str,
    spelling: str,
    base: str,
    *,
    parameters: list[DesignTypeParameter] | None = None,
    identity: bool = False,
    category: DesignTypeCategory = "other",
) -> _Type:
    return _Type(
        option=DesignTypeOption(
            code=code,
            title=title,
            sql=spelling,
            parameters=parameters or [],
            array_supported=False,
            identity_supported=identity,
            category=category,
        ),
        base=base,
    )


# Declared types whose affinity and name read back as their category (D250).
# Codes shared with the add-a-column vocabulary (D255) mean the same type.
DESIGN_TYPES: dict[str, _Type] = {
    item.option.code: item
    for item in (
        _type("text", N_("Text"), "TEXT", "TEXT", category="text"),
        _type("varchar", N_("Text, limited"), "VARCHAR(n)", "VARCHAR", parameters=["length"], category="text"),
        _type("integer", N_("Integer"), "INTEGER", "INTEGER", identity=True, category="number"),
        _type("real", N_("Floating point"), "REAL", "REAL", category="number"),
        _type("numeric", N_("Number"), "NUMERIC", "NUMERIC", category="number"),
        _type(
            "decimal",
            N_("Decimal"),
            "DECIMAL(p,s)",
            "DECIMAL",
            parameters=["precision", "scale"],
            category="number",
        ),
        _type("boolean", N_("Boolean (0 or 1)"), "BOOLEAN", "BOOLEAN", category="boolean"),
        _type("date", N_("Date"), "DATE", "DATE", category="temporal"),
        _type("datetime", N_("Date and time"), "DATETIME", "DATETIME", category="temporal"),
        _type("json", N_("JSON"), "JSON", "JSON", category="document"),
        _type("uuid", N_("UUID as text"), "UUID", "UUID", category="text"),
        _type("blob", N_("Binary"), "BLOB", "BLOB"),
    )
}


@dataclass(frozen=True)
class _Function:
    option: FunctionOption
    fragment: str
    # Written without parentheses, as a keyword.
    bare: bool = False


_EVERYWHERE: list[ExpressionContext] = ["default", "generated", "check", "index"]
_DEFAULT_ONLY: list[ExpressionContext] = ["default"]


def _function(
    code: str,
    title: str,
    signature: str,
    fragment: str,
    arity: int,
    contexts: list[ExpressionContext],
    *,
    bare: bool = False,
) -> _Function:
    return _Function(
        option=FunctionOption(code=code, title=title, signature=signature, arity=arity, contexts=contexts),
        fragment=fragment,
        bare=bare,
    )


# SQLite refuses the clock in a generated column, a check or an index.
DESIGN_FUNCTIONS: dict[str, _Function] = {
    item.option.code: item
    for item in (
        _function("now", N_("Now"), "CURRENT_TIMESTAMP", "CURRENT_TIMESTAMP", 0, _DEFAULT_ONLY, bare=True),
        _function("current_date", N_("Today"), "CURRENT_DATE", "CURRENT_DATE", 0, _DEFAULT_ONLY, bare=True),
        _function("lower", N_("Lower case"), "lower(x)", "lower", 1, _EVERYWHERE),
        _function("upper", N_("Upper case"), "upper(x)", "upper", 1, _EVERYWHERE),
        _function("trim", N_("Trimmed"), "trim(x)", "trim", 1, _EVERYWHERE),
        _function("length", N_("Length"), "length(x)", "length", 1, _EVERYWHERE),
        _function("abs", N_("Absolute"), "abs(x)", "abs", 1, _EVERYWHERE),
        _function("round", N_("Rounded"), "round(x)", "round", 1, _EVERYWHERE),
        _function("coalesce", N_("First value present"), "coalesce(x, y)", "coalesce", 2, _EVERYWHERE),
    )
}

_COMPARE = {"eq": "=", "ne": "<>", "lt": "<", "lte": "<=", "gt": ">", "gte": ">="}
_ARITHMETIC = {"add": "+", "subtract": "-", "multiply": "*", "divide": "/"}
_REF_ACTIONS: dict[RefAction, str] = {
    "no_action": "NO ACTION",
    "restrict": "RESTRICT",
    "cascade": "CASCADE",
    "set_null": "SET NULL",
    "set_default": "SET DEFAULT",
}

REFERENCE_ACTION_CHOICES = [
    DesignChoice(code="no_action", title=N_("No action")),
    DesignChoice(code="restrict", title=N_("Restrict")),
    DesignChoice(code="cascade", title=N_("Cascade")),
    DesignChoice(code="set_null", title=N_("Set null")),
    DesignChoice(code="set_default", title=N_("Set default")),
]
MATCH_CHOICES = [DesignChoice(code="simple", title=N_("Match simple"))]
PERSISTENCE_CHOICES = [DesignChoice(code="permanent", title=N_("Permanent"))]

DESIGN_INDEX_METHODS = [
    IndexMethodOption(code="btree", title=N_("B-tree"), sql="", unique_supported=True, multi_column_supported=True),
]

# The collations SQLite builds in; a file can use no other here.
COLLATIONS = ["BINARY", "NOCASE", "RTRIM"]

_TAKEN = "SELECT lower(name) FROM sqlite_schema"


class _Problem(Exception):
    def __init__(
        self,
        message: str,
        *,
        field_name: str | None = None,
        object_id: str | None = None,
        kind: Literal["invalid", "conflict"] = "invalid",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.field_name = field_name
        self.object_id = object_id
        self.kind = kind


@dataclass
class _Draft:
    definition: TableDefinition
    columns: dict[str, DesignColumn]
    taken: set[str]
    used: set[str] = field(default_factory=set)
    problems: list[PlanProblem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def note(self, problem: _Problem, object_id: str | None) -> None:
        self.problems.append(
            PlanProblem(
                object_id=problem.object_id or object_id,
                field=problem.field_name,
                message=problem.message,
                kind=problem.kind,
            )
        )


def literal(text: str) -> str:
    """A string literal as SQLite reads it: a quote is doubled, nothing escapes."""
    if "\x00" in text:
        raise _Problem(say("A value cannot contain a NUL character"), field_name="expression")
    return "'" + text.replace("'", "''") + "'"


def type_sql(chosen: DesignColumnType) -> str:
    known = DESIGN_TYPES.get(chosen.code)
    if known is None:
        raise _Problem(say('Unknown column type "{code}"', code=chosen.code), field_name="type")
    takes = known.option.parameters
    title = say(known.option.title)
    if chosen.dimensions:
        raise _Problem(say("SQLite has no array columns"), field_name="type")
    if chosen.length is not None and "length" not in takes:
        raise _Problem(say("{title} takes no length", title=title), field_name="type")
    if chosen.precision is not None and "precision" not in takes:
        raise _Problem(say("{title} takes no precision", title=title), field_name="type")
    if chosen.scale is not None and "scale" not in takes:
        raise _Problem(say("{title} takes no scale", title=title), field_name="type")
    if chosen.scale is not None and chosen.precision is None:
        raise _Problem(say("{title} needs a precision before a scale", title=title), field_name="type")
    if chosen.precision is not None and chosen.scale is not None and chosen.scale > chosen.precision:
        raise _Problem(say("A scale cannot exceed its precision"), field_name="type")
    if chosen.length is not None:
        return f"{known.base}({chosen.length})"
    if chosen.precision is not None:
        return f"{known.base}({chosen.precision},{chosen.scale or 0})"
    return known.base


class SqliteTableDesign:
    """The three questions a designed table asks of one SQLite file."""

    def __init__(self, session: SqliteSession, catalog: SqliteCatalog, relation: SqliteRelation) -> None:
        self._session = session
        self._catalog = catalog
        self._relation = relation

    async def _destination(self, node_id: str) -> tuple[SchemaNode | None, str | None]:
        node = (await self._catalog.path_to(node_id))[-1]
        if not isinstance(node, SchemaNode):
            return None, say("A table is created in a schema")
        return node, None

    async def table_design_options(self, node_id: str) -> TableDesignOptions:
        node, reason = await self._destination(node_id)
        if node is None:
            return TableDesignOptions(supported=False, reason=reason)
        return TableDesignOptions(
            supported=True,
            schema_label=node.name,
            types=worded_titles(item.option for item in DESIGN_TYPES.values()),
            index_methods=worded_titles(DESIGN_INDEX_METHODS),
            functions=worded_titles(item.option for item in DESIGN_FUNCTIONS.values()),
            collations=list(COLLATIONS),
            reference_actions=worded_titles(REFERENCE_ACTION_CHOICES),
            match_modes=worded_titles(MATCH_CHOICES),
            persistence_options=worded_titles(PERSISTENCE_CHOICES),
            hypertable=HypertableOffer(offered=False),
            abilities=DesignAbilities(
                unique_constraints=True,
                foreign_keys=True,
                deferrable_foreign_keys=True,
                index_direction=True,
                partial_indexes=True,
            ),
            limits=DesignLimits(name_bytes=NAME_LIMIT),
        )

    async def plan_table(self, request: TablePlanRequest) -> TablePlan:
        draft = await self._draft(request.node_id, request.definition)
        statements = await self._statements(draft)
        if draft.problems:
            return TablePlan(revision=request.revision, problems=draft.problems, warnings=draft.warnings)
        return TablePlan(
            revision=request.revision,
            fingerprint=_fingerprint(request.node_id, statements),
            statements=statements,
            warnings=draft.warnings,
        )

    async def create_table(self, node_id: str, definition: TableDefinition, fingerprint: str) -> CatalogNode:
        """Create the reviewed table, composed again rather than taken from the client."""
        plan = await self.plan_table(TablePlanRequest(node_id=node_id, definition=definition))
        if plan.problems:
            raise DesignRefused(plan.problems[0])
        if plan.fingerprint != fingerprint:
            raise DesignRefused(
                PlanProblem(kind="conflict", message=say("The plan changed since it was reviewed; look at it again"))
            )

        def work(connection: sqlite3.Connection) -> None:
            for statement in plan.statements:
                connection.execute(statement.sql)

        # One transaction: the table and its indexes arrive together or not at all.
        await self._session.restructure(work)
        return (await self._catalog.path_to(ids.relation_id(definition.name)))[-1]

    async def _draft(self, node_id: str, definition: TableDefinition) -> _Draft:
        node, reason = await self._destination(node_id)
        if node is None:
            raise ValueError(reason)

        def read(reading: Reading) -> set[str]:
            return {str(row[0]) for row in reading.tuples(_TAKEN)}

        return _Draft(
            definition=definition,
            columns={column.id: column for column in definition.columns},
            taken=await self._session.inspection(read),
        )

    async def _statements(self, draft: _Draft) -> list[PlannedStatement]:
        definition = draft.definition
        _check_name(draft, definition.name, None)
        if definition.name.lower() in draft.taken:
            draft.problems.append(
                PlanProblem(
                    field="name",
                    kind="conflict",
                    message=say('Something called "{name}" is already in that schema', name=definition.name),
                )
            )
        if definition.persistence != "permanent":
            draft.problems.append(PlanProblem(field="persistence", message=say("SQLite has no unlogged tables")))
        if definition.partition is not None:
            draft.problems.append(PlanProblem(field="partition", message=say("SQLite has no partitioned tables")))
        if definition.hypertable is not None:
            draft.problems.append(
                PlanProblem(field="hypertable", message=say("A hypertable is TimescaleDB's, not SQLite's"))
            )
        if definition.comment or any(column.comment for column in definition.columns):
            draft.warnings.append(say("SQLite keeps no comments; the comments given are not kept"))
        _check_column_names(draft)
        identity = _identity(draft)
        lines = _column_lines(draft, identity)
        lines += _key_lines(draft, identity)
        lines += await self._foreign_lines(draft)
        indexes = _index_statements(draft)
        if draft.problems:
            return []
        table = quoted_name(SCHEMA, definition.name)
        statements = [
            PlannedStatement(
                title=say("Table {name}", name=definition.name),
                sql=f"CREATE TABLE {table} (\n    " + ",\n    ".join(lines) + "\n)",
            )
        ]
        statements += indexes
        start = _identity_start(identity)
        if start is not None:
            statements.append(
                PlannedStatement(
                    title=say("Where {name} starts counting", name=definition.name),
                    sql=(
                        "INSERT INTO sqlite_sequence (name, seq) "  # noqa: S608 — reviewed text: a quoted literal and an integer
                        f"VALUES ({literal(definition.name)}, {start - 1})"
                    ),
                )
            )
        return statements

    async def _foreign_lines(self, draft: _Draft) -> list[str]:
        lines: list[str] = []
        for foreign in draft.definition.foreign_keys:
            try:
                lines.append(await self._foreign_line(draft, foreign))
            except _Problem as problem:
                draft.note(problem, foreign.id)
        return lines

    async def _foreign_line(self, draft: _Draft, foreign: DesignForeignKey) -> str:
        local = _column_list(draft, foreign.column_ids)
        if foreign.match != "simple":
            raise _Problem(say("SQLite matches a foreign key simply"), field_name="match")
        if foreign.initially_deferred and not foreign.deferrable:
            raise _Problem(say("Only a deferrable key can be checked at commit"), field_name="initially_deferred")
        for action, where in ((foreign.on_update, "on_update"), (foreign.on_delete, "on_delete")):
            if action == "set_null":
                for column_id in foreign.column_ids:
                    column = draft.columns.get(column_id)
                    if column is not None and column.not_null:
                        raise _Problem(
                            say('"{name}" must have a value, so it cannot be set to null', name=column.name),
                            field_name=where,
                        )
        if len(foreign.column_ids) != len(foreign.target_columns):
            raise _Problem(say("A foreign key names as many columns as it points at"), field_name="target_columns")
        schema, target_name = ids.parse(foreign.target_node_id)
        if target_name == draft.definition.name and schema == SCHEMA:
            # A key to the table itself names columns this definition makes.
            names = {column.name for column in draft.definition.columns}
            if not set(foreign.target_columns) <= names:
                raise _Problem(say("That names a column which is not there"), field_name="target_columns")
        else:
            try:
                target = await self._relation.facts(foreign.target_node_id)
            except ValueError as exc:
                raise _Problem(str(exc), field_name="target_node_id") from None
            except NodeNotFound:
                raise _Problem(say("That table is not there"), field_name="target_node_id") from None
            if not any(
                key.kind in ("PRIMARY KEY", "UNIQUE") and key.columns == list(foreign.target_columns)
                for key in target.keys
            ):
                raise _Problem(
                    say('"{name}" has no unique key over exactly those columns', name=target.name),
                    field_name="target_columns",
                )
            target_name = target.name
        name = _derive(draft, foreign.name, [_column_name(draft, column) for column in foreign.column_ids], "fkey")
        line = (
            f"CONSTRAINT {quoted_name(name)} FOREIGN KEY ({local}) "
            f"REFERENCES {quoted_name(target_name or '')} "
            f"({', '.join(quoted_name(column) for column in foreign.target_columns)})"
        )
        if foreign.on_update != "no_action":
            line += f" ON UPDATE {_REF_ACTIONS[foreign.on_update]}"
        if foreign.on_delete != "no_action":
            line += f" ON DELETE {_REF_ACTIONS[foreign.on_delete]}"
        if foreign.deferrable:
            line += " DEFERRABLE INITIALLY " + ("DEFERRED" if foreign.initially_deferred else "IMMEDIATE")
        return line


def _check_name(draft: _Draft, name: str, object_id: str | None) -> None:
    if name == "" or name != name.strip() or len(name) > NAME_LIMIT:
        draft.problems.append(
            PlanProblem(
                object_id=object_id,
                field="name",
                message=say(
                    "A SQLite name is 1 to {limit} characters and does not start or end with spaces",
                    limit=NAME_LIMIT,
                ),
            )
        )
    elif name.lower().startswith("sqlite_"):
        draft.problems.append(
            PlanProblem(object_id=object_id, field="name", message=say('A name starting "sqlite_" is SQLite\'s own'))
        )


def _check_column_names(draft: _Draft) -> None:
    seen: set[str] = set()
    for column in draft.definition.columns:
        _check_name(draft, column.name, column.id)
        # Column names are compared without case in SQLite.
        if column.name.lower() in seen:
            draft.problems.append(
                PlanProblem(
                    object_id=column.id,
                    field="name",
                    message=say('Two columns cannot both be called "{name}"', name=column.name),
                )
            )
        seen.add(column.name.lower())


def _column_name(draft: _Draft, column_id: str) -> str:
    column = draft.columns.get(column_id)
    if column is None:
        raise _Problem(say("That names a column which is not there"))
    return column.name


def _column_list(draft: _Draft, column_ids: Sequence[str]) -> str:
    if len(set(column_ids)) != len(column_ids):
        raise _Problem(say("A column may appear in a key only once"))
    return ", ".join(quoted_name(_column_name(draft, column_id)) for column_id in column_ids)


def _identity(draft: _Draft) -> DesignColumn | None:
    """The table's identity column: its rowid, under the column's name.

    SQLite numbers rows itself, and an `INTEGER PRIMARY KEY` is that number.
    So an identity is an integer that is the whole primary key, written
    inline with AUTOINCREMENT so a number is never given twice.
    """
    identities = [column for column in draft.definition.columns if isinstance(column.generation, IdentityGeneration)]
    if not identities:
        return None
    if len(identities) > 1:
        draft.problems.append(
            PlanProblem(
                object_id=identities[1].id,
                field="generation",
                message=say("A SQLite table has at most one identity column, its rowid"),
            )
        )
    column = identities[0]
    key = draft.definition.primary_key
    if key is None or key.column_ids != [column.id]:
        draft.problems.append(
            PlanProblem(
                object_id=column.id,
                field="generation",
                message=say("An identity column is SQLite's rowid, so it is the whole primary key"),
            )
        )
    if column.type.code != "integer":
        draft.problems.append(
            PlanProblem(
                object_id=column.id,
                field="generation",
                message=say("Only an integer column can be an identity column"),
            )
        )
    generation = column.generation
    if isinstance(generation, IdentityGeneration):
        if generation.generated == "always":
            draft.problems.append(
                PlanProblem(
                    object_id=column.id,
                    field="generation",
                    message=say("SQLite takes a value written into its rowid; it cannot be ALWAYS"),
                )
            )
        if generation.increment not in (None, 1):
            draft.problems.append(
                PlanProblem(
                    object_id=column.id,
                    field="generation",
                    message=say("SQLite counts its rowid one at a time"),
                )
            )
    return column


def _identity_start(identity: DesignColumn | None) -> int | None:
    if identity is None or not isinstance(identity.generation, IdentityGeneration):
        return None
    start = identity.generation.start
    return None if start in (None, 1) else start


def _column_lines(draft: _Draft, identity: DesignColumn | None) -> list[str]:
    lines: list[str] = []
    for column in draft.definition.columns:
        try:
            lines.append(_column_line(draft, column, identity))
        except _Problem as problem:
            draft.note(problem, column.id)
    return lines


def _column_line(draft: _Draft, column: DesignColumn, identity: DesignColumn | None) -> str:
    known = DESIGN_TYPES.get(column.type.code)
    sql = type_sql(column.type)
    line = f"{quoted_name(column.name)} {sql}"
    if column is identity:
        return line + " PRIMARY KEY AUTOINCREMENT"
    if column.collation is not None:
        if known is None or known.option.category != "text":
            raise _Problem(say("Only a text column has a collation"), field_name="collation")
        if column.collation not in COLLATIONS:
            raise _Problem(
                say('SQLite has no collation "{collation}"', collation=column.collation),
                field_name="collation",
            )
        line += f" COLLATE {column.collation}"
    generation = column.generation
    if column.not_null:
        line += " NOT NULL"
    match generation:
        case LiteralDefault(value=value):
            line += f" DEFAULT {default_literal(value, build_column_type(sql))}"
        case ExpressionDefault(expression=expression):
            line += f" DEFAULT ({_expression(draft, expression, 'default')})"
        case StoredGeneration(expression=expression):
            if column.id in referenced_columns(expression):
                raise _Problem(say("A generated column cannot be computed from itself"), field_name="generation")
            line += f" GENERATED ALWAYS AS ({_expression(draft, expression, 'generated')}) STORED"
        case IdentityGeneration() | NoGeneration():
            pass
    return line


def _key_lines(draft: _Draft, identity: DesignColumn | None) -> list[str]:
    definition = draft.definition
    lines: list[str] = []
    key = definition.primary_key
    if key is not None and not (identity is not None and key.column_ids == [identity.id]):
        try:
            for column_id in key.column_ids:
                column = draft.columns.get(column_id)
                # SQLite lets a primary key of a rowid table hold NULL, an old
                # quirk it keeps; a key promised here holds a value.
                if column is not None and not column.not_null:
                    raise _Problem(
                        say('"{name}" is part of the primary key, so it must have a value', name=column.name),
                        field_name="not_null",
                        object_id=column.id,
                    )
            columns = _column_list(draft, key.column_ids)
            head = f"CONSTRAINT {quoted_name(key.name)} " if key.name else ""
            lines.append(f"{head}PRIMARY KEY ({columns})")
        except _Problem as problem:
            draft.note(problem, None)
    for unique in definition.unique_constraints:
        try:
            if unique.nulls_not_distinct:
                raise _Problem(
                    say("SQLite always treats nulls as different in a unique key"), field_name="nulls_not_distinct"
                )
            if unique.deferrable or unique.initially_deferred:
                raise _Problem(say("SQLite checks a unique key at once; it cannot be deferred"), field_name="deferrable")
            columns = _column_list(draft, unique.column_ids)
            name = _derive(draft, unique.name, [_column_name(draft, column) for column in unique.column_ids], "key")
            lines.append(f"CONSTRAINT {quoted_name(name)} UNIQUE ({columns})")
        except _Problem as problem:
            draft.note(problem, unique.id)
    for check in definition.checks:
        try:
            body = _expression(draft, check.expression, "check")
            name = _derive(draft, check.name, [], "check")
            lines.append(f"CONSTRAINT {quoted_name(name)} CHECK ({body})")
        except _Problem as problem:
            draft.note(problem, check.id)
    return lines


def _index_statements(draft: _Draft) -> list[PlannedStatement]:
    statements: list[PlannedStatement] = []
    for index in draft.definition.indexes:
        try:
            statements.append(_index_statement(draft, index))
        except _Problem as problem:
            draft.note(problem, index.id)
    return statements


def _index_statement(draft: _Draft, index: DesignIndex) -> PlannedStatement:
    if index.method != "btree":
        raise _Problem(say('Unknown index method "{method}"', method=index.method), field_name="method")
    if index.include_column_ids:
        raise _Problem(say("SQLite cannot carry extra columns in an index"), field_name="include_column_ids")
    parts: list[str] = []
    for key in index.keys:
        if key.nulls is not None:
            raise _Problem(say("SQLite puts nulls first in an index and cannot be told otherwise"), field_name="nulls")
        if key.operator_class is not None:
            raise _Problem(say("SQLite has no operator classes"), field_name="operator_class")
        if isinstance(key, IndexColumnKey):
            part = quoted_name(_column_name(draft, key.column_id))
        else:
            part = f"({_expression(draft, key.expression, 'index')})"
        if key.direction == "desc":
            part += " DESC"
        parts.append(part)
    name = _derive(
        draft,
        index.name,
        [_column_name(draft, key.column_id) for key in index.keys if isinstance(key, IndexColumnKey)],
        "idx",
    )
    sql = (
        f"CREATE {'UNIQUE ' if index.unique else ''}INDEX {quoted_name(SCHEMA, name)} "
        f"ON {quoted_name(draft.definition.name)} ({', '.join(parts)})"
    )
    if index.predicate is not None:
        sql += f" WHERE {_expression(draft, index.predicate, 'index')}"
    return PlannedStatement(title=say("Index {name}", name=name), sql=sql)


def _expression(draft: _Draft, node: Expression, context: ExpressionContext) -> str:
    oversized = too_large(node)
    if oversized is not None:
        raise _Problem(oversized, field_name="expression")
    return _composed(draft, node, context)


def _composed(draft: _Draft, node: Expression, context: ExpressionContext) -> str:
    match node:
        case LiteralValue():
            return _literal(node)
        case ColumnReference():
            if context == "default":
                raise _Problem(say("A default cannot read a column of the row being written"), field_name="expression")
            return quoted_name(_column_name(draft, node.column_id))
        case FunctionCall():
            known = DESIGN_FUNCTIONS.get(node.function)
            if known is None:
                raise _Problem(say('Unknown function "{function}"', function=node.function), field_name="expression")
            if context not in known.option.contexts:
                raise _Problem(
                    say("{title} cannot be used there", title=say(known.option.title)), field_name="expression"
                )
            if len(node.arguments) != known.option.arity:
                raise _Problem(
                    say(
                        "{signature} takes {arity} arguments",
                        signature=known.option.signature,
                        arity=known.option.arity,
                    ),
                    field_name="expression",
                )
            if known.bare:
                return known.fragment
            return f"{known.fragment}({', '.join(_composed(draft, argument, context) for argument in node.arguments)})"
        case Comparison():
            return f"({_composed(draft, node.left, context)} {_COMPARE[node.operator]} {_composed(draft, node.right, context)})"
        case Arithmetic():
            return f"({_composed(draft, node.left, context)} {_ARITHMETIC[node.operator]} {_composed(draft, node.right, context)})"
        case BooleanGroup():
            joiner = " AND " if node.operator == "and" else " OR "
            return "(" + joiner.join(_composed(draft, term, context) for term in node.terms) + ")"
        case Negation():
            return f"(NOT {_composed(draft, node.operand, context)})"
        case NullTest():
            test = "IS NOT NULL" if node.negated else "IS NULL"
            return f"({_composed(draft, node.operand, context)} {test})"
        case Membership():
            values = ", ".join(_literal(value) for value in node.values)
            keyword = "NOT IN" if node.negated else "IN"
            return f"({_composed(draft, node.operand, context)} {keyword} ({values}))"
        case Cast():
            return _cast(draft, node, context)


# What a published type is cast to: one of SQLite's five storage classes.
_CAST_BY_CODE = {"integer": "INTEGER", "boolean": "INTEGER", "real": "REAL", "blob": "BLOB"}
_CAST_TARGETS = {"number": "NUMERIC", "text": "TEXT", "temporal": "TEXT", "document": "TEXT"}


def _cast(draft: _Draft, node: Cast, context: ExpressionContext) -> str:
    known = DESIGN_TYPES.get(node.type_code)
    if known is None:
        raise _Problem(say('Unknown type "{type_code}"', type_code=node.type_code), field_name="expression")
    target = _CAST_BY_CODE.get(node.type_code) or _CAST_TARGETS.get(known.option.category, "BLOB")
    return f"CAST({_composed(draft, node.operand, context)} AS {target})"


def _literal(node: LiteralValue) -> str:
    match node.value_kind:
        case "null":
            return "NULL"
        case "boolean":
            if node.text not in ("true", "false"):
                raise _Problem(say("A boolean is true or false"), field_name="expression")
            return "1" if node.text == "true" else "0"
        case "number":
            try:
                return str(Decimal(node.text))
            except (InvalidOperation, ValueError):
                raise _Problem(say('"{text}" is not a number', text=node.text), field_name="expression") from None
        case "json":
            try:
                json.loads(node.text)
            except ValueError:
                raise _Problem(say("That is not a JSON document"), field_name="expression") from None
            return literal(node.text)
        case "text":
            return literal(node.text)


def _derive(draft: _Draft, given: str, parts: Iterable[str], suffix: str) -> str:
    """The name typed, or one composed from the table and the columns.

    A name typed and taken is a refusal; a composed one is numbered until it
    is free, as PostgreSQL's are. Names are compared without case, as SQLite
    compares them.
    """
    if given:
        if len(given) > NAME_LIMIT or given != given.strip():
            raise _Problem(
                say(
                    "A SQLite name is 1 to {limit} characters and does not start or end with spaces",
                    limit=NAME_LIMIT,
                ),
                field_name="name",
            )
        if given.lower() in draft.taken:
            raise _Problem(
                say('Something called "{given}" is already there', given=given), field_name="name", kind="conflict"
            )
        if given.lower() in draft.used:
            raise _Problem(say('This definition already calls something "{given}"', given=given), field_name="name")
        draft.used.add(given.lower())
        return given
    stem = "_".join([draft.definition.name, *parts, suffix])
    at = 1
    while True:
        tail = "" if at == 1 else f"_{at}"
        candidate = stem[: NAME_LIMIT - len(tail)] + tail
        if candidate.lower() not in draft.taken and candidate.lower() not in draft.used:
            draft.used.add(candidate.lower())
            return candidate
        at += 1


def _fingerprint(node_id: str, statements: Sequence[PlannedStatement]) -> str:
    body = json.dumps(
        {"node": node_id, "statements": [item.sql for item in statements]},
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()
