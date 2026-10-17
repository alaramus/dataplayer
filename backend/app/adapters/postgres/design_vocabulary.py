"""What a PostgreSQL table may be designed out of, and the syntax for it.

Every entry pairs an opaque code with a fixed fragment. The code is what a
client sends; the fragment is what this module composes. A type, a function or
an access method that is not in a table here does not exist as far as a
definition is concerned, which is the property D2c asks for and the reason
nothing in this file is built out of a string that arrived in a request.
"""

from dataclasses import dataclass
from typing import Any

from psycopg import sql

from app.adapters.expressions import ExpressionContext
from app.adapters.table_design import (
    DesignChoice,
    DesignColumnType,
    DesignTypeCategory,
    DesignTypeOption,
    DesignTypeParameter,
    FunctionOption,
    OperatorClassOption,
)
from app.core.translation import N_, say


@dataclass(frozen=True)
class PostgresDesignType:
    option: DesignTypeOption
    # The bare type, before parameters and array brackets are attached.
    base: sql.SQL


def _type(
    code: str,
    title: str,
    spelling: str,
    fragment: sql.SQL,
    *,
    parameters: list[DesignTypeParameter] | None = None,
    identity: bool = False,
    category: DesignTypeCategory = "other",
) -> PostgresDesignType:
    return PostgresDesignType(
        option=DesignTypeOption(
            code=code,
            title=title,
            sql=spelling,
            parameters=parameters or [],
            array_supported=True,
            identity_supported=identity,
            category=category,
        ),
        base=fragment,
    )


# The order is the order the choices are offered in, so the ordinary answers
# come first. Codes that also exist in the smaller add-a-column vocabulary
# (D27) are spelled the same on purpose: one code means one type everywhere.
POSTGRES_DESIGN_TYPES: dict[str, PostgresDesignType] = {
    item.option.code: item
    for item in (
        _type("text", N_("Text"), "text", sql.SQL("text"), category="text"),
        _type(
            "varchar",
            N_("Text, limited"),
            "varchar(n)",
            sql.SQL("varchar"),
            parameters=["length"],
            category="text",
        ),
        _type(
            "char",
            N_("Text, fixed"),
            "char(n)",
            sql.SQL("char"),
            parameters=["length"],
            category="text",
        ),
        _type(
            "smallint", N_("Small integer"), "smallint", sql.SQL("smallint"),
            identity=True, category="number",
        ),
        _type(
            "integer", N_("Integer"), "integer", sql.SQL("integer"),
            identity=True, category="number",
        ),
        _type(
            "bigint", N_("Big integer"), "bigint", sql.SQL("bigint"),
            identity=True, category="number",
        ),
        _type(
            "numeric",
            N_("Numeric"),
            "numeric(p,s)",
            sql.SQL("numeric"),
            parameters=["precision", "scale"],
            category="number",
        ),
        _type("real", N_("Real"), "real", sql.SQL("real"), category="number"),
        _type(
            "double", N_("Double precision"), "double precision",
            sql.SQL("double precision"), category="number",
        ),
        _type("boolean", N_("Boolean"), "boolean", sql.SQL("boolean"), category="boolean"),
        _type("date", N_("Date"), "date", sql.SQL("date"), category="temporal"),
        _type("time", N_("Time"), "time", sql.SQL("time"), category="temporal"),
        _type(
            "timestamp", N_("Timestamp"), "timestamp", sql.SQL("timestamp"),
            category="temporal",
        ),
        _type(
            "timestamp_tz",
            N_("Timestamp with time zone"),
            "timestamptz",
            sql.SQL("timestamp with time zone"),
            category="temporal",
        ),
        _type(
            "interval", N_("Interval"), "interval", sql.SQL("interval"),
            category="temporal",
        ),
        _type("uuid", N_("UUID"), "uuid", sql.SQL("uuid"), category="other"),
        _type("jsonb", N_("JSON"), "jsonb", sql.SQL("jsonb"), category="document"),
        _type("bytea", N_("Bytes"), "bytea", sql.SQL("bytea"), category="other"),
        _type("inet", N_("IP address"), "inet", sql.SQL("inet"), category="other"),
        _type(
            "daterange", N_("Date range"), "daterange", sql.SQL("daterange"),
            category="other",
        ),
        _type(
            "int4range", N_("Integer range"), "int4range", sql.SQL("int4range"),
            category="other",
        ),
        _type(
            "tstzrange",
            N_("Timestamp range"),
            "tstzrange",
            sql.SQL("tstzrange"),
            category="other",
        ),
    )
}


