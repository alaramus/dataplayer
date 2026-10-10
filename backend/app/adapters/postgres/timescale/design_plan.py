"""Plan the difference between a hypertable and its design, executing nothing (D207).

The steps run in one fixed order, chosen so each one finds what it needs:
policies go before the columnstore is turned off and are added after it is
turned on, a hash dimension is added before compression settings that may
name it, and integer_now is set before the age policies that need it.
"""

import asyncio
from typing import Annotated, Literal

from psycopg import sql
from pydantic import BaseModel, ConfigDict, Field

from app.adapters.actions import ActionRefused
from app.adapters.hypertable_design import (
    BIGINT_MAX,
    AgePolicyDesign,
    ChosenByTimescale,
    ColumnstoreDesign,
    DesignDuration,
    ExistingNow,
    HypertableDesign,
    IntegerSpan,
    KeptNow,
    NowTemplate,
    OlderThan,
    OrderBy,
    OrderColumns,
    OrderKey,
    SegmentBy,
    SegmentColumns,
    Span,
    SparseColumns,
    SparseIndexes,
)
from app.adapters.postgres.inspection import PostgresReader
from app.adapters.postgres.timescale.age_policy_plan import (
    COMPRESSION,
    RETENTION,
    AgePolicySpec,
)
from app.adapters.postgres.timescale.api import (
    RoutineShape,
    extension_routine,
    extension_type,
    lockable_view,
)
from app.adapters.postgres.timescale.conversion_plan import (
    conversion_column,
    conversion_plan,
    require_unique_indexes,
    time_index_exists,
)
from app.adapters.postgres.timescale.design_state import (
    ADD_COMPACTION,
    INTEGER_MAX,
    INTEGER_TYPES,
    NOW_TEMPLATES,
    REMOVE_COMPACTION,
    CurrentHypertable,
    TableCandidate,
    converted,
    duration_microseconds,
    interval_duration,
    interval_units,
    is_hypertable,
    policy_units,
    read_current,
    read_table,
    require_new_function,
    span_length,
)
from app.adapters.postgres.timescale.interval_plan import SET_INTERVAL
from app.adapters.postgres.timescale.plans import (
    AgePolicy,
    ConversionStrategy,
    ReviewedPlan,
    TimeDuration,
)
from app.adapters.protocol import AdapterError

_OID = r"^[1-9][0-9]{0,9}$"
PolicyKind = Literal["retention", "compression", "reorder", "compaction"]

# sql/ddl_api.sql, sql/policy_api.sql and sql/size_utils.sql, the same across the
# matrix. regclass 2205, name 19, integer 23, boolean 16; void 2278, record 2249.
SET_PARTITIONS = RoutineShape("set_number_partitions", "f", "2205 23 19", 2278)
ATTACH_TABLESPACE = RoutineShape("attach_tablespace", "f", "19 2205", 2278)
DETACH_TABLESPACE = RoutineShape("detach_tablespace", "f", "19 2205", 23)
ADD_REORDER = RoutineShape("add_reorder_policy", "f", "2205 19 16", 23)
REMOVE_REORDER = RoutineShape("remove_reorder_policy", "f", "2205 16", 2278)
# regproc 24.
SET_NOW = RoutineShape("set_integer_now_func", "f", "2205 24 16", 2278)
TEMPLATE_PHRASES: dict[NowTemplate, str] = {
    "epoch_seconds": "seconds since 1970",
    "epoch_milliseconds": "milliseconds since 1970",
    "epoch_microseconds": "microseconds since 1970",
}


def add_dimension_shape(dimension_info: str) -> RoutineShape:
    # The legacy overload takes a name second, so a call whose arguments are all
    # concrete cannot resolve to it.
    return RoutineShape(
        "add_dimension", "f", f"2205 {dimension_info} 16", 2249, returns_set=True, exclusive=False,
    )


