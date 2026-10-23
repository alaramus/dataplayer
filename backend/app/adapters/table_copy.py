"""Tables copied with their structure, between two sources of one dialect (D182).

A source describes each table in its own words — a type as it spells it, a
default or a check as its catalog prints it — and a destination of the same
dialect composes and runs the copy from that description. Nothing here is SQL
the client wrote: the description is read from the source's catalog, and the
destination composes its statements itself, again, when the copy runs.

A catalog can lie, so every fragment is checked to be one expression before it
is composed into anything (`is_one_fragment`).
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.adapters.relation import RefAction

# Tables one copy may hold, the ones its links bring in included.
MAX_COPIED_TABLES = 100


# An enum, a domain and a composite type can be made again from what they
# are; a type an extension brings comes with its extension; anything else must
# already be at the destination.
TypeKind = Literal["enum", "domain", "composite", "extension", "other"]


class CopiedAttribute(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    type_sql: str


class CopiedType(BaseModel):
    """A type of the source's own that the tables use, by its qualified name."""

    model_config = ConfigDict(extra="forbid")

    schema_name: str
    name: str
    # As the source's catalog text names it, to be found there again.
    spelled: str
    kind: TypeKind
    labels: list[str] = Field(default_factory=list)
    extension: str | None = None
    # A domain: what it is over, and what it adds.
    base: str | None = None
    not_null: bool = False
    default: str | None = None
    checks: list[str] = Field(default_factory=list)
    attributes: list[CopiedAttribute] = Field(default_factory=list)


class CopiedColumn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    # The source's spelling, qualified wherever the type is not built in.
    type_sql: str
    not_null: bool = False
    default: str | None = None
    identity: Literal["always", "by_default"] | None = None
    identity_start: int | None = None
    identity_increment: int | None = None
    # A stored generated column's expression. Such a column takes no rows.
    generated: str | None = None
    # Named apart and quoted by whoever composes it.
    collation_schema: str | None = None
    collation_name: str | None = None
    comment: str | None = None
    # The serial spelling of a column whose default draws from a sequence it
    # owns: the copy gets a sequence of its own rather than sharing this one.
    serial: Literal["smallserial", "serial", "bigserial"] | None = None
    # The sequence a default draws from when the column does not own it.
    shared_sequence: str | None = None
    # The whole definition after the name, for a dialect that prints a column
    # in one line and keeps in it what the fields above cannot say (MySQL's
    # ON UPDATE, its character set). The fields above are read off it.
    definition: str | None = None


class CopiedConstraint(BaseModel):
    """A key, check or exclusion, in the source's own definition."""

    model_config = ConfigDict(extra="forbid")

    name: str
    kind: Literal["primary_key", "unique", "check", "exclude"]
    definition: str
    validated: bool = True


class CopiedIndex(BaseModel):
    """An index no constraint owns: its method and keys, without its table."""

    model_config = ConfigDict(extra="forbid")

    name: str
    unique: bool = False
    # What follows `USING`: the method, the keys, and whatever else it has.
    body: str


class CopiedLink(BaseModel):
    """A foreign key, by the columns at each end."""

    model_config = ConfigDict(extra="forbid")

    name: str
    columns: list[str]
    target_node_id: str
    target_schema: str
    target_name: str
    target_columns: list[str]
    on_update: RefAction = "no_action"
    on_delete: RefAction = "no_action"
    match: Literal["simple", "full"] = "simple"
    deferrable: bool = False
    initially_deferred: bool = False
    validated: bool = True


