"""A table designed whole, planned before it is created.

The other creation paths make a relation out of something that already exists:
rows kept as a table, a CSV loaded into one (D43, D45). This one starts from
nothing, so everything a table can be — its keys, its indexes, its checks —
has to be sayable in a request rather than discovered from data. Nothing here
is SQL: types, methods, functions and operator classes are all opaque codes the
source publishes and only the source turns into syntax (D27, D2c).

Three questions, in order. What may be defined at all, what the definition
would become, and then the creation itself, which happens through the ordinary
action so that access, refusals and catalog reloads stay in one place (D9).
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.adapters.expressions import (
    MAX_EXPRESSION_DEPTH,
    MAX_EXPRESSION_NODES,
    DraftId,
    Expression,
    ExpressionContext,
    raw_shape_refusal,
)
from app.adapters.hypertable_design import (
    MAX_HASH_DIMENSIONS,
    MAX_HASH_PARTITIONS,
    DesignDuration,
    DurationUnit,
    IntegerSpan,
    NewNowDesign,
    NowFunction,
    NowTemplate,
    Span,
    SparseKind,
)
from app.adapters.relation import IndexMethodOption, RefAction
from app.core.translation import N_, say

MAX_COLUMNS = 100
MAX_INDEXES = 32
MAX_CONSTRAINTS = 32
MAX_KEY_COLUMNS = 32
MAX_PARTITION_COLUMNS = 8
NAME_LIMIT_BYTES = 63

# A name that may be left empty, meaning the source should derive one. An index
# nobody named is the ordinary case, and a name invented by the browser could
# collide with something the browser cannot see.
DerivedName = Annotated[str, Field(default="", max_length=NAME_LIMIT_BYTES)]
ObjectName = Annotated[str, Field(min_length=1, max_length=NAME_LIMIT_BYTES)]

# What a type takes beside its code, and what sort of thing it holds. Named
# rather than written inline so the adapter that fills the list is checked
# against the same set the model accepts.
DesignTypeParameter = Literal["length", "precision", "scale"]
DesignTypeCategory = Literal[
    "text", "number", "boolean", "temporal", "document", "other"
]


class DesignChoice(BaseModel):
    """One value of a closed set, in the source's own words."""

    model_config = ConfigDict(extra="forbid")

    code: str
    title: str


class DesignTypeOption(BaseModel):
    """One type a new column may take, and what it accepts beside its code.

    Richer than the `ColumnTypeOption` a column added to an existing relation
    is offered: that list is deliberately small (D27) and takes no parameters,
    and widening it would change what every existing caller may send. A table
    being designed is the place where a length or a precision is chosen, so the
    parameters are declared here, still as flags rather than as syntax.
    """

    model_config = ConfigDict(extra="forbid")

    code: str
    title: str
    # The spelling, published so a person recognises what they are choosing.
    # Never sent back and never composed from: the code is what travels.
    sql: str
    # Which typed parameters this type takes, if any.
    parameters: list[DesignTypeParameter] = Field(default_factory=list)
    array_supported: bool = False
    # Whether a column of this type may be an identity column. PostgreSQL says
    # integers only, and a form that offered it on text would be offering a
    # refusal.
    identity_supported: bool = False
    # For grouping the choice in a menu; not a rule about anything.
    category: DesignTypeCategory = "other"


class FunctionOption(BaseModel):
    """One function a definition may call, by code, where it may be called."""

    model_config = ConfigDict(extra="forbid")

    code: str
    title: str
    # What it looks like written out, so a person knows what they are picking.
    signature: str
    arity: int = 0
    contexts: list[ExpressionContext] = Field(default_factory=list)


class OperatorClassOption(BaseModel):
    """One operator class, for one access method and one type.

    Read from the server rather than written down: which classes exist depends
    on what is installed, so a list kept in this repository would be wrong
    within a release and a list kept in the browser would be a guess.
    """

    model_config = ConfigDict(extra="forbid")

    code: str
    title: str
    method: str
    # The type code it applies to, or nothing when it applies to a type this
    # vocabulary does not publish.
    type_code: str | None = None
    default: bool = False