def type_sql(chosen: DesignColumnType) -> sql.Composed:
    """One column type, parameters and array brackets included.

    Raises ValueError for a code nobody published and for a parameter the type
    does not take: a length on a boolean is a request about a type that does
    not exist, not a value to ignore.
    """
    known = POSTGRES_DESIGN_TYPES.get(chosen.code)
    if known is None:
        raise ValueError(say('Unknown column type "{code}"', code=chosen.code))
    takes = known.option.parameters
    if chosen.length is not None and "length" not in takes:
        raise ValueError(say("{title} takes no length", title=say(known.option.title)))
    if chosen.precision is not None and "precision" not in takes:
        raise ValueError(say("{title} takes no precision", title=say(known.option.title)))
    if chosen.scale is not None and "scale" not in takes:
        raise ValueError(say("{title} takes no scale", title=say(known.option.title)))
    if chosen.scale is not None and chosen.precision is None:
        raise ValueError(say("{title} needs a precision before a scale", title=say(known.option.title)))
    if (
        chosen.precision is not None
        and chosen.scale is not None
        and chosen.scale > chosen.precision
    ):
        raise ValueError(say("A scale cannot exceed its precision"))

    parts: list[sql.Composable] = [known.base]
    if chosen.length is not None:
        parts.append(sql.SQL("({})").format(sql.Literal(chosen.length)))
    elif chosen.precision is not None and chosen.scale is not None:
        parts.append(
            sql.SQL("({},{})").format(
                sql.Literal(chosen.precision), sql.Literal(chosen.scale)
            )
        )
    elif chosen.precision is not None:
        parts.append(sql.SQL("({})").format(sql.Literal(chosen.precision)))
    parts.extend(sql.SQL("[]") for _ in range(chosen.dimensions))
    return sql.Composed(parts)


def type_spelling(chosen: DesignColumnType) -> str:
    """The same type as text, for a message about it."""
    return type_sql(chosen).as_string()


@dataclass(frozen=True)
class PostgresFunction:
    option: FunctionOption
    fragment: sql.SQL


def _function(
    code: str,
    title: str,
    signature: str,
    fragment: sql.SQL,
    arity: int,
    contexts: list[ExpressionContext],
) -> PostgresFunction:
    return PostgresFunction(
        option=FunctionOption(
            code=code,
            title=title,
            signature=signature,
            arity=arity,
            contexts=contexts,
        ),
        fragment=fragment,
    )


# Which contexts a function may appear in is its own property, and the reason
# is the server's: an index expression and a stored generated column must be
# immutable, so `now()` fills a column and cannot index one. Publishing that
# per function is what keeps the rule out of the browser.
_EVERYWHERE: list[ExpressionContext] = [
    "default",
    "generated",
    "check",
    "index",
    "predicate",
]
_DEFAULT_ONLY: list[ExpressionContext] = ["default"]

POSTGRES_DESIGN_FUNCTIONS: dict[str, PostgresFunction] = {
    item.option.code: item
    for item in (
        _function("now", N_("Now"), "now()", sql.SQL("now"), 0, _DEFAULT_ONLY),
        _function(
            "current_date",
            N_("Today"),
            "current_date",
            sql.SQL("current_date"),
            0,
            _DEFAULT_ONLY,
        ),
        _function(
            "gen_random_uuid",
            N_("Random UUID"),
            "gen_random_uuid()",
            sql.SQL("gen_random_uuid"),
            0,
            _DEFAULT_ONLY,
        ),
        _function("lower", N_("Lower case"), "lower(x)", sql.SQL("lower"), 1, _EVERYWHERE),
        _function("upper", N_("Upper case"), "upper(x)", sql.SQL("upper"), 1, _EVERYWHERE),
        _function("trim", N_("Trimmed"), "btrim(x)", sql.SQL("btrim"), 1, _EVERYWHERE),
        _function(
            "length", N_("Length"), "length(x)", sql.SQL("length"), 1, _EVERYWHERE
        ),
        _function("abs", N_("Absolute"), "abs(x)", sql.SQL("abs"), 1, _EVERYWHERE),
        _function("round", N_("Rounded"), "round(x)", sql.SQL("round"), 1, _EVERYWHERE),
        _function(
            "coalesce",
            N_("First value present"),
            "coalesce(x, y)",
            sql.SQL("coalesce"),
            2,
            _EVERYWHERE,
        ),
    )
}