def by_hash_shape(dimension_info: str) -> RoutineShape:
    return RoutineShape("by_hash", "f", "19 23", int(dimension_info))


class Duration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    amount: int = Field(strict=True, gt=0, le=2_147_483_647)
    unit: str = Field(pattern=r"^(second|minute|hour|day|week|month|year)$")

    def interval_value(self) -> str:
        return f"{self.amount} {self.unit}"


class Count(BaseModel):
    """A length in an integer time column's values."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    unit: Literal["integer"] = "integer"
    amount: int = Field(strict=True, gt=0, le=BIGINT_MAX)

    def interval_value(self) -> str:
        return str(self.amount)


Length = Duration | Count


def _duration(value: DesignDuration) -> Duration:
    return Duration(amount=value.amount, unit=value.unit)


def length_from(value: Span) -> Length:
    return Count(amount=int(value.amount)) if isinstance(value, IntegerSpan) else _duration(value)


class ConvertTable(BaseModel):
    """Turn the ordinary table into a hypertable; with rows, it moves them too and runs as a job."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    step: Literal["convert_table"] = "convert_table"
    column: str = Field(min_length=1, max_length=63)
    column_type: str = Field(min_length=1, max_length=100)
    interval: Length
    migrate: bool = Field(strict=True)
    column_not_null: bool = Field(strict=True)
    time_index_exists: bool = Field(strict=True)


class RemovePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    step: Literal["remove_policy"] = "remove_policy"
    kind: PolicyKind
    job_id: str = Field(pattern=_OID)