class DesignLimits(BaseModel):
    """What a definition may not exceed, published so a form can say so first."""

    model_config = ConfigDict(extra="forbid")

    max_columns: int = MAX_COLUMNS
    max_indexes: int = MAX_INDEXES
    max_constraints: int = MAX_CONSTRAINTS
    max_key_columns: int = MAX_KEY_COLUMNS
    max_expression_depth: int = MAX_EXPRESSION_DEPTH
    max_expression_nodes: int = MAX_EXPRESSION_NODES
    name_bytes: int = NAME_LIMIT_BYTES


class IntegerTimeOption(BaseModel):
    """What an integer type can be as a hypertable's time column (D207)."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["smallint", "integer", "bigint"]
    chunk_interval: IntegerSpan
    # The largest interval or policy age the type holds, as a decimal string.
    maximum: str
    now_templates: list[NowTemplate] = Field(default_factory=list)


class HypertableOffer(BaseModel):
    """Whether this destination can create a hypertable, and in which units (D207)."""

    model_config = ConfigDict(extra="forbid")

    # False where the source has no such thing at all, and the editor leaves
    # the section out; a PostgreSQL database without TimescaleDB is offered
    # it and says why it is unavailable.
    offered: bool = True
    available: bool = False
    reason: str | None = None
    # Whether "Timescale chooses" is a state the release keeps after enabling.
    per_chunk_defaults: bool = False
    interval_units: list[DurationUnit] = Field(default_factory=list)
    policy_units: list[DurationUnit] = Field(default_factory=list)
    integer_types: list[IntegerTimeOption] = Field(default_factory=list)
    # Functions of this database an integer time column may take as integer_now.
    now_functions: list[NowFunction] = Field(default_factory=list)
    # What this release has beyond the oldest one supported (D207, H7).
    sparse_indexes: bool = False
    compaction: bool = False
    uuid_time: bool = False


class EngineParameter(BaseModel):
    """A column an engine is given, and which types that column may have."""

    model_config = ConfigDict(extra="forbid")

    code: str
    title: str
    # One column or several.
    many: bool = False
    required: bool = False
    # Type codes a column given here may have, so a form offers only those.
    type_codes: list[str] = Field(default_factory=list)


class EngineOption(BaseModel):
    """One way a table may be kept, where the source has more than one."""

    model_config = ConfigDict(extra="forbid")

    code: str
    title: str
    description: str | None = None
    # Whether rows are kept in the order of a key. A primary key and an index
    # belong to such an engine only, and the editor leaves both out elsewhere.
    sorted: bool = True
    # Whether rows sharing the primary key are merged into one, which makes
    # the key required: a table without one would be merged into one row.
    merges_by_key: bool = False
    parameters: list[EngineParameter] = Field(default_factory=list)


class DesignAbilities(BaseModel):
    """Which parts of a definition this source has at all.

    The editor leaves out what is false rather than showing it and waiting for
    the plan to refuse it, the way a hypertable is left out everywhere but
    PostgreSQL. False by default, so a new source shows what it declared and
    nothing it forgot. What depends on a value rather than on the source — a
    method that cannot be unique, a type that cannot be an identity — stays on
    that value; the composer still refuses all of it, whatever a form showed.
    """

    model_config = ConfigDict(extra="forbid")

    unique_constraints: bool = False
    foreign_keys: bool = False
    deferrable_unique: bool = False
    deferrable_foreign_keys: bool = False
    # Ordering of an index key, and where its nulls go.
    index_direction: bool = False
    index_nulls_order: bool = False
    # Columns an index carries without sorting by them, and a predicate.
    index_include: bool = False
    partial_indexes: bool = False
    comments: bool = False
    # Tablespace and owner, shown as fields not built yet.
    tablespaces: bool = False


class TableDesignOptions(BaseModel):
    """What one destination will accept a designed table with.

    Answers rather than raises when it will accept none, the way
    `NewRelationOptions` does: a schema the server owns is a real schema, and
    saying why is more use than pretending it is not there.
    """

    model_config = ConfigDict(extra="forbid")

    supported: bool = False
    reason: str | None = None
    # What the destination is called, so the editor's header names it without
    # taking apart the node id (D21).
    schema_label: str = ""
    types: list[DesignTypeOption] = Field(default_factory=list)
    index_methods: list[IndexMethodOption] = Field(default_factory=list)
    functions: list[FunctionOption] = Field(default_factory=list)
    operator_classes: list[OperatorClassOption] = Field(default_factory=list)
    collations: list[str] = Field(default_factory=list)
    reference_actions: list[DesignChoice] = Field(default_factory=list)
    match_modes: list[DesignChoice] = Field(default_factory=list)
    persistence_options: list[DesignChoice] = Field(default_factory=list)
    partition_strategies: list[DesignChoice] = Field(default_factory=list)
    # Whether a unique constraint here can treat nulls as equal. A property of
    # the server rather than of the vocabulary: PostgreSQL learned it in 15, so
    # a form that offered it everywhere would be offering a syntax error.
    nulls_not_distinct_supported: bool = False
    hypertable: HypertableOffer = Field(default_factory=HypertableOffer)
    # Empty where the source keeps every table one way; the first is the usual.
    engines: list[EngineOption] = Field(default_factory=list)
    abilities: DesignAbilities = Field(default_factory=DesignAbilities)
    limits: DesignLimits = Field(default_factory=DesignLimits)


class DesignColumnType(BaseModel):
    """A published type code with the parameters that type declared."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=64)
    length: int | None = Field(default=None, ge=1, le=10_485_760)
    precision: int | None = Field(default=None, ge=1, le=1000)
    scale: int | None = Field(default=None, ge=0, le=1000)
    # PostgreSQL allows six; one is what a form can show honestly, and two is
    # as far as anything here has ever needed to go.
    dimensions: int = Field(default=0, ge=0, le=2)


