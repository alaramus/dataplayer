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

# What a run may be asked to do, and who ends the transaction.
#
# `read` is a read-only transaction the source enforces. `auto_commit` makes
# the whole run one transaction and commits only when every statement
# succeeded. `manual` leaves the transaction open for the person to end (D66).
ExecutionMode = Literal["read", "auto_commit", "manual"]

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
    # The four below are filled in from what the adapter actually implements,
    # by the route that answers this. An adapter does not restate them, so a
    # capability cannot be announced and then be missing (D62).
    supports_explain: bool = False
    supports_metadata: bool = False
    supports_formatting: bool = False
    supports_generated_query: bool = False
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
    # Whether this statement is one to ask about every time it is run (D66).
    risk: Literal["low", "high"] = "low"
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
    # How many rows a change touched, said by the source. Distinct from
    # `row_count`, which is how many rows came back to be looked at (D66).
    affected_rows: int | None = None
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


class RelationSummary(BaseModel):
    """One relation the editor may complete to."""

    model_config = ConfigDict(extra="forbid")

    schema_name: str
    name: str
    kind: Literal["table", "view", "materialized_view", "foreign_table", "other"]


class ColumnSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    type_sql: str


class QueryMetadataRequest(BaseModel):
    """What the editor wants to know now, not everything there is.

    Progressive on purpose (D65): the schemas in the current context first,
    the columns of a relation when one appears or completion asks for it, and
    another schema only when something is qualified with it.
    """

    model_config = ConfigDict(extra="forbid")

    search_path: list[str] = Field(default_factory=list, max_length=32)
    relations: list[str] = Field(default_factory=list, max_length=50)


class QueryMetadata(BaseModel):
    """What the source knows, and whether that is all of it.

    `complete` is the difference between "there is no such table" and "this
    editor has not been told about it": with limited metadata the console
    shows a status rather than red underlines under real relations (D65).
    """

    model_config = ConfigDict(extra="forbid")

    schemas: list[str] = Field(default_factory=list)
    relations: list[RelationSummary] = Field(default_factory=list)
    columns: dict[str, list[ColumnSummary]] = Field(default_factory=dict)
    complete: bool = True


class GenerateQueryRequest(BaseModel):
    """Ask the source for a statement about one of its nodes.

    The browser never assembles an identifier; quoting a name is a property of
    the dialect, so the source writes the SQL (D65).
    """

    model_config = ConfigDict(extra="forbid")

    node_id: str
    kind: Literal["select", "name", "columns"] = "select"


class GeneratedQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str


class ExplainNode(BaseModel):
    """One operation of a plan, and what the source estimates about it.

    Estimates, and nothing measured: this is a plan, not a run. What a
    statement would actually do is Explain Analyze, which executes and is
    therefore a separate decision (D65).
    """

    model_config = ConfigDict(extra="forbid")

    # Its place in the tree — "0", "0.1" — so a table row and a tree node are
    # the same node in two views.
    id: str
    kind: str
    label: str
    relation: str | None = None
    startup_cost: float | None = None
    total_cost: float | None = None
    rows: int | None = None
    width: int | None = None
    # Whatever else the source said about this operation, as text.
    details: dict[str, str] = Field(default_factory=dict)
    children: list[ExplainNode] = Field(default_factory=list)


class ExplainRequest(BaseModel):
    """One statement to be planned, and the context to plan it in."""

    model_config = ConfigDict(extra="forbid")

    text: str
    search_path: list[str] = Field(default_factory=list)
    parameters: list[ParameterValue] = Field(default_factory=list)
    timeout_seconds: int = Field(default=30, ge=1)


class ExplainResult(BaseModel):
    """A plan, in the two forms the source gives and a third the screen makes.

    The tree is the source's own structure and the raw text is what it prints;
    the table is the tree read as a list, which the screen flattens rather than
    the server inventing a second shape (D65).
    """

    model_config = ConfigDict(extra="forbid")

    plan: ExplainNode
    raw: str
    # The source's own estimate for the whole statement, kept at the top so a
    # screen does not have to know which field of which node means it.
    total_cost: float | None = None
    rows: int | None = None
    truncated: bool = False


class TransactionContext(BaseModel):
    """What an open transaction is set up with, once, when it begins."""

    model_config = ConfigDict(extra="forbid")

    search_path: list[str] = Field(default_factory=list)
    statement_timeout_seconds: int = Field(default=30, ge=1)


class TransactionState(BaseModel):
    """What is true of an open transaction now.

    Everything a person is shown about it comes from here, so the screen never
    infers a transaction's state from the last thing it happened to see (D66).
    """

    model_config = ConfigDict(extra="forbid")

    open: bool
    # Whether the source has made the transaction unusable — after an error,
    # PostgreSQL refuses everything until it ends.
    broken: bool = False
    statements: int = 0
    mutating_statements: int = 0
    affected_rows: int = 0
    targets: list[str] = Field(default_factory=list)


@runtime_checkable
class QueryTransaction(Protocol):
    """One transaction, open across more than one request.

    It holds a physical connection, which is why it is leased rather than
    created per run and why something has to end it (D66).
    """

    def execute(self, request: QueryRequest) -> QueryExecution: ...

    def absorb(self, run: QueryExecution) -> None: ...

    def state(self) -> TransactionState: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...

    async def aclose(self) -> None: ...


@runtime_checkable
class SupportsTransactions(Protocol):
    """A source that will hold a transaction open between requests."""

    async def begin_transaction(self, context: TransactionContext) -> QueryTransaction: ...


@runtime_checkable
class SupportsExplain(Protocol):
    """A source that will plan a statement without running it (D65)."""

    async def explain_query(self, request: ExplainRequest) -> ExplainResult: ...


@runtime_checkable
class SupportsQueryMetadata(Protocol):
    """A source that can say what an editor may complete to."""

    async def query_metadata(self, request: QueryMetadataRequest) -> QueryMetadata: ...


@runtime_checkable
class SupportsQueryFormatting(Protocol):
    """A source that can lay its own dialect out again."""

    def format_query(self, text: str) -> str: ...


@runtime_checkable
class SupportsGeneratedQuery(Protocol):
    """A source that writes a statement about one of its own nodes."""

    async def generate_query(self, request: GenerateQueryRequest) -> GeneratedQuery: ...


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
