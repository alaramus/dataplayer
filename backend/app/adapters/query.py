"""What a source that accepts complete SQL has to be able to say and do.

D62: this is the one operation in which the statement comes from the client.
Everywhere else the platform builds the statement and a client never supplies a
fragment of it (D2c). The exception is deliberate, declared per source, and
bounded by what is written here.

Nothing in this module is PostgreSQL. An adapter that implements the protocol
below answers with these shapes; the module that owns runs and results reads
them without knowing which source produced them.
"""

from collections.abc import AsyncIterator
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from app.adapters.relation import ColumnType

# The closed class of one prepared statement. "unknown" is a refusal rather
# than a write-shaped guess: a statement whose class cannot be established is
# not run (D62).
StatementClass = Literal[
    "read",
    "explain",
    "dml",
    "ddl",
    "transaction",
    "session",
    "copy",
    "unknown",
]

# What a run may be asked to do. Only reading exists in this slice; writing
# arrives with its own transaction lifecycle and its own decision (D66).
ExecutionMode = Literal["read"]

StatementStatus = Literal[
    "pending",
    "running",
    "succeeded",
    "failed",
    "cancelled",
    "timed_out",
    "not_run",
]


class QueryProfile(BaseModel):
    """What this source accepts, said by the source rather than guessed.

    Derived from what the adapter implements, so a capability cannot be
    announced and then be missing — and a screen never branches on the name of
    an adapter type to find any of this out (D62).
    """

    model_config = ConfigDict(extra="forbid")

    dialect: str
    # `:name`, and no second spelling. A parameter is a binding on the extended
    # query path, never text put into the statement.
    parameter_syntax: Literal["named_colon"]
    statement_modes: list[ExecutionMode]
    supports_cancel: bool
    supports_explain: bool
    default_timeout_seconds: int
    max_timeout_seconds: int


class QueryLimits(BaseModel):
    """Every ceiling one run is held to, passed in rather than reached for.

    The adapter enforces them while it reads, because only it is holding the
    cursor; the caller chooses them, because they are policy. D64 fixes the
    numbers and `app/queries` builds this from settings.
    """

    model_config = ConfigDict(extra="forbid")

    statement_timeout_seconds: int = Field(ge=1)
    script_timeout_seconds: int = Field(ge=1)
    max_statements: int = Field(ge=1)
    max_statement_bytes: int = Field(ge=1)
    max_result_rows: int = Field(ge=1)
    max_result_bytes: int = Field(ge=1)
    max_cell_bytes: int = Field(ge=1)
    max_run_results: int = Field(ge=1)
    max_run_bytes: int = Field(ge=1)
    max_messages: int = Field(ge=1)


class PreparedStatement(BaseModel):
    """One statement the source found in the text it was given.

    The range is into the submitted text, so an error can point at the place
    the person is looking at. Boundaries come from the dialect's own tokenizer:
    a semicolon inside a string, a comment or a dollar-quoted body is not a
    boundary, and no home-grown splitting decides that (D62).
    """

    model_config = ConfigDict(extra="forbid")

    ordinal: int = Field(ge=0)
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    text: str
    kind: StatementClass
    # Named parameters in this statement, in the order they first appear.
    parameters: list[str] = Field(default_factory=list)
    # What the statement names, for messages and for saying what a run touched.
    targets: list[str] = Field(default_factory=list)


