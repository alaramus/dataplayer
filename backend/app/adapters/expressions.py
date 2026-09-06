"""A closed expression model, so that a definition never carries SQL.

D2c refuses a SQL fragment typed into a field, which is why a column default is
a literal (D30) and an index has neither a predicate nor an expression (D39).
A table being designed needs all three — `now()`, `total >= 0`, a partial
index — and the way to have them without reopening that door is a vocabulary
rather than a parser: every node here is one of a fixed set of shapes, every
function is an opaque code the source maps to a fragment, and every value
crosses as data.

Nothing in this module composes anything. What each node becomes is the
source's to say, and only the adapter that owns the dialect says it.
"""

from collections.abc import Iterator
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# Where an expression sits, because a valid default is not a valid predicate:
# `now()` may fill a column and cannot decide a CHECK, and a column reference
# means nothing in a default. The source publishes which functions belong to
# which context, and the planner checks the answer.
ExpressionContext = Literal["default", "generated", "check", "index", "predicate"]

CompareOperator = Literal["eq", "ne", "lt", "lte", "gt", "gte"]
ArithmeticOperator = Literal["add", "subtract", "multiply", "divide"]
# What a literal is, so that the source knows what to quote it as rather than
# guessing from the characters. "json" is separate from "text" because the two
# reach a column differently, and a JSON document typed as text would arrive
# as a string containing braces.
LiteralKind = Literal["text", "number", "boolean", "null", "json"]

# What a draft object calls itself while it exists only in the browser. Stable
# across renames and reordering, which is the whole reason a definition refers
# to columns this way and never by name (D29 is the same rule for a column
# that exists).
DraftId = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,36}$")]

MAX_EXPRESSION_DEPTH = 8
MAX_EXPRESSION_NODES = 100
MAX_LITERAL_CHARS = 1000
MAX_MEMBERSHIP_VALUES = 100
MAX_ARGUMENTS = 8
MAX_TERMS = 32


class LiteralValue(BaseModel):
    """One value, as text plus what kind of value the text spells.

    The text is never composed into a statement: the source hands it to the
    driver as a bound literal, exactly as D30 does for a default.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["literal"] = "literal"
    value_kind: LiteralKind
    text: str = Field(default="", max_length=MAX_LITERAL_CHARS)


class ColumnReference(BaseModel):
    """A column of the table being defined, by its draft id."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["column"] = "column"
    column_id: DraftId


class FunctionCall(BaseModel):
    """A function the source advertised, by code, with its arguments.

    Never a name to call: the code is looked up in a registry that fixes the
    fragment, the arity and the contexts it is allowed in, so a code nobody
    published resolves to nothing rather than to a call.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["call"] = "call"
    function: str = Field(min_length=1, max_length=64)
    arguments: list[Expression] = Field(default_factory=list, max_length=MAX_ARGUMENTS)


class Comparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["compare"] = "compare"
    operator: CompareOperator
    left: Expression
    right: Expression


class Arithmetic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["arithmetic"] = "arithmetic"
    operator: ArithmeticOperator
    left: Expression
    right: Expression


class BooleanGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["group"] = "group"
    operator: Literal["and", "or"]
    terms: list[Expression] = Field(min_length=2, max_length=MAX_TERMS)


class Negation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["not"] = "not"
    operand: Expression


class NullTest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["null_test"] = "null_test"
    operand: Expression
    negated: bool = False


class Membership(BaseModel):
    """One value against a bounded list of literals, and nothing else.

    Literals rather than expressions, deliberately: a subquery is the thing
    this model exists to make unsayable.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["in"] = "in"
    operand: Expression
    values: list[LiteralValue] = Field(min_length=1, max_length=MAX_MEMBERSHIP_VALUES)
    negated: bool = False


class Cast(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["cast"] = "cast"
    operand: Expression
    # A published type code, the same vocabulary a column is declared with. Not
    # SQL, for the reason a column type is not SQL (D27).
    type_code: str = Field(min_length=1, max_length=64)


Expression = Annotated[
    LiteralValue
    | ColumnReference
    | FunctionCall
    | Comparison
    | Arithmetic
    | BooleanGroup
    | Negation
    | NullTest
    | Membership
    | Cast,
    Field(discriminator="kind"),
]


class ExpressionNodeModel(BaseModel):
    """A holder, so that a bare expression can be validated on its own."""

    model_config = ConfigDict(extra="forbid")

    expression: Expression


def children(node: Expression) -> list[Expression]:
    """Whatever this node is composed of, in reading order."""
    match node:
        case FunctionCall():
            return list(node.arguments)
        case Comparison() | Arithmetic():
            return [node.left, node.right]
        case BooleanGroup():
            return list(node.terms)
        case Negation() | NullTest() | Cast():
            return [node.operand]
        case Membership():
            return [node.operand, *node.values]
        case _:
            return []


def walk(node: Expression) -> Iterator[Expression]:
    """Every node of the tree, the root first."""
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(children(current))


def depth_of(node: Expression) -> int:
    """How deeply the tree nests, counting the root as one."""
    deepest = 1
    stack = [(node, 1)]
    while stack:
        current, level = stack.pop()
        deepest = max(deepest, level)
        stack.extend((child, level + 1) for child in children(current))
    return deepest


def referenced_columns(node: Expression) -> set[str]:
    return {item.column_id for item in walk(node) if isinstance(item, ColumnReference)}


def too_large(node: Expression) -> str | None:
    """Why this expression is beyond what may be planned, or nothing.

    Checked after parsing as well as before it: the raw guard below bounds what
    the parser is asked to build, and this bounds what the composer is asked to
    walk. Neither is the other's duplicate — one reads JSON, one reads a tree.
    """
    if depth_of(node) > MAX_EXPRESSION_DEPTH:
        return f"An expression may nest at most {MAX_EXPRESSION_DEPTH} levels deep"
    if sum(1 for _ in walk(node)) > MAX_EXPRESSION_NODES:
        return f"An expression may hold at most {MAX_EXPRESSION_NODES} parts"
    return None


# How deeply a whole definition may nest before it is parsed at all, and how
# many containers it may hold. A recursive model built by Pydantic recurses on
# the way in, so hostile JSON is turned away by walking it iteratively first —
# a bound on the parser rather than on the tree, which is why the number is
# larger than the one above: a definition nests several levels of its own
# before an expression starts.
MAX_RAW_DEPTH = 32
MAX_RAW_CONTAINERS = 5000


def raw_shape_refusal(raw: Any) -> str | None:
    """Why this payload is too nested or too large to parse, or nothing."""
    containers = 0
    stack: list[tuple[Any, int]] = [(raw, 1)]
    while stack:
        current, level = stack.pop()
        if isinstance(current, dict):
            values: list[Any] = list(current.values())
        elif isinstance(current, list):
            values = list(current)
        else:
            continue
        containers += 1
        if containers > MAX_RAW_CONTAINERS:
            return "That definition holds more parts than can be planned"
        if level > MAX_RAW_DEPTH:
            return f"A definition may nest at most {MAX_RAW_DEPTH} levels deep"
        stack.extend((value, level + 1) for value in values)
    return None
