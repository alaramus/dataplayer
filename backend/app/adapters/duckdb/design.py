"""Planning and creating one designed DuckDB table (D117, D397).

The plan a person reviews and the statements that run come from one composer,
as PostgreSQL's do: a sequence for an identity, the `CREATE TABLE`, one
`CREATE INDEX` per index, then comments, run in one transaction, since
DuckDB's structure changes are transactional (D393).

What DuckDB does not have is a problem next to the object that asks for it —
an unlogged or partitioned table, a cascading or deferrable key, INCLUDE,
operator classes, a partial index, an identity that is ALWAYS — rather than a
statement refused after the person has reviewed it.
"""

import hashlib
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Literal

import duckdb

from app.adapters import database_ids as ids
from app.adapters.catalog import CatalogNode, SchemaNode
from app.adapters.duckdb.catalog import DuckdbCatalog
from app.adapters.duckdb.columns import literal
from app.adapters.duckdb.keys import TAKEN
from app.adapters.duckdb.relation import DuckdbRelation
from app.adapters.duckdb.session import DuckdbSession, Reading
from app.adapters.duckdb.sql import quoted_name
from app.adapters.duckdb.structure import restructure
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
from app.adapters.relation import IndexMethodOption
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

# DuckDB sets no limit on a name; this keeps one readable on every screen.
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
            array_supported=True,
            identity_supported=identity,
            category=category,
        ),
        base=base,
    )