class CopiedTable(BaseModel):
    """One table as a copy of it is made."""

    model_config = ConfigDict(extra="forbid")

    node_id: str
    schema_name: str
    name: str
    # Why this cannot be copied at all; nothing else is described then.
    refusal: str | None = None
    comment: str | None = None
    unlogged: bool = False
    columns: list[CopiedColumn] = Field(default_factory=list)
    constraints: list[CopiedConstraint] = Field(default_factory=list)
    indexes: list[CopiedIndex] = Field(default_factory=list)
    links: list[CopiedLink] = Field(default_factory=list)
    # The source's own types its columns use, directly or through another
    # type, each after the ones it is made of.
    types: list[CopiedType] = Field(default_factory=list)
    # Other tables whose keys land on this one.
    referenced_by: list[str] = Field(default_factory=list)
    # What the copy will not have, in a phrase each: "2 triggers".
    left_behind: list[str] = Field(default_factory=list)
    row_estimate: int | None = None
    # What follows the columns, for a dialect that prints its table options
    # in a line of their own: MySQL's engine, character set and comment.
    options: str | None = None

    @property
    def label(self) -> str:
        return f"{self.schema_name}.{self.name}"


# What becomes of one link: it points at the copy of its target, at the
# original target, or it is not made.
LinkDecision = Literal["copy", "original", "drop"]


class TableCopyTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    table: CopiedTable
    name: str
    # By the link's name; a link absent here is not made.
    links: dict[str, LinkDecision] = Field(default_factory=dict)


class TableCopyRequest(BaseModel):
    """Everything a destination composes a copy from."""

    model_config = ConfigDict(extra="forbid")

    dialect: str
    # The place the tables are made in, as the destination's catalog issued it.
    place_node_id: str
    # Whether both ends are one database, so a link may keep its original.
    same_database: bool
    tables: list[TableCopyTarget] = Field(max_length=MAX_COPIED_TABLES)
    rows: bool = True


class CopyStatement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # The source table it belongs to; None for what the tables share.
    node_id: str | None = None
    title: str
    sql: str
    # Before the rows arrive, or after: keys and indexes are built once over
    # the rows rather than row by row.
    stage: Literal["before", "after"] = "before"


class CopyLoad(BaseModel):
    """The rows of one table: which columns are read at one end and written at
    the other. A generated column takes none."""

    model_config = ConfigDict(extra="forbid")

    node_id: str
    # The new table.
    schema_name: str
    name: str
    columns: list[str]

    @property
    def target_label(self) -> str:
        return f"{self.schema_name}.{self.name}"


class CopyProblem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # The source table it is about; None for the copy as a whole.
    node_id: str | None = None
    message: str
    kind: Literal["invalid", "conflict"] = "invalid"


class TableCopyPlan(BaseModel):
    """What a copy would run, composed but not run."""

    model_config = ConfigDict(extra="forbid")

    statements: list[CopyStatement] = Field(default_factory=list)
    loads: list[CopyLoad] = Field(default_factory=list)
    problems: list[CopyProblem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class TableRows(Protocol):
    """The rows of the source's tables, all read in one snapshot."""

    def rows(self, node_id: str, columns: list[str]) -> AsyncIterator[bytes]:
        """One table's rows in the dialect's own bulk format."""
        ...


# Called as the rows of a table arrive: which table, and how many rows and
# bytes have arrived for it so far.
Arrived = Callable[[CopyLoad, int, int], Awaitable[None]]
RowsOf = Callable[[CopyLoad], AsyncIterator[bytes]]


def is_one_fragment(text: str) -> bool:
    """Whether catalog text is one expression and nothing after it.

    Not a parser: a check that no statement can end and no comment can start
    outside quotes, that every quote closes and every parenthesis matches.
    That is what composing it into a larger statement relies on, and all it
    relies on.
    """
    depth = 0
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char in ("'", '"'):
            closing = text.find(char, index + 1)
            # A doubled quote inside is an escaped one: keep looking past it.
            while closing != -1 and text[closing + 1 : closing + 2] == char:
                closing = text.find(char, closing + 2)
            if closing == -1:
                return False
            index = closing + 1
            continue
        if char == ";" or text.startswith(("--", "/*"), index) or char == "$":
            return False
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                return False
        index += 1
    return depth == 0 and text.strip() != ""
