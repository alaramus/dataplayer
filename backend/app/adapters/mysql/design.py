"""Planning and creating one designed MySQL table (D117, D236).

The plan a person reviews and the statement that runs come from one composer,
as PostgreSQL's do. Unlike PostgreSQL's, the plan is one `CREATE TABLE`: keys,
checks, foreign keys and indexes are all written inside it, because MySQL
commits each structure statement by itself (D233) and a table half made is a
table nobody asked for.

What MySQL does not have is a problem next to the object that asks for it —
deferrable constraints, MATCH FULL, SET DEFAULT, NULLS FIRST, INCLUDE, partial
indexes, UNLOGGED, an identity that is ALWAYS or steps by more than one —
rather than a statement the server refuses after the person has reviewed it.
"""

import hashlib
import json
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
from app.adapters.mysql import ids
from app.adapters.mysql.catalog import MysqlCatalog
from app.adapters.mysql.relation import MysqlRelation
from app.adapters.mysql.session import MysqlSession, quoted_name
from app.adapters.protocol import NodeNotFound
from app.adapters.relation import IndexMethodOption, RefAction
from app.adapters.table_design import (
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

# MySQL's limit for the name of a table, a column, an index or a constraint.
NAME_LIMIT = 64


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


# Codes shared with the smaller add-a-column vocabulary (D27) mean the same
# type here; a code is never SQL.
DESIGN_TYPES: dict[str, _Type] = {
    item.option.code: item
    for item in (
        _type("varchar", N_("Text, limited"), "varchar(n)", "varchar", parameters=["length"], category="text"),
        _type("char", N_("Text, fixed"), "char(n)", "char", parameters=["length"], category="text"),
        _type("long_text", N_("Long text"), "text", "text", category="text"),
        _type("medium_text", N_("Medium text"), "mediumtext", "mediumtext", category="text"),
        _type("huge_text", N_("Huge text"), "longtext", "longtext", category="text"),
        _type("tinyint", N_("Tiny integer"), "tinyint", "tinyint", identity=True, category="number"),
        _type("smallint", N_("Small integer"), "smallint", "smallint", identity=True, category="number"),
        _type("integer", N_("Integer"), "int", "int", identity=True, category="number"),
        _type("bigint", N_("Big integer"), "bigint", "bigint", identity=True, category="number"),
        _type(
            "decimal",
            N_("Decimal"),
            "decimal(p,s)",
            "decimal",
            parameters=["precision", "scale"],
            category="number",
        ),
        _type("float", N_("Single precision"), "float", "float", category="number"),
        _type("double", N_("Floating point"), "double", "double", category="number"),
        _type("boolean", N_("Boolean (0 or 1)"), "tinyint(1)", "tinyint(1)", category="boolean"),
        _type("date", N_("Date"), "date", "date", category="temporal"),
        _type("time", N_("Time"), "time", "time", category="temporal"),
        _type("datetime", N_("Date and time"), "datetime", "datetime", category="temporal"),
        _type("timestamp", N_("Timestamp (UTC)"), "timestamp", "timestamp", category="temporal"),
        _type("year", N_("Year"), "year", "year", category="temporal"),
        _type("json", N_("JSON"), "json", "json", category="document"),
        _type("uuid", N_("UUID as text"), "char(36)", "char(36)", category="text"),
        _type("binary", N_("Bytes, fixed"), "binary(n)", "binary", parameters=["length"]),
        _type("varbinary", N_("Bytes, limited"), "varbinary(n)", "varbinary", parameters=["length"]),
        _type("blob", N_("Bytes"), "blob", "blob"),
        _type("point", N_("Point"), "point", "point"),
        _type("geometry", N_("Geometry"), "geometry", "geometry"),
    )
}

# A length MySQL insists on and a designer may leave empty: a VARCHAR has no
# length of its own, and 255 is the one a person means when they give none.
# CHAR and BINARY default to one character in MySQL itself.
_DEFAULT_LENGTH = {"varchar": 255, "varbinary": 255}

# Types that take no literal default in MySQL; an expression default is theirs.
_NO_LITERAL_DEFAULT = frozenset(
    {"long_text", "medium_text", "huge_text", "json", "blob", "point", "geometry"}
)


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


# MySQL refuses a function that is not deterministic in a generated column, a
# check or an index, so the clock and UUID() fill a default and nothing else.
DESIGN_FUNCTIONS: dict[str, _Function] = {
    item.option.code: item
    for item in (
        _function("now", N_("Now"), "CURRENT_TIMESTAMP", "CURRENT_TIMESTAMP", 0, _DEFAULT_ONLY, bare=True),
        _function("current_date", N_("Today"), "CURRENT_DATE", "CURRENT_DATE", 0, _DEFAULT_ONLY, bare=True),
        _function("uuid", N_("Random UUID"), "UUID()", "UUID", 0, _DEFAULT_ONLY),
        _function("lower", N_("Lower case"), "LOWER(x)", "LOWER", 1, _EVERYWHERE),
        _function("upper", N_("Upper case"), "UPPER(x)", "UPPER", 1, _EVERYWHERE),
        _function("trim", N_("Trimmed"), "TRIM(x)", "TRIM", 1, _EVERYWHERE),
        _function("length", N_("Length"), "CHAR_LENGTH(x)", "CHAR_LENGTH", 1, _EVERYWHERE),
        _function("abs", N_("Absolute"), "ABS(x)", "ABS", 1, _EVERYWHERE),
        _function("round", N_("Rounded"), "ROUND(x)", "ROUND", 1, _EVERYWHERE),
        _function("coalesce", N_("First value present"), "COALESCE(x, y)", "COALESCE", 2, _EVERYWHERE),
    )
}

_COMPARE = {"eq": "=", "ne": "<>", "lt": "<", "lte": "<=", "gt": ">", "gte": ">="}
_ARITHMETIC = {"add": "+", "subtract": "-", "multiply": "*", "divide": "/"}
_REF_ACTIONS: dict[RefAction, str] = {
    "restrict": "RESTRICT",
    "cascade": "CASCADE",
    "set_null": "SET NULL",
}

REFERENCE_ACTION_CHOICES = [
    DesignChoice(code="no_action", title=N_("No action")),
    DesignChoice(code="restrict", title=N_("Restrict")),
    DesignChoice(code="cascade", title=N_("Cascade")),
    DesignChoice(code="set_null", title=N_("Set null")),
]
MATCH_CHOICES = [DesignChoice(code="simple", title=N_("Match simple"))]
PERSISTENCE_CHOICES = [DesignChoice(code="permanent", title=N_("Permanent"))]

DESIGN_INDEX_METHODS = [
    IndexMethodOption(code="btree", title=N_("B-tree"), sql="BTREE", unique_supported=True, multi_column_supported=True),
    IndexMethodOption(
        code="fulltext", title=N_("Full text"), sql="FULLTEXT", unique_supported=False, multi_column_supported=True
    ),
    IndexMethodOption(
        code="spatial", title=N_("Spatial"), sql="SPATIAL", unique_supported=False, multi_column_supported=False
    ),
]

_COLLATIONS = """
SELECT COLLATION_NAME AS name
FROM information_schema.COLLATIONS
WHERE CHARACTER_SET_NAME = 'utf8mb4'
ORDER BY COLLATION_NAME
LIMIT 300
"""

# Foreign keys and checks are named once per database in MySQL, not per table.
_TAKEN = """
SELECT TABLE_NAME AS name FROM information_schema.TABLES WHERE TABLE_SCHEMA = %s
UNION
SELECT CONSTRAINT_NAME FROM information_schema.TABLE_CONSTRAINTS
WHERE CONSTRAINT_SCHEMA = %s AND CONSTRAINT_TYPE IN ('FOREIGN KEY', 'CHECK')
"""

_SQL_MODE = "SELECT @@SESSION.sql_mode AS mode"

CREATE_REFUSALS: dict[int, str] = {
    1050: N_("Something with that name is already there"),
    1826: N_("Something with that name is already there"),
    1061: N_("Two indexes of one table cannot share a name"),
    1060: N_("Two columns cannot have the same name"),
    1101: N_("A text, blob or JSON column cannot have a literal default"),
    1067: N_("A default does not fit the type of its column"),
    1075: N_("An AUTO_INCREMENT column must be a key"),
    1215: N_("These columns and the ones they point at cannot be compared"),
    3780: N_("These columns and the ones they point at cannot be compared"),
    6125: N_("The target relation has no unique key over those columns"),
    1822: N_("The target relation has no unique key over those columns"),
    1170: N_("A text or blob column in a key needs a length"),
    3152: N_("A JSON column cannot be part of a key"),
    3813: N_("A check reads a column that is not there"),
    3814: N_("A check uses something that is not allowed in a check"),
    3757: N_("A function in an index must give the same answer every time"),
    1142: N_("This connection may not create a table in that database"),
    1044: N_("This connection may not create a table in that database"),
    1064: N_("The composed statement was refused by the server"),
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
    collations: set[str]
    taken: set[str]
    backslashes: bool
    mariadb: bool
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


def literal(text: str, *, backslashes: bool) -> str:
    """A string literal as MySQL reads it in the session it will run in.

    A backslash is an escape unless the server runs with
    NO_BACKSLASH_ESCAPES, so how it is written depends on the mode the plan
    was read with.
    """
    body = text.replace("'", "''")
    if backslashes:
        body = body.replace("\\", "\\\\").replace("\x00", "\\0")
    elif "\x00" in text:
        raise _Problem(say("A value cannot contain a NUL character"), field_name="expression")
    return f"'{body}'"


def type_sql(chosen: DesignColumnType) -> str:
    known = DESIGN_TYPES.get(chosen.code)
    if known is None:
        raise _Problem(say('Unknown column type "{code}"', code=chosen.code), field_name="type")
    takes = known.option.parameters
    title = say(known.option.title)
    if chosen.dimensions:
        raise _Problem(say("MySQL has no array columns"), field_name="type")
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
    length = chosen.length if chosen.length is not None else _DEFAULT_LENGTH.get(chosen.code)
    if length is not None:
        return f"{known.base}({length})"
    if chosen.precision is not None:
        return f"{known.base}({chosen.precision},{chosen.scale or 0})"
    return known.base


class MysqlTableDesign:
    """The three questions a designed table asks of one MySQL connection."""

    def __init__(self, session: MysqlSession, catalog: MysqlCatalog, relation: MysqlRelation) -> None:
        self._session = session
        self._catalog = catalog
        self._relation = relation

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
        collations = await self._session.query(_COLLATIONS)
        return TableDesignOptions(
            supported=True,
            schema_label=node.name,
            types=worded_titles(item.option for item in DESIGN_TYPES.values()),
            index_methods=worded_titles(DESIGN_INDEX_METHODS),
            functions=worded_titles(item.option for item in DESIGN_FUNCTIONS.values()),
            collations=[str(row["name"]) for row in collations],
            reference_actions=worded_titles(REFERENCE_ACTION_CHOICES),
            match_modes=worded_titles(MATCH_CHOICES),
            persistence_options=worded_titles(PERSISTENCE_CHOICES),
            hypertable=HypertableOffer(offered=False),
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
        async with self._session.altering(refusals=CREATE_REFUSALS) as work:
            for statement in plan.statements:
                # Reviewed as it reads; a `%` doubled only for the driver.
                await work.execute(statement.sql.replace("%", "%%"))
        schema, _ = ids.parse(node_id)
        return (await self._catalog.path_to(ids.relation_id(schema, definition.name)))[-1]

    async def _draft(self, node_id: str, definition: TableDefinition) -> _Draft:
        node, reason = await self._destination(node_id)
        if node is None:
            raise ValueError(reason)
        mode = await self._session.query(_SQL_MODE)
        collations: set[str] = set()
        if any(column.collation for column in definition.columns):
            collations = {str(row["name"]) for row in await self._session.query(_COLLATIONS)}
        taken = {str(row["name"]).lower() for row in await self._session.query(_TAKEN, (node.name, node.name))}
        return _Draft(
            schema=node.name,
            definition=definition,
            columns={column.id: column for column in definition.columns},
            collations=collations,
            taken=taken,
            backslashes="NO_BACKSLASH_ESCAPES" not in str(mode[0]["mode"]).upper(),
            mariadb=(await self._session.profile()).mariadb,
        )

    async def _statements(self, draft: _Draft) -> list[PlannedStatement]:
        definition = draft.definition
        _check_name(draft, definition.name, None)
        if definition.name.lower() in draft.taken:
            draft.problems.append(
                PlanProblem(
                    field="name",
                    kind="conflict",
                    message=say('Something called "{name}" is already in that database', name=definition.name),
                )
            )
        if definition.persistence != "permanent":
            draft.problems.append(
                PlanProblem(field="persistence", message=say("MySQL has no unlogged tables"))
            )
        if definition.partition is not None:
            draft.problems.append(
                PlanProblem(field="partition", message=say("A MySQL table is not partitioned here"))
            )
        if definition.hypertable is not None:
            draft.problems.append(
                PlanProblem(field="hypertable", message=say("A hypertable is TimescaleDB's, not MySQL's"))
            )
        _check_column_names(draft)
        lines = _column_lines(draft)
        lines += _key_lines(draft)
        lines += await self._foreign_lines(draft)
        lines += _index_lines(draft)
        _check_identity(draft)
        if draft.problems:
            return []
        table = quoted_name(draft.schema, definition.name)
        options: list[str] = []
        start = _identity_start(draft)
        if start is not None:
            options.append(f"AUTO_INCREMENT={start}")
        if definition.comment:
            options.append(f"COMMENT={literal(definition.comment, backslashes=draft.backslashes)}")
        statement = f"CREATE TABLE {table} (\n    " + ",\n    ".join(lines) + "\n)"
        if options:
            statement += " " + " ".join(options)
        return [PlannedStatement(title=say("Table {name}", name=definition.name), sql=statement)]

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
        if foreign.deferrable or foreign.initially_deferred:
            raise _Problem(say("MySQL checks a foreign key at once; it cannot be deferred"), field_name="deferrable")
        if foreign.match != "simple":
            raise _Problem(say("MySQL matches a foreign key simply"), field_name="match")
        for action, where in ((foreign.on_update, "on_update"), (foreign.on_delete, "on_delete")):
            if action == "set_default":
                raise _Problem(say("InnoDB does not carry out SET DEFAULT on a foreign key"), field_name=where)
            if action == "set_null":
                for column_id in foreign.column_ids:
                    column = draft.columns.get(column_id)
                    if column is not None and column.not_null:
                        raise _Problem(
                            say('"{name}" must have a value, so it cannot be set to null', name=column.name),
                            field_name=where,
                        )
        try:
            target = await self._relation.facts(foreign.target_node_id)
        except ValueError as exc:
            raise _Problem(str(exc), field_name="target_node_id") from None
        except NodeNotFound:
            raise _Problem(say("That table is not there"), field_name="target_node_id") from None
        if len(foreign.column_ids) != len(foreign.target_columns):
            raise _Problem(say("A foreign key names as many columns as it points at"), field_name="target_columns")
        if not any(
            key.kind in ("PRIMARY KEY", "UNIQUE") and key.columns == list(foreign.target_columns)
            for key in target.keys
        ):
            raise _Problem(
                say('"{name}" has no unique key over exactly those columns', name=target.name),
                field_name="target_columns",
            )
        name = _derive(draft, foreign.name, [_column_name(draft, column) for column in foreign.column_ids], "fk")
        line = (
            f"CONSTRAINT {quoted_name(name)} FOREIGN KEY ({local}) "
            f"REFERENCES {quoted_name(target.schema, target.name)} "
            f"({', '.join(quoted_name(column) for column in foreign.target_columns)})"
        )
        if foreign.on_update != "no_action":
            line += f" ON UPDATE {_REF_ACTIONS[foreign.on_update]}"
        if foreign.on_delete != "no_action":
            line += f" ON DELETE {_REF_ACTIONS[foreign.on_delete]}"
        return line


def _check_name(draft: _Draft, name: str, object_id: str | None) -> None:
    if name == "" or name != name.strip() or len(name) > NAME_LIMIT:
        draft.problems.append(
            PlanProblem(
                object_id=object_id,
                field="name",
                message=say(
                    "A MySQL name is 1 to {limit} characters and does not start or end with spaces",
                    limit=NAME_LIMIT,
                ),
            )
        )


def _check_column_names(draft: _Draft) -> None:
    seen: set[str] = set()
    for column in draft.definition.columns:
        _check_name(draft, column.name, column.id)
        # Column names are not case-sensitive in MySQL.
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
    line = f"{quoted_name(column.name)} {type_sql(column.type)}"
    if column.collation is not None:
        if known is None or known.option.category != "text":
            raise _Problem(say("Only a text column has a collation"), field_name="collation")
        if column.collation not in draft.collations:
            raise _Problem(
                say('This server has no collation "{collation}"', collation=column.collation),
                field_name="collation",
            )
        line += f" COLLATE {column.collation}"
    generation = column.generation
    if isinstance(generation, StoredGeneration):
        referenced = referenced_columns(generation.expression)
        if column.id in referenced:
            raise _Problem(say("A generated column cannot be computed from itself"), field_name="generation")
        line += f" GENERATED ALWAYS AS ({_expression(draft, generation.expression, 'generated')}) STORED"
    if column.not_null or isinstance(generation, IdentityGeneration):
        line += " NOT NULL"
    match generation:
        case LiteralDefault(value=value):
            if column.type.code in _NO_LITERAL_DEFAULT:
                raise _Problem(
                    say("A text, blob or JSON column cannot have a literal default"), field_name="generation"
                )
            line += f" DEFAULT {literal(value, backslashes=draft.backslashes)}"
        case ExpressionDefault(expression=expression):
            line += f" DEFAULT ({_expression(draft, expression, 'default')})"
        case IdentityGeneration() as identity:
            if known is None or not known.option.identity_supported:
                raise _Problem(say("Only an integer column can be an identity column"), field_name="generation")
            if identity.generated == "always":
                raise _Problem(
                    say("MySQL takes a value written into an AUTO_INCREMENT column; it cannot be ALWAYS"),
                    field_name="generation",
                )
            if identity.increment not in (None, 1):
                raise _Problem(
                    say("MySQL steps AUTO_INCREMENT by a server setting, not per column"),
                    field_name="generation",
                )
            line += " AUTO_INCREMENT"
        case NoGeneration() | StoredGeneration():
            pass
    if column.comment:
        line += f" COMMENT {literal(column.comment, backslashes=draft.backslashes)}"
    return line


def _identity_columns(draft: _Draft) -> list[DesignColumn]:
    return [column for column in draft.definition.columns if isinstance(column.generation, IdentityGeneration)]


def _check_identity(draft: _Draft) -> None:
    """One AUTO_INCREMENT column, and it leads a key, or MySQL refuses the table."""
    identities = _identity_columns(draft)
    if len(identities) > 1:
        draft.problems.append(
            PlanProblem(
                object_id=identities[1].id,
                field="generation",
                message=say("A MySQL table has at most one AUTO_INCREMENT column"),
            )
        )
    if not identities:
        return
    column_id = identities[0].id
    definition = draft.definition
    leads = [definition.primary_key.column_ids[0]] if definition.primary_key else []
    leads += [unique.column_ids[0] for unique in definition.unique_constraints]
    leads += [
        index.keys[0].column_id for index in definition.indexes if isinstance(index.keys[0], IndexColumnKey)
    ]
    if column_id not in leads:
        draft.problems.append(
            PlanProblem(
                object_id=column_id,
                field="generation",
                message=say("An AUTO_INCREMENT column must lead the primary key, a unique key or an index"),
            )
        )


def _identity_start(draft: _Draft) -> int | None:
    for column in _identity_columns(draft):
        generation = column.generation
        if isinstance(generation, IdentityGeneration) and generation.start is not None:
            return generation.start
    return None


def _key_lines(draft: _Draft) -> list[str]:
    definition = draft.definition
    lines: list[str] = []
    key = definition.primary_key
    if key is not None:
        try:
            if key.name and key.name != "PRIMARY":
                draft.warnings.append(say("MySQL calls every primary key PRIMARY; the name given is not kept"))
            for column_id in key.column_ids:
                column = draft.columns.get(column_id)
                if column is not None and not column.not_null and not isinstance(
                    column.generation, IdentityGeneration
                ):
                    raise _Problem(
                        say('"{name}" is part of the primary key, so it must have a value', name=column.name),
                        field_name="not_null",
                        object_id=column.id,
                    )
            lines.append(f"PRIMARY KEY ({_column_list(draft, key.column_ids)})")
        except _Problem as problem:
            draft.note(problem, None)
    for unique in definition.unique_constraints:
        try:
            if unique.nulls_not_distinct:
                raise _Problem(
                    say("MySQL always treats nulls as different in a unique key"), field_name="nulls_not_distinct"
                )
            if unique.deferrable or unique.initially_deferred:
                raise _Problem(say("MySQL checks a unique key at once; it cannot be deferred"), field_name="deferrable")
            columns = _column_list(draft, unique.column_ids)
            name = _derive(draft, unique.name, [_column_name(draft, column) for column in unique.column_ids], "key")
            lines.append(f"CONSTRAINT {quoted_name(name)} UNIQUE ({columns})")
        except _Problem as problem:
            draft.note(problem, unique.id)
    for check in definition.checks:
        try:
            body = _expression(draft, check.expression, "check")
            name = _derive(draft, check.name, [], "chk")
            lines.append(f"CONSTRAINT {quoted_name(name)} CHECK ({body})")
        except _Problem as problem:
            draft.note(problem, check.id)
    return lines


def _index_lines(draft: _Draft) -> list[str]:
    lines: list[str] = []
    for index in draft.definition.indexes:
        try:
            lines.append(_index_line(draft, index))
        except _Problem as problem:
            draft.note(problem, index.id)
    return lines


def _index_line(draft: _Draft, index: DesignIndex) -> str:
    method = next((item for item in DESIGN_INDEX_METHODS if item.code == index.method), None)
    if method is None:
        raise _Problem(say('Unknown index method "{method}"', method=index.method), field_name="method")
    if index.unique and not method.unique_supported:
        raise _Problem(say("{title} cannot build a unique index", title=say(method.title)), field_name="unique")
    if len(index.keys) > 1 and not method.multi_column_supported:
        raise _Problem(say("{title} cannot index more than one column", title=say(method.title)), field_name="keys")
    if index.include_column_ids:
        raise _Problem(say("MySQL cannot carry extra columns in an index"), field_name="include_column_ids")
    if index.predicate is not None:
        raise _Problem(say("MySQL has no partial indexes"), field_name="predicate")
    parts: list[str] = []
    for key in index.keys:
        if key.nulls is not None:
            raise _Problem(say("MySQL puts nulls first in an index and cannot be told otherwise"), field_name="nulls")
        if key.operator_class is not None:
            raise _Problem(say("MySQL has no operator classes"), field_name="operator_class")
        if isinstance(key, IndexColumnKey):
            part = quoted_name(_column_name(draft, key.column_id))
        else:
            if draft.mariadb:
                raise _Problem(say("MariaDB cannot index an expression"), field_name="keys")
            part = f"({_expression(draft, key.expression, 'index')})"
        if key.direction == "desc":
            if method.code != "btree":
                raise _Problem(say("Only a B-tree index has a direction"), field_name="direction")
            part += " DESC"
        parts.append(part)
    name = _derive(
        draft,
        index.name,
        [_column_name(draft, key.column_id) for key in index.keys if isinstance(key, IndexColumnKey)],
        "idx",
    )
    kind = "UNIQUE " if index.unique else {"fulltext": "FULLTEXT ", "spatial": "SPATIAL "}.get(method.code, "")
    return f"{kind}INDEX {quoted_name(name)} ({', '.join(parts)})"


def _expression(draft: _Draft, node: Expression, context: ExpressionContext) -> str:
    oversized = too_large(node)
    if oversized is not None:
        raise _Problem(oversized, field_name="expression")
    return _composed(draft, node, context)


def _composed(draft: _Draft, node: Expression, context: ExpressionContext) -> str:
    match node:
        case LiteralValue():
            return _literal(draft, node)
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
            values = ", ".join(_literal(draft, value) for value in node.values)
            keyword = "NOT IN" if node.negated else "IN"
            return f"({_composed(draft, node.operand, context)} {keyword} ({values}))"
        case Cast():
            return _cast(draft, node, context)


# What a published type is cast to: CAST in MySQL takes a few targets only,
# by type where one fits and by category otherwise.
_CAST_BY_CODE = {
    "tinyint": "SIGNED",
    "smallint": "SIGNED",
    "integer": "SIGNED",
    "bigint": "SIGNED",
    "date": "DATE",
    "time": "TIME",
}
_CAST_TARGETS = {
    "number": "DECIMAL(65,30)",
    "text": "CHAR",
    "temporal": "DATETIME",
    "document": "JSON",
    "boolean": "SIGNED",
}


def _cast(draft: _Draft, node: Cast, context: ExpressionContext) -> str:
    known = DESIGN_TYPES.get(node.type_code)
    if known is None:
        raise _Problem(say('Unknown type "{type_code}"', type_code=node.type_code), field_name="expression")
    target = _CAST_BY_CODE.get(node.type_code) or _CAST_TARGETS.get(known.option.category)
    if target is None:
        raise _Problem(say("MySQL cannot cast to {title}", title=say(known.option.title)), field_name="expression")
    return f"CAST({_composed(draft, node.operand, context)} AS {target})"


def _literal(draft: _Draft, node: LiteralValue) -> str:
    match node.value_kind:
        case "null":
            return "NULL"
        case "boolean":
            if node.text not in ("true", "false"):
                raise _Problem(say("A boolean is true or false"), field_name="expression")
            return "TRUE" if node.text == "true" else "FALSE"
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
            return f"CAST({literal(node.text, backslashes=draft.backslashes)} AS JSON)"
        case "text":
            return literal(node.text, backslashes=draft.backslashes)


def _derive(draft: _Draft, given: str, parts: Iterable[str], suffix: str) -> str:
    """The name typed, or one composed from the table and the columns.

    A name typed and taken is a refusal; a composed one is numbered until it
    is free, as PostgreSQL's are. Names are compared without case, as MySQL
    compares them.
    """
    if given:
        if len(given) > NAME_LIMIT or given != given.strip():
            raise _Problem(
                say(
                    "A MySQL name is 1 to {limit} characters and does not start or end with spaces",
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