class AddHashDimension(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    step: Literal["add_hash_dimension"] = "add_hash_dimension"
    column: str = Field(min_length=1, max_length=63)
    partitions: int = Field(strict=True, gt=0)


class SetPartitions(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    step: Literal["set_partitions"] = "set_partitions"
    column: str = Field(min_length=1, max_length=63)
    partitions: int = Field(strict=True, gt=0)


class SetChunkInterval(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    step: Literal["set_chunk_interval"] = "set_chunk_interval"
    interval: Length


class ConfigureColumnstore(BaseModel):
    """Enable the columnstore or change its settings, always stating both lists whole.

    Before 2.20 an `ALTER TABLE` that leaves a list out derives a default for it
    again, from indexes and statistics: changing only the merge interval once
    produced a segment column that was already an order column, and the source
    refused. So every change repeats both lists when they are named, and the
    `*_changed` flags say only what the preview reports.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    step: Literal["configure_columnstore"] = "configure_columnstore"
    enable: bool = Field(strict=True)
    segment_by: SegmentBy
    order_by: OrderBy
    segment_changed: bool = Field(strict=True)
    order_changed: bool = Field(strict=True)
    # None stops merging chunks as they are compressed.
    merge_interval: Duration | None
    merge_changed: bool = Field(strict=True)
    sparse_indexes: SparseIndexes = Field(default_factory=ChosenByTimescale)
    sparse_changed: bool = Field(default=False, strict=True)


class DisableColumnstore(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    step: Literal["disable_columnstore"] = "disable_columnstore"


class AttachTablespace(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    step: Literal["attach_tablespace"] = "attach_tablespace"
    name: str = Field(min_length=1, max_length=63)


class DetachTablespace(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    step: Literal["detach_tablespace"] = "detach_tablespace"
    name: str = Field(min_length=1, max_length=63)


class AddAgePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    step: Literal["add_age_policy"] = "add_age_policy"
    kind: Literal["retention", "compression"]
    older_than: Length


class AddCompactionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    step: Literal["add_compaction_policy"] = "add_compaction_policy"


class AddReorderPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    step: Literal["add_reorder_policy"] = "add_reorder_policy"
    index: str = Field(min_length=1, max_length=63)


class CreateNowFunction(BaseModel):
    """A function made from one of the server's templates; nothing in it comes from the request (D207)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    step: Literal["create_now_function"] = "create_now_function"
    schema_name: str = Field(min_length=1, max_length=63)
    name: str = Field(min_length=1, max_length=63)
    template: NowTemplate
    column_type: str = Field(pattern=r"^(smallint|integer|bigint)$")


class SetIntegerNow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    step: Literal["set_integer_now"] = "set_integer_now"
    schema_name: str = Field(min_length=1, max_length=63)
    name: str = Field(min_length=1, max_length=63)
    replace: bool = Field(strict=True)


DesignStep = Annotated[
    ConvertTable | RemovePolicy | AddHashDimension | SetPartitions | SetChunkInterval | ConfigureColumnstore
    | DisableColumnstore | AttachTablespace | DetachTablespace | CreateNowFunction | SetIntegerNow
    | AddAgePolicy | AddReorderPolicy | AddCompactionPolicy,
    Field(discriminator="step"),
]

# The steps that change TimescaleDB's jobs, which wait behind DataPlayer's job guard (D211).
POLICY_STEPS = (RemovePolicy, AddAgePolicy, AddReorderPolicy, AddCompactionPolicy)


class RoutineUse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=63)
    oid: str = Field(pattern=_OID)


class DesignStrategy(BaseModel):
    """What execution calls, as discovered for this plan's steps and nothing else."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Literal["hypertable_design_v1"] = "hypertable_design_v1"
    extension_version: str
    function_schema: str | None = Field(default=None, min_length=1, max_length=63)
    routines: tuple[RoutineUse, ...] = ()
    dimensions_view_oid: str | None = Field(default=None, pattern=_OID)
    conversion: ConversionStrategy | None = None


class HypertableDesignPlan(ReviewedPlan):
    operation: Literal["design_hypertable"] = "design_hypertable"
    current: CurrentHypertable
    requested: HypertableDesign
    steps: tuple[DesignStep, ...]
    strategy: DesignStrategy

    @property
    def locks_table_exclusively(self) -> bool:
        return any(
            isinstance(step, ConvertTable | ConfigureColumnstore | DisableColumnstore | AddHashDimension)
            for step in self.steps
        )

    @property
    def migrates(self) -> bool:
        """Whether rows are moved, which makes the plan a job rather than a request (D207)."""
        return any(isinstance(step, ConvertTable) and step.migrate for step in self.steps)

    @property
    def coordination(self) -> str:
        if self.locks_table_exclusively:
            return "Locks this hypertable exclusively while it changes; its reads and writes wait until it commits"
        if self.strategy.dimensions_view_oid is not None:
            return "Briefly locks TimescaleDB metadata across this database; new chunk creation may wait"
        if any(isinstance(step, POLICY_STEPS) for step in self.steps):
            return (
                "Other policy changes made here in this database wait until it commits, "
                "and so may a policy run starting meanwhile"
            )
        return "Other changes to this hypertable's settings wait until it commits"


def _refuse(message: str) -> ActionRefused:
    return ActionRefused("not_applicable", message)


def _same(left: Span | None, right: Span | None) -> bool:
    if left is None or right is None:
        return left is right
    if isinstance(left, IntegerSpan) or isinstance(right, IntegerSpan):
        return (
            isinstance(left, IntegerSpan) and isinstance(right, IntegerSpan)
            and int(left.amount) == int(right.amount)
        )
    fixed = duration_microseconds(left), duration_microseconds(right)
    if fixed[0] is not None and fixed[1] is not None:
        return fixed[0] == fixed[1]
    months = {"month": 1, "year": 12}
    return (
        left.unit in months and right.unit in months
        and left.amount * months[left.unit] == right.amount * months[right.unit]
    )


def _chunk_interval(current: CurrentHypertable, requested: Span | None) -> list[DesignStep]:
    if requested is None or _same(requested, current.design.chunk_interval):
        return []
    if current.integer:
        span_length(current.target.column_type, requested)
        return [SetChunkInterval(interval=length_from(requested))]
    if isinstance(requested, IntegerSpan) or requested.unit not in interval_units(current.target):
        allowed = " or ".join(f"{unit}s" for unit in interval_units(current.target))
        raise _refuse(f"A chunk interval of this hypertable is counted in {allowed}")
    return [SetChunkInterval(interval=_duration(requested))]


def _orderable(current: CurrentHypertable, name: str, use: str) -> None:
    column = current.column(name)
    if column is None:
        raise _refuse(f'This hypertable has no column "{name}"')
    if not column.orderable:
        raise _refuse(f'Column "{name}" has a type that cannot be used as {use}')


def _dimensions(current: CurrentHypertable, requested: HypertableDesign) -> list[DesignStep]:
    existing = {item.column: item.partitions for item in current.design.hash_dimensions}
    wanted = {item.column: item.partitions for item in requested.hash_dimensions}
    removed = [name for name in existing if name not in wanted]
    if removed:
        raise _refuse(f'TimescaleDB cannot remove the hash dimension on "{removed[0]}"')
    steps: list[DesignStep] = []
    for item in requested.hash_dimensions:
        if item.column in existing:
            if existing[item.column] != item.partitions:
                steps.append(SetPartitions(column=item.column, partitions=item.partitions))
            continue
        if current.has_chunks:
            raise _refuse("A hash dimension can only be added while the hypertable holds no chunks")
        if item.column == current.target.column_name:
            raise _refuse("The time column cannot also be a hash dimension")
        _orderable(current, item.column, "a hash dimension")
        for key in current.unique_keys:
            if item.column not in key.columns:
                raise _refuse(
                    f'Unique key "{key.name}" must include "{item.column}" before it can be a hash dimension',
                )
        steps.append(AddHashDimension(column=item.column, partitions=item.partitions))
    return steps


def _validated_sparse(current: CurrentHypertable, requested: SparseIndexes) -> None:
    if isinstance(requested, ChosenByTimescale):
        return
    if not current.sparse_indexes_supported:
        raise _refuse(f"TimescaleDB {current.extension_version} has no sparse indexes; they arrived in 2.22")
    if not isinstance(requested, SparseColumns):
        return
    seen: set[tuple[str, str]] = set()
    for index in requested.indexes:
        if current.column(index.column) is None:
            raise _refuse(f'This hypertable has no column "{index.column}"')
        if index.kind == "minmax":
            _orderable(current, index.column, "a minmax sparse index")
        if (index.column, index.kind) in seen:
            raise _refuse(f'Column "{index.column}" has the same sparse index twice')
        seen.add((index.column, index.kind))


def _validated_columnstore(current: CurrentHypertable, requested: ColumnstoreDesign) -> None:
    _validated_sparse(current, requested.sparse_indexes)
    # Timescale's own rule, "cannot set sparse index option without orderby option".
    if not isinstance(requested.sparse_indexes, ChosenByTimescale) and not isinstance(requested.order_by, OrderColumns):
        raise _refuse("Sparse indexes need the order to be named; choose the columns to order by")
    named: list[str] = []
    if isinstance(requested.segment_by, SegmentColumns):
        for name in requested.segment_by.columns:
            _orderable(current, name, "a segment column")
            named.append(name)
    if isinstance(requested.order_by, OrderColumns):
        for key in requested.order_by.columns:
            _orderable(current, key.column, "an order column")
            named.append(key.column)
    repeated = next((name for name in named if named.count(name) > 1), None)
    if repeated is not None:
        raise _refuse(f'Column "{repeated}" is listed more than once in the columnstore settings')


def _effective_order(current: CurrentHypertable, segment: SegmentBy, order: OrderBy) -> OrderBy:
    # The rule Timescale applies itself (add_time_to_order_by_if_not_included in
    # tsl/src/compression/create.c): an explicit order without the time column gets
    # it appended descending. Planned here so the plan says what the source will hold.
    if not isinstance(order, OrderColumns):
        return order
    time_column = current.target.column_name
    segmented = isinstance(segment, SegmentColumns) and time_column in segment.columns
    if segmented or any(key.column == time_column for key in order.columns):
        return order
    return OrderColumns(columns=[*order.columns, OrderKey(column=time_column, descending=True, nulls_first=True)])


def _columnstore(current: CurrentHypertable, requested: HypertableDesign) -> list[DesignStep]:
    now, wanted = current.design.columnstore, requested.columnstore
    if not wanted.enabled:
        if not now.enabled:
            return []
        if current.compressed_chunks:
            raise _refuse("The columnstore cannot be turned off while chunks are compressed; decompress them first")
        return [DisableColumnstore()]
    _validated_columnstore(current, wanted)
    order = _effective_order(current, wanted.segment_by, wanted.order_by)
    segment_changed = not now.enabled or wanted.segment_by != now.segment_by
    order_changed = not now.enabled or order != now.order_by
    merge_changed = not _same(wanted.merge_interval, now.merge_interval if now.enabled else None)
    sparse_changed = (
        wanted.sparse_indexes != now.sparse_indexes if now.enabled
        else not isinstance(wanted.sparse_indexes, ChosenByTimescale)
    )
    back_to_default = now.enabled and (
        (segment_changed and isinstance(wanted.segment_by, ChosenByTimescale))
        or (order_changed and isinstance(order, ChosenByTimescale))
    )
    if back_to_default and not current.per_chunk_defaults:
        raise _refuse(
            f"TimescaleDB {current.extension_version} cannot return a setting to its own choice; "
            "name the columns instead",
        )
    if wanted.merge_interval is not None and current.integer:
        raise _refuse("Merging compressed chunks is set in time, which an integer column does not count in")
    if wanted.merge_interval is not None and merge_changed:
        _merge_interval(current, requested, wanted.merge_interval)
    if now.enabled and not (segment_changed or order_changed or merge_changed or sparse_changed):
        return []
    return [ConfigureColumnstore(
        enable=not now.enabled,
        segment_by=wanted.segment_by,
        order_by=order,
        segment_changed=segment_changed,
        order_changed=order_changed,
        merge_interval=None if wanted.merge_interval is None else _duration(wanted.merge_interval),
        merge_changed=merge_changed,
        sparse_indexes=wanted.sparse_indexes,
        sparse_changed=sparse_changed,
    )]


def _merge_interval(current: CurrentHypertable, requested: HypertableDesign, merge: DesignDuration) -> None:
    if merge.unit not in interval_units(current.target):
        raise _refuse("A merge interval is counted in the units of the chunk interval")
    chunk = requested.chunk_interval or current.design.chunk_interval
    merged = duration_microseconds(merge)
    single = duration_microseconds(chunk) if isinstance(chunk, DesignDuration) else None
    if merged is not None and single is not None and (merged <= single or merged % single != 0):
        raise _refuse("The merge interval must be a whole multiple of the chunk interval, larger than it")


def _age_policy(
    spec: AgePolicySpec, existing: AgePolicy | None, design: AgePolicyDesign | None,
    current: CurrentHypertable,
) -> tuple[list[DesignStep], list[DesignStep]]:
    """The removal and the addition one policy needs, each possibly empty."""
    if design is None:
        return ([RemovePolicy(kind=spec.kind, job_id=existing.job_id)] if existing else []), []
    if not isinstance(design, OlderThan):
        if existing is None:
            raise _refuse(f"There is no {spec.noun} to keep")
        return [], []
    wanted = design.older_than
    if existing is not None and existing.scheduled and _same(_existing_age(existing), wanted):
        return [], []
    column_type = current.target.column_type
    if current.integer:
        if not isinstance(wanted, IntegerSpan):
            raise _refuse(f"The {spec.noun} of an integer column is a number of its values")
        if int(wanted.amount) > INTEGER_MAX[column_type]:
            raise _refuse(f"The {spec.noun} of a {column_type} column is at most {INTEGER_MAX[column_type]:,}")
    elif isinstance(wanted, IntegerSpan) or wanted.unit not in policy_units(current.target):
        unit = "plain numbers" if isinstance(wanted, IntegerSpan) else f"{wanted.unit}s"
        raise _refuse(f"The {spec.noun} of a {column_type} column cannot count in {unit}")
    # A replacement is scheduled by default, so replacing a paused policy would resume it.
    if existing is not None and not existing.scheduled:
        raise _refuse(f"The existing {spec.noun} is paused; remove it before setting a new one")
    removal: list[DesignStep] = [] if existing is None else [RemovePolicy(kind=spec.kind, job_id=existing.job_id)]
    return removal, [AddAgePolicy(kind=spec.kind, older_than=length_from(wanted))]


def _existing_age(existing: AgePolicy) -> Span | None:
    if existing.older_than is not None:
        return interval_duration(existing.older_than)
    if existing.older_than_count is not None and int(existing.older_than_count) <= BIGINT_MAX:
        return IntegerSpan(amount=existing.older_than_count)
    return None


def _reorder(current: CurrentHypertable, requested: HypertableDesign) -> tuple[list[DesignStep], list[DesignStep]]:
    existing, wanted = current.reorder, requested.reorder_index
    if existing is not None and existing.index_name is not None and existing.index_name == wanted:
        return [], []
    if wanted is not None and wanted not in current.indexes:
        raise _refuse(f'This hypertable has no index "{wanted}"')
    # A replacement is scheduled by default, so replacing a paused policy would resume it.
    if existing is not None and not existing.scheduled and wanted is not None:
        raise _refuse("The existing reorder policy is paused; remove it before setting a new one")
    removal: list[DesignStep] = [] if existing is None else [RemovePolicy(kind="reorder", job_id=existing.job_id)]
    return removal, ([] if wanted is None else [AddReorderPolicy(index=wanted)])


def _tablespaces(current: CurrentHypertable, requested: HypertableDesign) -> list[DesignStep]:
    now, wanted = current.design.tablespaces, requested.tablespaces
    unknown = next((name for name in wanted if name not in now and name not in current.available_tablespaces), None)
    if unknown is not None:
        raise _refuse(f'Tablespace "{unknown}" does not exist or this connection may not create in it')
    return [
        *(DetachTablespace(name=name) for name in now if name not in wanted),
        *(AttachTablespace(name=name) for name in wanted if name not in now),
    ]


def _integer_now(current: CurrentHypertable, requested: HypertableDesign) -> list[DesignStep]:
    wanted, now = requested.integer_now, current.design.integer_now
    if not current.integer:
        if wanted is not None:
            raise _refuse("Only a hypertable partitioned by an integer column takes an integer_now function")
        return []
    column_type = current.target.column_type
    if wanted is None:
        if now is not None:
            raise _refuse("TimescaleDB cannot take an integer_now function away; keep it or choose another")
        return []
    if isinstance(wanted, KeptNow):
        if now is None:
            raise _refuse("There is no integer_now function to keep")
        return []
    if isinstance(wanted, ExistingNow):
        if wanted == now:
            return []
        if not any(
            item.schema_name == wanted.schema_name and item.name == wanted.name for item in current.now_functions
        ):
            raise _refuse(
                f'{_routine(wanted.schema_name, wanted.name)} is not a function TimescaleDB accepts as '
                f"integer_now of a {column_type} column",
            )
        return [SetIntegerNow(schema_name=wanted.schema_name, name=wanted.name, replace=now is not None)]
    if wanted.template not in NOW_TEMPLATES[column_type]:
        raise _refuse(f"A {column_type} column cannot hold the {TEMPLATE_PHRASES[wanted.template]}")
    schema = current.target.schema_name
    return [
        CreateNowFunction(
            schema_name=schema, name=wanted.name, template=wanted.template,
            column_type=column_type,
        ),
        SetIntegerNow(schema_name=schema, name=wanted.name, replace=now is not None),
    ]


def _routine(schema_name: str, name: str) -> str:
    return sql.Identifier(schema_name, name).as_string() + "()"


def _compaction(current: CurrentHypertable, requested: HypertableDesign) -> tuple[list[DesignStep], list[DesignStep]]:
    existing = current.compaction
    if not requested.compaction_policy:
        return ([RemovePolicy(kind="compaction", job_id=existing.job_id)] if existing else []), []
    if existing is not None:
        return [], []
    if not current.compaction_supported:
        raise _refuse(f"TimescaleDB {current.extension_version} has no compaction policy; it arrived in 2.29")
    if not requested.columnstore.enabled:
        raise _refuse("A compaction policy merges compressed chunks; turn the columnstore on")
    return [], [AddCompactionPolicy()]


def plan_steps(current: CurrentHypertable, requested: HypertableDesign) -> tuple[DesignStep, ...]:
    if requested.columnstore_policy is not None and not requested.columnstore.enabled:
        raise _refuse("Remove the columnstore policy to turn the columnstore off")
    if requested.compaction_policy and not requested.columnstore.enabled:
        raise _refuse("Remove the compaction policy to turn the columnstore off")
    retention = _age_policy(RETENTION, current.retention, requested.retention, current)
    compression = _age_policy(COMPRESSION, current.compression, requested.columnstore_policy, current)
    reorder = _reorder(current, requested)
    compaction = _compaction(current, requested)
    if current.integer and requested.integer_now is None and (retention[1] or compression[1]):
        raise _refuse("An age policy on an integer column needs an integer_now function to tell the current value")
    return (
        *retention[0], *compression[0], *reorder[0], *compaction[0],
        *_dimensions(current, requested),
        *_chunk_interval(current, requested.chunk_interval),
        *_columnstore(current, requested),
        *_tablespaces(current, requested),
        *_integer_now(current, requested),
        *retention[1], *compression[1], *reorder[1], *compaction[1],
    )


async def require_new_functions(reader: PostgresReader, steps: tuple[DesignStep, ...]) -> None:
    """What planning cannot see in the current state: whether a new function's name is free."""
    for step in steps:
        if isinstance(step, CreateNowFunction):
            await require_new_function(reader, step.schema_name, step.name)


def step_shapes(steps: tuple[DesignStep, ...]) -> list[RoutineShape]:
    shapes: list[RoutineShape] = []
    for step in steps:
        match step:
            case RemovePolicy(kind="retention"):
                shapes.append(RETENTION.remove)
            case RemovePolicy(kind="compression"):
                shapes.append(COMPRESSION.remove)
            case RemovePolicy(kind="reorder"):
                shapes.append(REMOVE_REORDER)
            case RemovePolicy(kind="compaction"):
                shapes.append(REMOVE_COMPACTION)
            case AddCompactionPolicy():
                shapes.append(ADD_COMPACTION)
            case AddAgePolicy(kind="retention"):
                shapes.append(RETENTION.add)
            case AddAgePolicy(kind="compression"):
                shapes.append(COMPRESSION.add)
            case AddReorderPolicy():
                shapes.append(ADD_REORDER)
            case SetPartitions():
                shapes.append(SET_PARTITIONS)
            case SetChunkInterval():
                shapes.append(SET_INTERVAL)
            case AttachTablespace():
                shapes.append(ATTACH_TABLESPACE)
            case DetachTablespace():
                shapes.append(DETACH_TABLESPACE)
            case SetIntegerNow():
                shapes.append(SET_NOW)
            case _:
                pass
    return shapes


async def _strategy(
    reader: PostgresReader, current: CurrentHypertable, steps: tuple[DesignStep, ...],
) -> DesignStrategy:
    version = current.extension_version
    shapes = step_shapes(steps)
    if any(isinstance(step, AddHashDimension) for step in steps):
        dimension_info = await extension_type(reader, version, "_timescaledb_internal", "dimension_info")
        shapes.extend((add_dimension_shape(dimension_info), by_hash_shape(dimension_info)))
    routines: list[RoutineUse] = []
    schema: str | None = None
    for shape in dict.fromkeys(shapes):
        routine = await extension_routine(reader, version, shape)
        schema = routine.schema_name
        routines.append(RoutineUse(name=shape.name, oid=routine.oid))
    dimensions = any(
        isinstance(step, SetChunkInterval | SetPartitions | AddHashDimension | SetIntegerNow) for step in steps
    )
    return DesignStrategy(
        extension_version=version,
        function_schema=schema,
        routines=tuple(routines),
        dimensions_view_oid=await lockable_view(reader, version, "dimensions") if dimensions else None,
    )


def _conversion(candidate: TableCandidate, requested: HypertableDesign) -> tuple[CurrentHypertable, ConvertTable]:
    """The conversion step, and the hypertable it leaves for every other step to plan against."""
    if requested.time_column is None:
        raise _refuse("Choose the time column the table is partitioned by")
    if requested.chunk_interval is None:
        raise _refuse("Choose the chunk interval")
    interval = requested.chunk_interval
    state = candidate.conversion
    column = conversion_column(state, requested.time_column)
    if column.type in INTEGER_TYPES:
        require_unique_indexes(state, column)
    elif column.type == "uuid":
        # Partitioned by the time inside a UUIDv7, so its intervals are durations.
        if isinstance(interval, IntegerSpan) or duration_microseconds(interval) is None:
            raise _refuse("A chunk interval is counted in minutes, hours, days or weeks")
        require_unique_indexes(state, column)
    else:
        if isinstance(interval, IntegerSpan) or duration_microseconds(interval) is None:
            raise _refuse("A chunk interval is counted in minutes, hours, days or weeks")
        # The single-purpose conversion's own rules: the unit for the column's
        # type and every unique index holding it.
        conversion_plan(state, column.name, TimeDuration(amount=interval.amount, unit=interval.unit))
    current = converted(candidate, column, interval)
    if isinstance(interval, DesignDuration) and interval.unit not in interval_units(current.target):
        allowed = " or ".join(f"{unit}s" for unit in interval_units(current.target))
        raise _refuse(f"A chunk interval of this column is counted in {allowed}")
    return current, ConvertTable(
        column=column.name,
        column_type=column.type,
        interval=length_from(interval),
        migrate=not state.empty,
        column_not_null=column.not_null,
        time_index_exists=time_index_exists(state, column),
    )


async def plan_design(
    reader: PostgresReader, schema_name: str, table_name: str, requested: HypertableDesign,
) -> HypertableDesignPlan:
    try:
        async with asyncio.timeout(5):
            if await is_hypertable(reader, schema_name, table_name):
                current = await read_current(reader, schema_name, table_name)
                if requested.time_column not in (None, current.target.column_name):
                    raise _refuse("TimescaleDB cannot change the time column of a hypertable")
                steps = plan_steps(current, requested)
                await require_new_functions(reader, steps)
                strategy = await _strategy(reader, current, steps)
            else:
                candidate = await read_table(reader, schema_name, table_name)
                current, conversion = _conversion(candidate, requested)
                steps = (conversion, *plan_steps(current, requested))
                await require_new_functions(reader, steps)
                strategy = (await _strategy(reader, current, steps)).model_copy(
                    update={"conversion": candidate.conversion.strategy},
                )
            return HypertableDesignPlan(current=current, requested=requested, steps=steps, strategy=strategy)
    except TimeoutError:
        raise _refuse("Planning the hypertable change timed out") from None
    except (AdapterError, ValueError):
        raise _refuse("The hypertable could not be inspected safely") from None

