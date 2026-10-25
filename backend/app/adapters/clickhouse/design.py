"""Planning and creating one designed ClickHouse table (D117, D274).

The plan a person reviews and the statement that runs come from one composer,
as PostgreSQL's and MySQL's do, and the plan is one `CREATE TABLE … ENGINE =
MergeTree`: ClickHouse has no transaction to make several statements one.

What ClickHouse has not got is a problem next to the object that asks for it
rather than a statement the server refuses after the review: a unique key, a
foreign key, an identity, a collation, a partial index, a partition by range
or list. The primary key is the sorting key, which orders and finds rows and
never refuses one (D269); the plan says so.
"""

import hashlib
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Literal

from app.adapters.catalog import CatalogNode, SchemaNode
from app.adapters.clickhouse.catalog import ClickhouseCatalog
from app.adapters.clickhouse.columns import ALTERING
from app.adapters.clickhouse.session import ClickhouseSession, quoted_name
from app.adapters.clickhouse.sql import text_literal
from app.adapters.clickhouse.vocabulary import CLICKHOUSE_INDEX_METHODS
from app.adapters.database_ids import parse, relation_id
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
from app.adapters.table_design import (
    DesignColumn,
    DesignColumnType,
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

# The longest name the designer's own model takes; ClickHouse allows more.
NAME_LIMIT = 63
GRANULARITY = 1


@dataclass(frozen=True)
class _Type:
    option: DesignTypeOption
    base: str
    # Whether `Nullable(…)` may wrap it: an array and JSON cannot be NULL.
    nullable: bool = True


def _type(
    code: str,
    title: str,
    spelling: str,
    base: str,
    *,
    parameters: list[DesignTypeParameter] | None = None,
    category: DesignTypeCategory = "other",
    array: bool = True,
    nullable: bool = True,
) -> _Type:
    return _Type(
        option=DesignTypeOption(
            code=code,
            title=title,
            sql=spelling,
            parameters=parameters or [],
            array_supported=array,
            identity_supported=False,
            category=category,
        ),
        base=base,
        nullable=nullable,
    )


# Codes shared with the add-a-column vocabulary (D27) mean the same type here.
DESIGN_TYPES: dict[str, _Type] = {
    item.option.code: item
    for item in (
        _type("text", N_("Text"), "String", "String", category="text"),
        _type("fixed_text", N_("Text, fixed"), "FixedString(n)", "FixedString", parameters=["length"], category="text"),
        _type(
            "repeated_text",
            N_("Text with few distinct values"),
            "LowCardinality(String)",
            "LowCardinality(String)",
            category="text",
        ),
        _type("int8", N_("Tiny integer"), "Int8", "Int8", category="number"),
        _type("int16", N_("Small integer"), "Int16", "Int16", category="number"),
        _type("int32", N_("Integer"), "Int32", "Int32", category="number"),
        _type("int64", N_("Big integer"), "Int64", "Int64", category="number"),
        _type("uint8", N_("Unsigned tiny integer"), "UInt8", "UInt8", category="number"),
        _type("uint32", N_("Unsigned integer"), "UInt32", "UInt32", category="number"),
        _type("uint64", N_("Unsigned big integer"), "UInt64", "UInt64", category="number"),
        _type(
            "decimal",
            N_("Decimal"),
            "Decimal(p, s)",
            "Decimal",
            parameters=["precision", "scale"],
            category="number",
        ),
        _type("float32", N_("Single precision"), "Float32", "Float32", category="number"),
        _type("float64", N_("Floating point"), "Float64", "Float64", category="number"),
        _type("boolean", N_("Boolean"), "Bool", "Bool", category="boolean"),
        _type("date", N_("Date"), "Date32", "Date32", category="temporal"),
        _type("datetime", N_("Date and time (UTC)"), "DateTime('UTC')", "DateTime('UTC')", category="temporal"),
        _type(
            "datetime64",
            N_("Date and time with fractions (UTC)"),
            "DateTime64(p, 'UTC')",
            "DateTime64",
            parameters=["precision"],
            category="temporal",
        ),
        _type("uuid", N_("UUID"), "UUID", "UUID", category="text"),
        _type("ipv4", N_("IPv4 address"), "IPv4", "IPv4"),
        _type("ipv6", N_("IPv6 address"), "IPv6", "IPv6"),
        _type("json", N_("JSON"), "JSON", "JSON", category="document", array=False, nullable=False),
    )
}


@dataclass(frozen=True)
class _Function:
    option: FunctionOption
    fragment: str


_EVERYWHERE: list[ExpressionContext] = ["default", "generated", "check", "index"]
_COMPUTED: list[ExpressionContext] = ["default", "generated"]


def _function(
    code: str, title: str, signature: str, fragment: str, arity: int, contexts: list[ExpressionContext]
) -> _Function:
    return _Function(
        option=FunctionOption(code=code, title=title, signature=signature, arity=arity, contexts=contexts),
        fragment=fragment,
    )


# The clock and a random UUID fill a default or a computed column; a check or
# an index reads the row and nothing else.
DESIGN_FUNCTIONS: dict[str, _Function] = {
    item.option.code: item
    for item in (
        _function("now", N_("Now"), "now()", "now", 0, _COMPUTED),
        _function("current_date", N_("Today"), "today()", "today", 0, _COMPUTED),
        _function("uuid", N_("Random UUID"), "generateUUIDv4()", "generateUUIDv4", 0, _COMPUTED),
        _function("lower", N_("Lower case"), "lowerUTF8(x)", "lowerUTF8", 1, _EVERYWHERE),
        _function("upper", N_("Upper case"), "upperUTF8(x)", "upperUTF8", 1, _EVERYWHERE),
        _function("trim", N_("Trimmed"), "trimBoth(x)", "trimBoth", 1, _EVERYWHERE),
        _function("length", N_("Length"), "lengthUTF8(x)", "lengthUTF8", 1, _EVERYWHERE),
        _function("abs", N_("Absolute"), "abs(x)", "abs", 1, _EVERYWHERE),
        _function("round", N_("Rounded"), "round(x)", "round", 1, _EVERYWHERE),
        _function("coalesce", N_("First value present"), "coalesce(x, y)", "coalesce", 2, _EVERYWHERE),
    )
}

_COMPARE = {"eq": "=", "ne": "!=", "lt": "<", "lte": "<=", "gt": ">", "gte": ">="}
_ARITHMETIC = {"add": "+", "subtract": "-", "multiply": "*", "divide": "/"}

_TAKEN = "SELECT name FROM system.tables WHERE database = {database:String}"

CREATE_REFUSALS: dict[int, str] = {
    57: N_("Something with that name is already there"),
    15: N_("Two columns cannot have the same name"),
    44: N_("Two indexes of one table cannot share a name"),
    6: N_("A default does not fit the type of its column"),
    53: N_("A default does not fit the type of its column"),
    70: N_("A default does not fit the type of its column"),
    497: N_("This connection may not create a table in that database"),
    62: N_("The composed statement was refused by the server"),
}


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

    def note(self, problem: _Problem, object_id: str | None) -> None:
        self.problems.append(
            PlanProblem(
                object_id=problem.object_id or object_id,
                field=problem.field_name,
                message=problem.message,
                kind=problem.kind,
            )
        )


def type_sql(chosen: DesignColumnType, *, nullable: bool) -> str:
    known = DESIGN_TYPES.get(chosen.code)
    if known is None:
        raise _Problem(say('Unknown column type "{code}"', code=chosen.code), field_name="type")
    takes = known.option.parameters
    title = say(known.option.title)
    if chosen.length is not None and "length" not in takes:
        raise _Problem(say("{title} takes no length", title=title), field_name="type")
    if chosen.precision is not None and "precision" not in takes:
        raise _Problem(say("{title} takes no precision", title=title), field_name="type")
    if chosen.scale is not None and "scale" not in takes:
        raise _Problem(say("{title} takes no scale", title=title), field_name="type")
    if chosen.dimensions and not known.option.array_supported:
        raise _Problem(say("{title} cannot be held in an array", title=title), field_name="type")
    if known.base == "FixedString":
        if chosen.length is None:
            raise _Problem(say("{title} needs a length", title=title), field_name="type")
        sql = f"FixedString({chosen.length})"
    elif known.base == "Decimal":
        precision = 38 if chosen.precision is None else chosen.precision
        scale = chosen.scale or 0
        if precision > 76:
            raise _Problem(say("A ClickHouse decimal has at most 76 digits"), field_name="type")
        if scale > precision:
            raise _Problem(say("A scale cannot exceed its precision"), field_name="type")
        sql = f"Decimal({precision}, {scale})"
    elif known.base == "DateTime64":
        precision = 3 if chosen.precision is None else chosen.precision
        if precision > 9:
            raise _Problem(say("A moment keeps at most nine digits of a second"), field_name="type")
        sql = f"DateTime64({precision}, 'UTC')"
    else:
        sql = known.base
    if chosen.dimensions:
        # An array is never NULL; empty is what it holds instead.
        for _ in range(chosen.dimensions):
            sql = f"Array({sql})"
        return sql
    if not nullable or not known.nullable:
        return sql
    if sql.startswith("LowCardinality("):
        return f"LowCardinality(Nullable({sql[len('LowCardinality(') : -1]}))"
    return f"Nullable({sql})"


class ClickhouseTableDesign:
    """The three questions a designed table asks of one ClickHouse connection."""

    def __init__(self, session: ClickhouseSession, catalog: ClickhouseCatalog) -> None:
        self._session = session
        self._catalog = catalog

    async def _destination(self, node_id: str) -> tuple[SchemaNode | None, str | None]:
        node = (await self._catalog.path_to(node_id))[-1]
        if not isinstance(node, SchemaNode):
            return None, say("A table is created in a database")
        if node.is_system:
            return None, say('"{schema}" belongs to the server', schema=node.name)
        return node, None

    async def table_design_options(self, node_id: str) -> TableDesignOptions:
        node, reason = await self._destination(node_id)
        if node is None:
            return TableDesignOptions(supported=False, reason=reason)
        return TableDesignOptions(
            supported=True,
            schema_label=node.name,
            types=worded_titles(item.option for item in DESIGN_TYPES.values()),
            index_methods=worded_titles(CLICKHOUSE_INDEX_METHODS),
            functions=worded_titles(item.option for item in DESIGN_FUNCTIONS.values()),
            hypertable=HypertableOffer(offered=False),
            limits=DesignLimits(name_bytes=NAME_LIMIT),
        )

    async def plan_table(self, request: TablePlanRequest) -> TablePlan:
        draft = await self._draft(request.node_id, request.definition)
        statements = _statements(draft)
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
        for statement in plan.statements:
            await self._session.command(statement.sql, {}, settings=ALTERING, refusals=CREATE_REFUSALS)
        schema, _ = parse(node_id)
        return (await self._catalog.path_to(relation_id(schema, definition.name)))[-1]

    async def _draft(self, node_id: str, definition: TableDefinition) -> _Draft:
        node, reason = await self._destination(node_id)
        if node is None:
            raise ValueError(reason)
        taken = {str(row["name"]) for row in await self._session.query(_TAKEN, {"database": node.name})}
        return _Draft(
            schema=node.name,
            definition=definition,
            columns={column.id: column for column in definition.columns},
            taken=taken,
        )


def _statements(draft: _Draft) -> list[PlannedStatement]:
    definition = draft.definition
    _check_name(draft, definition.name, None)
    if definition.name in draft.taken:
        draft.problems.append(
            PlanProblem(
                field="name",
                kind="conflict",
                message=say('Something called "{name}" is already in that database', name=definition.name),
            )
        )
    for refused, where in (
        (definition.persistence != "permanent", "persistence"),
        (definition.partition is not None, "partition"),
        (definition.hypertable is not None, "hypertable"),
    ):
        if refused:
            draft.problems.append(PlanProblem(field=where, message=say(_OUTSIDE[where])))
    for unique in definition.unique_constraints:
        draft.problems.append(
            PlanProblem(object_id=unique.id, message=say("ClickHouse has no unique keys"))
        )
    for foreign in definition.foreign_keys:
        draft.problems.append(
            PlanProblem(object_id=foreign.id, message=say("ClickHouse has no foreign keys"))
        )
    _check_column_names(draft)
    lines = _column_lines(draft)
    lines += _index_lines(draft)
    lines += _check_lines(draft)
    order = _order_by(draft)
    if draft.problems:
        return []
    statement = (
        f"CREATE TABLE {quoted_name(draft.schema, definition.name)} (\n    "
        + ",\n    ".join(lines)
        + f"\n)\nENGINE = MergeTree\nORDER BY {order}"
    )
    if definition.comment:
        statement += f"\nCOMMENT {text_literal(definition.comment)}"
    return [PlannedStatement(title=say("Table {name}", name=definition.name), sql=statement)]


_OUTSIDE = {
    "persistence": N_("A ClickHouse table is written to disk; there is no unlogged one"),
    "partition": N_("A ClickHouse table is not partitioned by range, list or hash here"),
    "hypertable": N_("A hypertable is TimescaleDB's, not ClickHouse's"),
}


def _check_name(draft: _Draft, name: str, object_id: str | None) -> None:
    if name == "" or name != name.strip() or len(name) > NAME_LIMIT:
        draft.problems.append(
            PlanProblem(
                object_id=object_id,
                field="name",
                message=say(
                    "A name is 1 to {limit} characters and does not start or end with spaces",
                    limit=NAME_LIMIT,
                ),
            )
        )


def _check_column_names(draft: _Draft) -> None:
    seen: set[str] = set()
    for column in draft.definition.columns:
        _check_name(draft, column.name, column.id)
        # ClickHouse compares column names with case.
        if column.name in seen:
            draft.problems.append(
                PlanProblem(
                    object_id=column.id,
                    field="name",
                    message=say('Two columns cannot both be called "{name}"', name=column.name),
                )
            )
        seen.add(column.name)


def _column_name(draft: _Draft, column_id: str) -> str:
    column = draft.columns.get(column_id)
    if column is None:
        raise _Problem(say("That names a column which is not there"))
    return column.name


def _column_lines(draft: _Draft) -> list[str]:
    lines: list[str] = []
    for column in draft.definition.columns:
        try:
            lines.append(_column_line(draft, column))
        except _Problem as problem:
            draft.note(problem, column.id)
    return lines


def _column_line(draft: _Draft, column: DesignColumn) -> str:
    known = DESIGN_TYPES.get(column.type.code)
    if column.collation is not None:
        raise _Problem(say("ClickHouse compares text by its bytes; it has no collations"), field_name="collation")
    if known is not None and not column.not_null and (column.type.dimensions or not known.nullable):
        draft.warnings.append(
            say('"{name}" cannot hold NULL in ClickHouse, so it will always have a value', name=column.name)
        )
    line = f"{quoted_name(column.name)} {type_sql(column.type, nullable=not column.not_null)}"
    generation = column.generation
    match generation:
        case LiteralDefault(value=value):
            line += f" DEFAULT {text_literal(value)}"
        case ExpressionDefault(expression=expression):
            line += f" DEFAULT {_expression(draft, expression, 'default')}"
        case StoredGeneration(expression=expression):
            if column.id in referenced_columns(expression):
                raise _Problem(say("A generated column cannot be computed from itself"), field_name="generation")
            line += f" MATERIALIZED {_expression(draft, expression, 'generated')}"
        case IdentityGeneration():
            raise _Problem(
                say("ClickHouse has no identity columns; a random UUID or the time can fill a default"),
                field_name="generation",
            )
        case NoGeneration():
            pass
    if column.comment:
        line += f" COMMENT {text_literal(column.comment)}"
    return line


def _order_by(draft: _Draft) -> str:
    """The sorting key, from the primary key: rows kept in its order (D269)."""
    key = draft.definition.primary_key
    if key is None:
        return "tuple()"
    try:
        if len(set(key.column_ids)) != len(key.column_ids):
            raise _Problem(say("A column may appear in a key only once"))
        for column_id in key.column_ids:
            column = draft.columns.get(column_id)
            if column is not None and not column.not_null:
                raise _Problem(
                    say('"{name}" is part of the primary key, so it must have a value', name=column.name),
                    field_name="not_null",
                    object_id=column.id,
                )
        if key.name:
            draft.warnings.append(say("A ClickHouse primary key has no name; the name given is not kept"))
        draft.warnings.append(
            say(
                "ClickHouse keeps rows in the order of the primary key and finds them by it, "
                "but does not stop two rows from sharing it"
            )
        )
        return "(" + ", ".join(quoted_name(_column_name(draft, column_id)) for column_id in key.column_ids) + ")"
    except _Problem as problem:
        draft.note(problem, None)
        return "tuple()"


def _index_lines(draft: _Draft) -> list[str]:
    lines: list[str] = []
    for index in draft.definition.indexes:
        try:
            lines.append(_index_line(draft, index))
        except _Problem as problem:
            draft.note(problem, index.id)
    return lines


def _index_line(draft: _Draft, index: DesignIndex) -> str:
    method = next((item for item in CLICKHOUSE_INDEX_METHODS if item.code == index.method), None)
    if method is None:
        raise _Problem(say('Unknown index method "{method}"', method=index.method), field_name="method")
    if index.unique:
        raise _Problem(say("A ClickHouse index cannot be unique; no key of ClickHouse is"), field_name="unique")
    if index.include_column_ids:
        raise _Problem(say("A ClickHouse index carries no extra columns"), field_name="include_column_ids")
    if index.predicate is not None:
        raise _Problem(say("A ClickHouse index covers every row"), field_name="predicate")
    parts: list[str] = []
    for key in index.keys:
        if key.nulls is not None or key.direction is not None:
            raise _Problem(say("A ClickHouse index has no order of its own"), field_name="direction")
        if key.operator_class is not None:
            raise _Problem(say("ClickHouse has no operator classes"), field_name="operator_class")
        if isinstance(key, IndexColumnKey):
            parts.append(quoted_name(_column_name(draft, key.column_id)))
        else:
            parts.append(_expression(draft, key.expression, "index"))
    name = _derive(
        draft,
        index.name,
        [_column_name(draft, key.column_id) for key in index.keys if isinstance(key, IndexColumnKey)],
        "idx",
    )
    # The method is the vocabulary's own text.
    return f"INDEX {quoted_name(name)} ({', '.join(parts)}) TYPE {method.sql} GRANULARITY {GRANULARITY}"


def _check_lines(draft: _Draft) -> list[str]:
    lines: list[str] = []
    for check in draft.definition.checks:
        try:
            body = _expression(draft, check.expression, "check")
            name = _derive(draft, check.name, [], "chk")
            lines.append(f"CONSTRAINT {quoted_name(name)} CHECK {body}")
        except _Problem as problem:
            draft.note(problem, check.id)
    return lines


def _expression(draft: _Draft, node: Expression, context: ExpressionContext) -> str:
    oversized = too_large(node)
    if oversized is not None:
        raise _Problem(oversized, field_name="expression")
    return _composed(draft, node, context)


# The walk is MySQL's (D236); what each piece is spelt as is ClickHouse's,
# which is why it is not shared.
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
            if target is None or target.option.parameters:
                raise _Problem(say('Unknown type "{type_code}"', type_code=node.type_code), field_name="expression")
            return f"CAST({_composed(draft, node.operand, context)} AS {target.base})"


def _literal(node: LiteralValue) -> str:
    match node.value_kind:
        case "null":
            return "NULL"
        case "boolean":
            if node.text not in ("true", "false"):
                raise _Problem(say("A boolean is true or false"), field_name="expression")
            return node.text
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
            return text_literal(node.text)
        case "text":
            return text_literal(node.text)


def _derive(draft: _Draft, given: str, parts: Iterable[str], suffix: str) -> str:
    """The name typed, or one composed from the table and the columns.

    An index and a check are named once per table in ClickHouse, so the names
    taken are this definition's own.
    """
    if given:
        if len(given) > NAME_LIMIT or given != given.strip():
            raise _Problem(
                say(
                    "A name is 1 to {limit} characters and does not start or end with spaces",
                    limit=NAME_LIMIT,
                ),
                field_name="name",
            )
        if given in draft.used:
            raise _Problem(say('This definition already calls something "{given}"', given=given), field_name="name")
        draft.used.add(given)
        return given
    stem = "_".join([draft.definition.name, *parts, suffix])
    at = 1
    while True:
        tail = "" if at == 1 else f"_{at}"
        candidate = stem[: NAME_LIMIT - len(tail)] + tail
        if candidate not in draft.used:
            draft.used.add(candidate)
            return candidate
        at += 1


def _fingerprint(node_id: str, statements: Sequence[PlannedStatement]) -> str:
    body = json.dumps(
        {"node": node_id, "statements": [item.sql for item in statements]},
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()