# DuckDB's own types. Codes shared with the add-a-column vocabulary (D396)
# mean the same type.
DESIGN_TYPES: dict[str, _Type] = {
    item.option.code: item
    for item in (
        _type("text", N_("Text"), "VARCHAR", "VARCHAR", category="text"),
        _type("smallint", N_("Small integer"), "SMALLINT", "SMALLINT", identity=True, category="number"),
        _type("integer", N_("Integer"), "INTEGER", "INTEGER", identity=True, category="number"),
        _type("bigint", N_("Big integer"), "BIGINT", "BIGINT", identity=True, category="number"),
        _type("hugeint", N_("128-bit integer"), "HUGEINT", "HUGEINT", category="number"),
        _type("double", N_("Floating point"), "DOUBLE", "DOUBLE", category="number"),
        _type(
            "decimal",
            N_("Decimal"),
            "DECIMAL(p,s)",
            "DECIMAL",
            parameters=["precision", "scale"],
            category="number",
        ),
        _type("boolean", N_("Boolean"), "BOOLEAN", "BOOLEAN", category="boolean"),
        _type("date", N_("Date"), "DATE", "DATE", category="temporal"),
        _type("time", N_("Time"), "TIME", "TIME", category="temporal"),
        _type("timestamp", N_("Date and time"), "TIMESTAMP", "TIMESTAMP", category="temporal"),
        _type(
            "timestamptz",
            N_("Date and time with time zone"),
            "TIMESTAMP WITH TIME ZONE",
            "TIMESTAMP WITH TIME ZONE",
            category="temporal",
        ),
        _type("interval", N_("Interval"), "INTERVAL", "INTERVAL", category="temporal"),
        _type("uuid", N_("UUID"), "UUID", "UUID", category="text"),
        _type("json", N_("JSON"), "JSON", "JSON", category="document"),
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


# The clock is for a default: a generated column, a check or an index is
# computed again whenever DuckDB reads it.
DESIGN_FUNCTIONS: dict[str, _Function] = {
    item.option.code: item
    for item in (
        _function("now", N_("Now"), "CURRENT_TIMESTAMP", "CURRENT_TIMESTAMP", 0, _DEFAULT_ONLY, bare=True),
        _function("current_date", N_("Today"), "CURRENT_DATE", "CURRENT_DATE", 0, _DEFAULT_ONLY, bare=True),
        _function("uuid", N_("New UUID"), "uuid()", "uuid", 0, _DEFAULT_ONLY),
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

# DuckDB refuses CASCADE, SET NULL and SET DEFAULT on a foreign key.
REFERENCE_ACTION_CHOICES = [
    DesignChoice(code="no_action", title=N_("No action")),
    DesignChoice(code="restrict", title=N_("Restrict")),
]
MATCH_CHOICES = [DesignChoice(code="simple", title=N_("Match simple"))]
PERSISTENCE_CHOICES = [DesignChoice(code="permanent", title=N_("Permanent"))]

DESIGN_INDEX_METHODS = [
    IndexMethodOption(code="art", title=N_("Adaptive radix tree"), sql="", unique_supported=True, multi_column_supported=True),
]

# The collations DuckDB builds in.
COLLATIONS = ["NOCASE", "NOACCENT", "NFC"]


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
    schema: str
    definition: TableDefinition
    columns: dict[str, DesignColumn]
    taken: set[str]
    used: set[str] = field(default_factory=set)
    problems: list[PlanProblem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # A literal default and the type it must read as, tried while planning.
    defaults: list[tuple[str, str, str]] = field(default_factory=list)

    def note(self, problem: _Problem, object_id: str | None) -> None:
        self.problems.append(
            PlanProblem(
                object_id=problem.object_id or object_id,
                field=problem.field_name,
                message=problem.message,
                kind=problem.kind,
            )
        )


def _sql_literal(text: str) -> str:
    try:
        return literal(text)
    except ValueError as exc:
        raise _Problem(str(exc), field_name="expression") from None


def type_sql(chosen: DesignColumnType) -> str:
    known = DESIGN_TYPES.get(chosen.code)
    if known is None:
        raise _Problem(say('Unknown column type "{code}"', code=chosen.code), field_name="type")
    takes = known.option.parameters
    title = say(known.option.title)
    if chosen.length is not None:
        raise _Problem(say("{title} takes no length", title=title), field_name="type")
    if chosen.precision is not None and "precision" not in takes:
        raise _Problem(say("{title} takes no precision", title=title), field_name="type")
    if chosen.scale is not None and "scale" not in takes:
        raise _Problem(say("{title} takes no scale", title=title), field_name="type")
    if chosen.scale is not None and chosen.precision is None:
        raise _Problem(say("{title} needs a precision before a scale", title=title), field_name="type")
    if chosen.precision is not None and not 1 <= chosen.precision <= 38:
        raise _Problem(say("A decimal's precision is 1 to 38"), field_name="type")
    if chosen.precision is not None and chosen.scale is not None and chosen.scale > chosen.precision:
        raise _Problem(say("A scale cannot exceed its precision"), field_name="type")
    base = known.base
    if chosen.precision is not None:
        base = f"{known.base}({chosen.precision},{chosen.scale or 0})"
    return base + "[]" * chosen.dimensions


class DuckdbTableDesign:
    """The three questions a designed table asks of one DuckDB file."""

    def __init__(self, session: DuckdbSession, catalog: DuckdbCatalog, relation: DuckdbRelation) -> None:
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
                index_direction=True,
                index_nulls_order=True,
                comments=True,
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

        def work(connection: duckdb.DuckDBPyConnection) -> None:
            for statement in plan.statements:
                connection.execute(statement.sql)

        # One transaction: the table and everything with it arrive together.
        await restructure(self._session, work)
        schema, _ = ids.parse(node_id)
        return (await self._catalog.path_to(ids.relation_id(schema, definition.name)))[-1]

    async def _draft(self, node_id: str, definition: TableDefinition) -> _Draft:
        node, reason = await self._destination(node_id)
        if node is None:
            raise ValueError(reason)
        schema = node.name

        def read(reading: Reading) -> set[str]:
            return {str(row[0]) for row in reading.tuples(TAKEN, [schema] * 4)}

        return _Draft(
            schema=schema,
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
            draft.problems.append(PlanProblem(field="persistence", message=say("DuckDB has no unlogged tables")))
        if definition.partition is not None:
            draft.problems.append(PlanProblem(field="partition", message=say("DuckDB has no partitioned tables")))
        if definition.engine is not None:
            draft.problems.append(PlanProblem(field="engine", message=say("DuckDB keeps every table one way")))
        if definition.hypertable is not None:
            draft.problems.append(
                PlanProblem(field="hypertable", message=say("A hypertable is TimescaleDB's, not DuckDB's"))
            )
        _check_column_names(draft)
        sequences = _identities(draft)
        lines = _column_lines(draft, sequences)
        lines += _key_lines(draft)
        lines += await self._foreign_lines(draft)
        indexes = _index_statements(draft)
        await self._try_defaults(draft)
        if draft.problems:
            return []
        table = quoted_name(draft.schema, definition.name)
        statements = [
            PlannedStatement(
                title=say("Sequence {name}", name=name),
                sql=f"CREATE SEQUENCE {quoted_name(draft.schema, name)} START {start} INCREMENT BY {step}",
            )
            for name, start, step in sequences.values()
        ]
        statements.append(
            PlannedStatement(
                title=say("Table {name}", name=definition.name),
                sql=f"CREATE TABLE {table} (\n    " + ",\n    ".join(lines) + "\n)",
            )
        )
        statements += indexes
        try:
            statements += _comments(draft, table)
        except _Problem as problem:
            draft.note(problem, None)
            return []
        return statements

    async def _try_defaults(self, draft: _Draft) -> None:
        """Every literal default read as its column's type, as DuckDB will at
        an insert: DuckDB stores one it cannot read and fails only then."""
        if not draft.defaults:
            return
        tried = draft.defaults

        def read(reading: Reading) -> list[bool]:
            # Each a literal quoted here and a type of DESIGN_TYPES.
            return [
                bool(reading.value("SELECT TRY_CAST(" + text + " AS " + sql + ") IS NULL"))  # noqa: S608
                for _, text, sql in tried
            ]

        for (column_id, _, sql), failed in zip(tried, await self._session.inspection(read), strict=True):
            if failed:
                draft.problems.append(
                    PlanProblem(
                        object_id=column_id,
                        field="generation",
                        message=say("That value cannot be read as {sql}", sql=sql),
                    )
                )

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
            raise _Problem(say("DuckDB matches a foreign key simply"), field_name="match")
        if foreign.deferrable or foreign.initially_deferred:
            raise _Problem(say("DuckDB checks a foreign key at once; it cannot be deferred"), field_name="deferrable")
        for action, where in ((foreign.on_update, "on_update"), (foreign.on_delete, "on_delete")):
            if action not in ("no_action", "restrict"):
                raise _Problem(
                    say("DuckDB refuses a foreign key that cascades, sets null or sets a default"),
                    field_name=where,
                )
        if len(foreign.column_ids) != len(foreign.target_columns):
            raise _Problem(say("A foreign key names as many columns as it points at"), field_name="target_columns")
        schema, target_name = ids.parse(foreign.target_node_id)
        if schema != draft.schema:
            raise _Problem(
                say("DuckDB keeps a foreign key within one schema"), field_name="target_node_id"
            )
        if target_name == draft.definition.name:
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
        if foreign.name:
            draft.warnings.append(_named_warning())
        line = (
            f"FOREIGN KEY ({local}) "
            f"REFERENCES {quoted_name(draft.schema, target_name or '')} "
            f"({', '.join(quoted_name(column) for column in foreign.target_columns)})"
        )
        if foreign.on_update == "restrict":
            line += " ON UPDATE RESTRICT"
        if foreign.on_delete == "restrict":
            line += " ON DELETE RESTRICT"
        return line


def _comments(draft: _Draft, table: str) -> list[PlannedStatement]:
    """The table's and its columns' comments, which DuckDB keeps (D397)."""
    definition = draft.definition
    statements: list[PlannedStatement] = []
    if definition.comment:
        statements.append(
            PlannedStatement(
                title=say("Comment on {name}", name=definition.name),
                sql=f"COMMENT ON TABLE {table} IS {_sql_literal(definition.comment)}",
            )
        )
    for column in definition.columns:
        if column.comment:
            statements.append(
                PlannedStatement(
                    title=say("Comment on {name}", name=column.name),
                    sql=(
                        f"COMMENT ON COLUMN {table}.{quoted_name(column.name)} "
                        f"IS {_sql_literal(column.comment)}"
                    ),
                )
            )
    return statements


def _named_warning() -> str:
    return say("DuckDB names constraints itself; the names given are not kept")


def _check_name(draft: _Draft, name: str, object_id: str | None) -> None:
    if name == "" or name != name.strip() or len(name) > NAME_LIMIT:
        draft.problems.append(
            PlanProblem(
                object_id=object_id,
                field="name",
                message=say(
                    "A DuckDB name is 1 to {limit} characters and does not start or end with spaces",
                    limit=NAME_LIMIT,
                ),
            )
        )


def _check_column_names(draft: _Draft) -> None:
    seen: set[str] = set()
    for column in draft.definition.columns:
        _check_name(draft, column.name, column.id)
        # Column names are compared without case in DuckDB.
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


def _identities(draft: _Draft) -> dict[str, tuple[str, int, int]]:
    """Each identity column's sequence: its name, start and step, by column id.

    DuckDB has no identity columns; a sequence of the column's own, read by
    its default, counts instead (D397).
    """
    found: dict[str, tuple[str, int, int]] = {}
    for column in draft.definition.columns:
        generation = column.generation
        if not isinstance(generation, IdentityGeneration):
            continue
        known = DESIGN_TYPES.get(column.type.code)
        if known is None or not known.option.identity_supported or column.type.dimensions:
            draft.problems.append(
                PlanProblem(
                    object_id=column.id,
                    field="generation",
                    message=say("Only an integer column can be an identity column"),
                )
            )
            continue
        if generation.generated == "always":
            draft.problems.append(
                PlanProblem(
                    object_id=column.id,
                    field="generation",
                    message=say("DuckDB takes a value written into an identity column; it cannot be ALWAYS"),
                )
            )
            continue
        step = generation.increment if generation.increment is not None else 1
        if step == 0:
            draft.problems.append(
                PlanProblem(object_id=column.id, field="generation", message=say("A sequence cannot step by zero"))
            )
            continue
        start = generation.start if generation.start is not None else 1
        name = _derive(draft, "", [draft.definition.name, column.name], "seq", table=False)
        found[column.id] = (name, start, step)
    return found


def _column_lines(draft: _Draft, sequences: dict[str, tuple[str, int, int]]) -> list[str]:
    lines: list[str] = []
    for column in draft.definition.columns:
        try:
            lines.append(_column_line(draft, column, sequences))
        except _Problem as problem:
            draft.note(problem, column.id)
    return lines


def _column_line(draft: _Draft, column: DesignColumn, sequences: dict[str, tuple[str, int, int]]) -> str:
    known = DESIGN_TYPES.get(column.type.code)
    sql = type_sql(column.type)
    line = f"{quoted_name(column.name)} {sql}"
    if column.collation is not None:
        if known is None or known.option.category != "text" or column.type.dimensions:
            raise _Problem(say("Only a text column has a collation"), field_name="collation")
        if column.collation.upper() not in COLLATIONS:
            raise _Problem(
                say('DuckDB has no collation "{collation}"', collation=column.collation),
                field_name="collation",
            )
        line += f" COLLATE {column.collation.upper()}"
    if column.not_null:
        line += " NOT NULL"
    generation = column.generation
    match generation:
        case LiteralDefault(value=value):
            text = _sql_literal(value)
            draft.defaults.append((column.id, text, sql))
            line += f" DEFAULT CAST({text} AS {sql})"
        case ExpressionDefault(expression=expression):
            line += f" DEFAULT ({_expression(draft, expression, 'default')})"
        case StoredGeneration(expression=expression):
            if column.id in referenced_columns(expression):
                raise _Problem(say("A generated column cannot be computed from itself"), field_name="generation")
            if column.not_null:
                raise _Problem(say("A generated column is computed, so it cannot be required"), field_name="not_null")
            draft.warnings.append(
                say("DuckDB computes a generated column whenever it is read; it is not stored")
            )
            line += f" GENERATED ALWAYS AS ({_expression(draft, expression, 'generated')}) VIRTUAL"
        case IdentityGeneration():
            sequence = sequences.get(column.id)
            if sequence is not None:
                line += f" DEFAULT nextval({_sql_literal(draft.schema + '.' + sequence[0])})"
        case NoGeneration():
            pass
    return line


def _key_lines(draft: _Draft) -> list[str]:
    definition = draft.definition
    lines: list[str] = []
    key = definition.primary_key
    if key is not None:
        try:
            for column_id in key.column_ids:
                column = draft.columns.get(column_id)
                if column is not None and not column.not_null:
                    raise _Problem(
                        say('"{name}" is part of the primary key, so it must have a value', name=column.name),
                        field_name="not_null",
                        object_id=column.id,
                    )
            lines.append(f"PRIMARY KEY ({_column_list(draft, key.column_ids)})")
            if key.name:
                draft.warnings.append(_named_warning())
        except _Problem as problem:
            draft.note(problem, None)
    for unique in definition.unique_constraints:
        try:
            if unique.nulls_not_distinct:
                raise _Problem(
                    say("DuckDB always treats nulls as different in a unique key"), field_name="nulls_not_distinct"
                )
            if unique.deferrable or unique.initially_deferred:
                raise _Problem(say("DuckDB checks a unique key at once; it cannot be deferred"), field_name="deferrable")
            lines.append(f"UNIQUE ({_column_list(draft, unique.column_ids)})")
            if unique.name:
                draft.warnings.append(_named_warning())
        except _Problem as problem:
            draft.note(problem, unique.id)
    for check in definition.checks:
        try:
            lines.append(f"CHECK ({_expression(draft, check.expression, 'check')})")
            if check.name:
                draft.warnings.append(_named_warning())
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
    if index.method != "art":
        raise _Problem(say('Unknown index method "{method}"', method=index.method), field_name="method")
    if index.include_column_ids:
        raise _Problem(say("DuckDB cannot carry extra columns in an index"), field_name="include_column_ids")
    if index.predicate is not None:
        raise _Problem(say("DuckDB cannot index part of the rows"), field_name="predicate")
    parts: list[str] = []
    for key in index.keys:
        if key.operator_class is not None:
            raise _Problem(say("DuckDB has no operator classes"), field_name="operator_class")
        if isinstance(key, IndexColumnKey):
            part = quoted_name(_column_name(draft, key.column_id))
        else:
            part = f"({_expression(draft, key.expression, 'index')})"
        if key.direction == "desc":
            part += " DESC"
        if key.nulls is not None:
            part += " NULLS FIRST" if key.nulls == "first" else " NULLS LAST"
        parts.append(part)
    name = _derive(
        draft,
        index.name,
        [_column_name(draft, key.column_id) for key in index.keys if isinstance(key, IndexColumnKey)],
        "idx",
    )
    sql = (
        f"CREATE {'UNIQUE ' if index.unique else ''}INDEX {quoted_name(name)} "
        f"ON {quoted_name(draft.schema, draft.definition.name)} ({', '.join(parts)})"
    )
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
            target = DESIGN_TYPES.get(node.type_code)
            if target is None:
                raise _Problem(say('Unknown type "{type_code}"', type_code=node.type_code), field_name="expression")
            return f"CAST({_composed(draft, node.operand, context)} AS {target.base})"


def _literal(node: LiteralValue) -> str:
    match node.value_kind:
        case "null":
            return "NULL"
        case "boolean":
            if node.text not in ("true", "false"):
                raise _Problem(say("A boolean is true or false"), field_name="expression")
            return node.text.upper()
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
            return _sql_literal(node.text)
        case "text":
            return _sql_literal(node.text)


def _derive(draft: _Draft, given: str, parts: Iterable[str], suffix: str, *, table: bool = True) -> str:
    """The name typed, or one composed from the table and the columns.

    A name typed and taken is a refusal; a composed one is numbered until it
    is free, as PostgreSQL's are. Names are compared without case, as DuckDB
    compares them.
    """
    if given:
        if len(given) > NAME_LIMIT or given != given.strip():
            raise _Problem(
                say(
                    "A DuckDB name is 1 to {limit} characters and does not start or end with spaces",
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
    stem = "_".join([*([draft.definition.name] if table else []), *parts, suffix])
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