class NoGeneration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["none"] = "none"


class LiteralDefault(BaseModel):
    """A value the column type coerces, exactly as D30 assigns one."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["literal"] = "literal"
    value: str = Field(max_length=1000)


class ExpressionDefault(BaseModel):
    """A default the source can compose, such as `now()`."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["expression"] = "expression"
    expression: Expression


class IdentityGeneration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["identity"] = "identity"
    generated: Literal["always", "by_default"] = "by_default"
    start: int | None = None
    increment: int | None = None

    @model_validator(mode="after")
    def increment_is_not_zero(self) -> IdentityGeneration:
        if self.increment == 0:
            raise ValueError(say("An identity column cannot increment by zero"))
        return self


class StoredGeneration(BaseModel):
    """A value computed from the row and stored with it."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["generated"] = "generated"
    expression: Expression


# One choice, so that two of them cannot arrive together: a default string kept
# beside a generation mode can hold both, and then something has to decide which
# of the two wins. A union cannot be in that state.
Generation = Annotated[
    NoGeneration
    | LiteralDefault
    | ExpressionDefault
    | IdentityGeneration
    | StoredGeneration,
    Field(discriminator="kind"),
]


class DesignColumn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # The browser's own id for this draft column, referred to by every key,
    # index and expression. Renaming or reordering a column therefore changes
    # nothing else in the definition.
    id: DraftId
    name: ObjectName
    type: DesignColumnType
    not_null: bool = False
    comment: str | None = Field(default=None, max_length=1000)
    collation: str | None = Field(default=None, max_length=63)
    generation: Generation = NoGeneration()


class DesignPrimaryKey(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: DerivedName = ""
    # In key order, which is not the order the columns are declared in.
    column_ids: list[DraftId] = Field(min_length=1, max_length=MAX_KEY_COLUMNS)


class DesignUnique(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: DraftId
    name: DerivedName = ""
    column_ids: list[DraftId] = Field(min_length=1, max_length=MAX_KEY_COLUMNS)
    nulls_not_distinct: bool = False
    deferrable: bool = False
    initially_deferred: bool = False


class DesignCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: DraftId
    name: DerivedName = ""
    expression: Expression


class DesignForeignKey(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: DraftId
    name: DerivedName = ""
    column_ids: list[DraftId] = Field(min_length=1, max_length=MAX_KEY_COLUMNS)
    # The target as the catalog issued it (D21), and one of the candidate keys
    # that target publishes. A column called `id` is not evidence of a key.
    target_node_id: str = Field(min_length=1, max_length=512)
    target_columns: list[str] = Field(min_length=1, max_length=MAX_KEY_COLUMNS)
    on_update: RefAction = "no_action"
    on_delete: RefAction = "no_action"
    match: Literal["simple", "full"] = "simple"
    deferrable: bool = False
    initially_deferred: bool = False


class IndexColumnKey(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["column"] = "column"
    column_id: DraftId
    direction: Literal["asc", "desc"] | None = None
    nulls: Literal["first", "last"] | None = None
    operator_class: str | None = Field(default=None, max_length=64)


class IndexExpressionKey(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["expression"] = "expression"
    expression: Expression
    direction: Literal["asc", "desc"] | None = None
    nulls: Literal["first", "last"] | None = None
    operator_class: str | None = Field(default=None, max_length=64)


IndexKey = Annotated[IndexColumnKey | IndexExpressionKey, Field(discriminator="kind")]


class DesignIndex(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: DraftId
    name: DerivedName = ""
    method: str = Field(default="btree", min_length=1, max_length=64)
    unique: bool = False
    keys: list[IndexKey] = Field(min_length=1, max_length=MAX_KEY_COLUMNS)
    include_column_ids: list[DraftId] = Field(
        default_factory=list, max_length=MAX_KEY_COLUMNS
    )
    predicate: Expression | None = None


class DesignPartition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: Literal["range", "list", "hash"]
    column_ids: list[DraftId] = Field(min_length=1, max_length=MAX_PARTITION_COLUMNS)


class TableHashDimension(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column_id: DraftId
    partitions: int = Field(strict=True, gt=0, le=MAX_HASH_PARTITIONS)


class TableOrderKey(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column_id: DraftId
    descending: bool = Field(strict=True)
    nulls_first: bool = Field(strict=True)


class TableSparseIndex(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column_id: DraftId
    kind: SparseKind


class TableHypertable(BaseModel):
    """The table created as a hypertable, its columns named by draft id (D207).

    The same settings as the hypertable editor's, flattened into what a new
    table can have: nothing is kept as it is, and no tablespace is attached,
    since the designer places no table in one.
    """

    model_config = ConfigDict(extra="forbid")

    time_column_id: DraftId
    chunk_interval: Span
    hash_dimensions: list[TableHashDimension] = Field(default_factory=list, max_length=MAX_HASH_DIMENSIONS)
    columnstore: bool = False
    segment_mode: Literal["default", "none", "columns"] = "default"
    segment_column_ids: list[DraftId] = Field(default_factory=list, max_length=MAX_KEY_COLUMNS)
    order_mode: Literal["default", "columns"] = "default"
    order_keys: list[TableOrderKey] = Field(default_factory=list, max_length=MAX_KEY_COLUMNS)
    merge_interval: DesignDuration | None = None
    retention: Span | None = None
    columnstore_policy: Span | None = None
    reorder_index_id: DraftId | None = None
    integer_now: NewNowDesign | None = None
    sparse_mode: Literal["default", "none", "columns"] = "default"
    sparse_indexes: list[TableSparseIndex] = Field(default_factory=list, max_length=MAX_KEY_COLUMNS)
    compaction_policy: bool = False


class EngineArgument(BaseModel):
    """The columns given to one parameter of the chosen engine."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=64)
    column_ids: list[DraftId] = Field(min_length=1, max_length=MAX_KEY_COLUMNS)