# `current_date` is a keyword rather than a call: PostgreSQL accepts it without
# parentheses and writes it back that way, so composing `current_date()` would
# produce a statement the server does not have.
BARE_FUNCTIONS = frozenset({"current_date"})

COMPARE_SQL: dict[str, sql.SQL] = {
    "eq": sql.SQL("="),
    "ne": sql.SQL("<>"),
    "lt": sql.SQL("<"),
    "lte": sql.SQL("<="),
    "gt": sql.SQL(">"),
    "gte": sql.SQL(">="),
}

ARITHMETIC_SQL: dict[str, sql.SQL] = {
    "add": sql.SQL("+"),
    "subtract": sql.SQL("-"),
    "multiply": sql.SQL("*"),
    "divide": sql.SQL("/"),
}

DIRECTION_SQL: dict[str, sql.SQL] = {"asc": sql.SQL("ASC"), "desc": sql.SQL("DESC")}
NULLS_SQL: dict[str, sql.SQL] = {
    "first": sql.SQL("NULLS FIRST"),
    "last": sql.SQL("NULLS LAST"),
}
MATCH_SQL: dict[str, sql.SQL] = {
    "simple": sql.SQL("MATCH SIMPLE"),
    "full": sql.SQL("MATCH FULL"),
}
PARTITION_SQL: dict[str, sql.SQL] = {
    "range": sql.SQL("RANGE"),
    "list": sql.SQL("LIST"),
    "hash": sql.SQL("HASH"),
}

REFERENCE_ACTION_CHOICES = [
    DesignChoice(code="no_action", title=N_("No action")),
    DesignChoice(code="restrict", title=N_("Restrict")),
    DesignChoice(code="cascade", title=N_("Cascade")),
    DesignChoice(code="set_null", title=N_("Set null")),
    DesignChoice(code="set_default", title=N_("Set default")),
]
MATCH_CHOICES = [
    DesignChoice(code="simple", title=N_("Match simple")),
    DesignChoice(code="full", title=N_("Match full")),
]
# Temporary is missing on purpose: its lifetime is a database session, and a
# pooled request cannot promise one.
PERSISTENCE_CHOICES = [
    DesignChoice(code="permanent", title=N_("Permanent")),
    DesignChoice(code="unlogged", title=N_("Unlogged")),
]
PARTITION_CHOICES = [
    DesignChoice(code="range", title=N_("Range")),
    DesignChoice(code="list", title=N_("List")),
    DesignChoice(code="hash", title=N_("Hash")),
]

# Which methods take INCLUDE columns. PostgreSQL says B-tree and GiST, and it
# is a property of the method rather than of the index, so it is written beside
# the other method facts instead of being discovered from a failed statement.
INCLUDE_METHODS = frozenset({"btree", "gist"})

# The operator classes the server has, bounded and read once per options call.
# `opcintype` is the type the class applies to, spelled the way `format_type`
# spells it, which is how it is matched to a published type code.
OPERATOR_CLASSES = """
SELECT am.amname AS method,
       oc.opcname AS name,
       pg_catalog.format_type(oc.opcintype, NULL) AS applies_to,
       oc.opcdefault AS is_default
FROM pg_catalog.pg_opclass oc
JOIN pg_catalog.pg_am am ON am.oid = oc.opcmethod
WHERE am.amtype = 'i'
ORDER BY am.amname, oc.opcname
LIMIT 500
"""

COLLATIONS = """
SELECT collname AS name
FROM pg_catalog.pg_collation
WHERE collencoding IN (-1, pg_catalog.pg_char_to_encoding(
        current_setting('server_encoding')))
ORDER BY collname
LIMIT 200
"""


def operator_class_options(
    rows: list[dict[str, Any]], methods: set[str]
) -> list[OperatorClassOption]:
    """The classes belonging to the methods on offer, named by type code.

    A class for a type this vocabulary does not publish is still listed: the
    key it would cover may be an expression, and the type of an expression is
    the server's to know.
    """
    by_spelling = {
        item.option.sql: code for code, item in POSTGRES_DESIGN_TYPES.items()
    }
    options: list[OperatorClassOption] = []
    for row in rows:
        method = str(row["method"])
        if method not in methods:
            continue
        applies_to = str(row["applies_to"])
        options.append(
            OperatorClassOption(
                code=str(row["name"]),
                title=f"{row['name']} ({applies_to})",
                method=method,
                type_code=by_spelling.get(applies_to),
                default=bool(row["is_default"]),
            )
        )
    return options