class PreparedScript(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statements: list[PreparedStatement]
    parameters: list[str] = Field(default_factory=list)


class QueryRefused(Exception):
    """The source will not run this, and says why in words a person can read.

    Separate from `AdapterError`: nothing failed and nothing was reached. The
    statement was read and refused before a connection was asked for.
    """

    def __init__(self, message: str, *, ordinal: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.ordinal = ordinal


class ResultColumn(BaseModel):
    """One column of a result, whose identity is its position.

    SQL results have duplicate and empty headings as a matter of course, so the
    name is what is shown and the id is what is addressed (D64).
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    type: ColumnType


class MaterialisedResult(BaseModel):
    """One tabular output, read once and complete in itself.

    Not a cursor: keeping one would hold a transaction and a pooled connection
    while somebody reads, and re-running for the second page would show a
    different snapshot. Rows are canonical text, as everywhere else (D23).
    """

    model_config = ConfigDict(extra="forbid")

    columns: list[ResultColumn]
    rows: list[list[str | None]]
    # The source had more than the ceiling allowed; one extra row established
    # that, and it is not in `rows`.
    truncated: bool = False
    bytes_used: int = 0


class QueryDiagnostic(BaseModel):
    """Why a statement failed, reduced to what is safe to show.

    Driver text is never passed through: it carries the connection string,
    password included. What crosses is a code, a category, one normalised
    sentence and where in the submitted text it happened.
    """

    model_config = ConfigDict(extra="forbid")

    code: str
    category: Literal[
        "syntax",
        "missing_object",
        "permission",
        "read_only",
        "timeout",
        "cancelled",
        "data",
        "resource",
        "unknown",
    ]
    message: str
    # Offset into the statement, where the source gave one.
    position: int | None = None
    hint: str | None = None


class QueryNotice(BaseModel):
    """One message the source raised while running, bounded and stripped."""

    model_config = ConfigDict(extra="forbid")

    severity: str
    message: str


class StatementStarted(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: Literal["statement_started"] = "statement_started"
    ordinal: int


class StatementFinished(BaseModel):
    """What one statement did, whether or not it did it.

    The result is here rather than fetched later because it was read once, in
    the transaction that produced it; where it is kept afterwards is the
    caller's business.
    """

    model_config = ConfigDict(extra="forbid")

    event: Literal["statement_finished"] = "statement_finished"
    ordinal: int
    status: StatementStatus
    duration_ms: int
    command_tag: str | None = None
    row_count: int | None = None
    result: MaterialisedResult | None = None
    notices: list[QueryNotice] = Field(default_factory=list)
    diagnostic: QueryDiagnostic | None = None


QueryEvent = StatementStarted | StatementFinished


class ParameterValue(BaseModel):
    """One binding, as the source is given it.

    A value or SQL null, and nothing else: there is no type language here.
    PostgreSQL infers the type from the expression the parameter stands in,
    and an ambiguous expression is resolved with a cast in the SQL rather than
    with a second vocabulary in a form (D62).
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=63)
    value: str | None = None


class QueryRequest(BaseModel):
    """One press of Run, as the source is asked to carry it out.

    The text is exactly what will be executed; the caller has already decided
    whether that is a selection, one statement or a whole document, and the
    snapshot of it belongs to the run rather than to the document it came from
    (D63).
    """

    model_config = ConfigDict(extra="forbid")

    text: str
    mode: ExecutionMode
    # The ordered schema context to set before anything runs. Every name is
    # checked against the source before a statement is composed (D62).
    search_path: list[str] = Field(default_factory=list)
    # Bindings by name. A statement is given only the ones it uses.
    parameters: list[ParameterValue] = Field(default_factory=list)
    limits: QueryLimits


@runtime_checkable
class QueryExecution(Protocol):
    """One run in progress, and the two things a caller does with it.

    Cancellation is a method on the execution rather than a call back into the
    adapter, because what has to be reached is the connection this run is
    holding — and only the execution knows it.
    """

    def events(self) -> AsyncIterator[QueryEvent]: ...

    async def cancel(self) -> None: ...


@runtime_checkable
class SupportsQuery(Protocol):
    """A source that accepts a complete statement written by a user.

    Method-only, so capability discovery stays a runtime `isinstance` check
    against the protocol rather than a second handwritten list of what each
    adapter can do (D62).
    """

    def query_profile(self) -> QueryProfile: ...

    def prepare_query(self, text: str) -> PreparedScript: ...

    def open_query(self, request: QueryRequest) -> QueryExecution: ...