class DesignEngine(BaseModel):
    """A published engine, by code, with the columns its parameters name."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=64)
    arguments: list[EngineArgument] = Field(default_factory=list, max_length=8)


class TableDefinition(BaseModel):
    """Everything about a table that does not exist yet.

    The destination is not in here: it is the node the action is performed on,
    so there is one place it can come from and no way for the two to disagree.
    """

    model_config = ConfigDict(extra="forbid")

    name: ObjectName
    comment: str | None = Field(default=None, max_length=1000)
    persistence: Literal["permanent", "unlogged"] = "permanent"
    columns: list[DesignColumn] = Field(min_length=1, max_length=MAX_COLUMNS)
    primary_key: DesignPrimaryKey | None = None
    unique_constraints: list[DesignUnique] = Field(
        default_factory=list, max_length=MAX_CONSTRAINTS
    )
    checks: list[DesignCheck] = Field(default_factory=list, max_length=MAX_CONSTRAINTS)
    foreign_keys: list[DesignForeignKey] = Field(
        default_factory=list, max_length=MAX_CONSTRAINTS
    )
    indexes: list[DesignIndex] = Field(default_factory=list, max_length=MAX_INDEXES)
    partition: DesignPartition | None = None
    hypertable: TableHypertable | None = None
    # None is the source's usual engine; only a source that publishes engines
    # accepts one.
    engine: DesignEngine | None = None

    @model_validator(mode="before")
    @classmethod
    def within_shape(cls, raw: Any) -> Any:
        """Turn away a payload too nested to parse, before parsing it.

        The expression model is recursive, so Pydantic recurses on the way in
        and hostile JSON would fail as a crash rather than as a refusal. The
        raw walk is iterative and cheap, and what it lets through is bounded
        again per expression once the tree exists.
        """
        refusal = raw_shape_refusal(raw)
        if refusal is not None:
            raise ValueError(refusal)
        return raw

    @model_validator(mode="after")
    def ids_are_distinct(self) -> TableDefinition:
        """One id per draft object, since everything else refers to them."""
        for refusal, ids in (
            (N_("Two columns of one table cannot share an id"), [column.id for column in self.columns]),
            (N_("Two indexes of one table cannot share an id"), [index.id for index in self.indexes]),
            (
                N_("Two constraints of one table cannot share an id"),
                [item.id for item in self.unique_constraints]
                + [item.id for item in self.checks]
                + [item.id for item in self.foreign_keys],
            ),
        ):
            if len(ids) != len(set(ids)):
                raise ValueError(say(refusal))
        return self


class PlanProblem(BaseModel):
    """Why a definition cannot become a table, next to what is wrong.

    The object is named by its draft id so the editor can select it, which is
    the difference between "this cannot be created" and a form that shows the
    reader where to look.
    """

    model_config = ConfigDict(extra="forbid")

    # None means the table itself rather than one of its objects.
    object_id: str | None = None
    field: str | None = None
    message: str
    # Whether the definition is wrong or the schema is simply occupied. The
    # two lead to different work — one is corrected, one is waited out or
    # renamed — and the status of a refused creation follows this rather than a
    # reading of the sentence.
    kind: Literal["invalid", "conflict"] = "invalid"


class DesignRefused(Exception):
    """The definition will not be created, and the reason is one problem."""

    def __init__(self, problem: PlanProblem) -> None:
        super().__init__(problem.message)
        self.problem = problem


class PlannedStatement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Which draft object this statement belongs to; None for the table itself.
    object_id: str | None = None
    title: str
    sql: str


class TablePlan(BaseModel):
    """What the definition would become, composed but not executed.

    This is not D46's rehearsal. Nothing runs: rolled-back DDL still takes
    locks and still fires whatever the server hangs off it, which is not a
    thing to do on every keystroke.
    """

    model_config = ConfigDict(extra="forbid")

    # Echoed from the request so a late answer to an earlier draft can be
    # dropped rather than shown as the current plan.
    revision: int = 0
    # Empty while the definition has problems: there is nothing to review, and
    # a fingerprint over a plan that was never composed would be a promise.
    fingerprint: str = ""
    statements: list[PlannedStatement] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    problems: list[PlanProblem] = Field(default_factory=list)


class TablePlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # The destination, as the catalog issued it.
    node_id: str = Field(min_length=1, max_length=512)
    definition: TableDefinition
    revision: int = Field(default=0, ge=0)


class TableDesignTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(min_length=1, max_length=512)
