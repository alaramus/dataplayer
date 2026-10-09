"""A table designed as a hypertable: the statements after CREATE TABLE (D207, H4).

The new table is planned as the empty hypertable `create_hypertable` would make
of it, through the same `plan_steps` the settings editor uses, so a hypertable
made in the designer follows the rules of one edited later. What comes back is
statement text, because the designer reviews SQL; values are literals composed
here and never text from the request.
"""

from dataclasses import dataclass

from psycopg import sql

from app.adapters.actions import ActionRefused
from app.adapters.hypertable_design import (
    ChosenByTimescale,
    ColumnstoreDesign,
    DurationUnit,
    HypertableDesign,
    NoColumns,
    OlderThan,
    OrderBy,
    OrderColumns,
    OrderKey,
    SegmentBy,
    SegmentColumns,
)
from app.adapters.hypertable_design import (
    HashDimensionDesign as HashDesign,
)
from app.adapters.postgres.inspection import PostgresReader
from app.adapters.postgres.timescale.api import (
    RoutineShape,
    extension_routine,
    extension_type,
)
from app.adapters.postgres.timescale.conversion_plan import by_range_shape, create_shape
from app.adapters.postgres.timescale.design_execution import columnstore_statements
from app.adapters.postgres.timescale.design_plan import (
    AddAgePolicy,
    AddHashDimension,
    AddReorderPolicy,
    ConfigureColumnstore,
    DesignStep,
    Duration,
    add_dimension_shape,
    by_hash_shape,
    plan_steps,
    step_shapes,
)
from app.adapters.postgres.timescale.design_state import (
    PER_CHUNK_DEFAULTS,
    ColumnFact,
    CurrentHypertable,
    DesignTarget,
    UniqueKey,
    duration_microseconds,
    interval_units,
    release,
)
from app.adapters.postgres.timescale.profile import discover, require_available
from app.adapters.table_design import HypertableOffer, TableHypertable

# The designer's codes for the types a time dimension may have, as PostgreSQL names them.
TIME_TYPES = {
    "timestamp": "timestamp without time zone",
    "timestamp_tz": "timestamp with time zone",
    "date": "date",
}
# The table does not exist while it is planned, so nothing reads its identity;
# the plan carries the name and the statements cast it.
_UNBORN = "1"
_ADD_POLICY = {"retention": "add_retention_policy", "compression": "add_compression_policy"}
_TITLES = {"retention": "Retention policy", "compression": "Columnstore policy"}


@dataclass(frozen=True)
class DraftColumn:
    name: str
    type_code: str
    array: bool
    not_null: bool


class CreationProblem(Exception):
    # Not a frozen dataclass: raising writes __traceback__ onto the exception.
    def __init__(self, message: str, object_id: str | None = None, field: str | None = "hypertable") -> None:
        super().__init__(message)
        self.message = message
        self.object_id = object_id
        self.field = field


@dataclass(frozen=True)
class CreationStatement:
    title: str
    sql: str


async def hypertable_offer(reader: PostgresReader) -> HypertableOffer:
    try:
        version = require_available(await discover(reader))
    except ActionRefused as refusal:
        return HypertableOffer(reason=refusal.message)
    units: list[DurationUnit] = ["minute", "hour", "day", "week"]
    return HypertableOffer(
        available=True,
        per_chunk_defaults=release(version) >= PER_CHUNK_DEFAULTS,
        interval_units=units,
        policy_units=["hour", "day", "week", "month", "year"],
    )


def _name(columns: dict[str, DraftColumn], draft_id: str, what: str) -> str:
    column = columns.get(draft_id)
    if column is None:
        raise CreationProblem(f"The {what} names a column that is not there")
    return column.name


def _design(
    hyper: TableHypertable, columns: dict[str, DraftColumn], index_names: dict[str, str],
) -> HypertableDesign:
    segment: SegmentBy = ChosenByTimescale()
    if hyper.segment_mode == "none":
        segment = NoColumns()
    elif hyper.segment_mode == "columns":
        if not hyper.segment_column_ids:
            raise CreationProblem("Choose the columns to segment by")
        segment = SegmentColumns(columns=[_name(columns, item, "segment list") for item in hyper.segment_column_ids])
    order: OrderBy = ChosenByTimescale()
    if hyper.order_mode == "columns":
        if not hyper.order_keys:
            raise CreationProblem("Choose the columns to order by")
        order = OrderColumns(columns=[
            OrderKey(column=_name(columns, key.column_id, "order list"),
                     descending=key.descending, nulls_first=key.nulls_first)
            for key in hyper.order_keys
        ])
    reorder = None
    if hyper.reorder_index_id is not None:
        reorder = index_names.get(hyper.reorder_index_id)
        if reorder is None:
            raise CreationProblem("The reorder policy names an index that is not there")
    return HypertableDesign(
        time_column=_name(columns, hyper.time_column_id, "time dimension"),
        chunk_interval=hyper.chunk_interval,
        hash_dimensions=[
            HashDesign(column=_name(columns, item.column_id, "hash dimension"), partitions=item.partitions)
            for item in hyper.hash_dimensions
        ],
        columnstore=ColumnstoreDesign(
            enabled=hyper.columnstore, segment_by=segment, order_by=order, merge_interval=hyper.merge_interval,
        ) if hyper.columnstore else ColumnstoreDesign(enabled=False),
        retention=None if hyper.retention is None else OlderThan(older_than=hyper.retention),
        columnstore_policy=None if hyper.columnstore_policy is None else OlderThan(older_than=hyper.columnstore_policy),
        reorder_index=reorder,
    )


def _unborn(
    schema: str, table: str, column: DraftColumn, design: HypertableDesign, version: str,
    columns: dict[str, DraftColumn], unique_keys: list[UniqueKey], index_names: dict[str, str],
) -> CurrentHypertable:
    """The empty hypertable `create_hypertable` makes of the new table, before anything else is set."""
    interval = design.chunk_interval
    microseconds = None if interval is None else duration_microseconds(interval)
    if interval is None or microseconds is None:
        raise CreationProblem("A chunk interval is counted in minutes, hours, days or weeks", field="chunk_interval")
    per_chunk_defaults = release(version) >= PER_CHUNK_DEFAULTS
    return CurrentHypertable(
        extension_version=version,
        target=DesignTarget(
            database_oid=_UNBORN, relation_oid=_UNBORN, schema_name=schema, table_name=table,
            column_name=column.name, column_type=TIME_TYPES[column.type_code],
        ),
        design=HypertableDesign(
            time_column=column.name, chunk_interval=interval,
            columnstore=ColumnstoreDesign(
                enabled=False, segment_by=ChosenByTimescale() if per_chunk_defaults else NoColumns(),
            ),
        ),
        interval_microseconds=microseconds,
        # Every type the designer offers has a default btree operator class.
        columns=tuple(ColumnFact(name=item.name, type=item.type_code, orderable=True) for item in columns.values()),
        unique_keys=tuple(unique_keys),
        indexes=tuple(index_names.values()),
        available_tablespaces=(),
        retention=None, compression=None, reorder=None,
        per_chunk_defaults=per_chunk_defaults,
        has_chunks=False,
        compressed_chunks=False,
    )


async def _schema(reader: PostgresReader, version: str, steps: tuple[DesignStep, ...]) -> str:
    """The extension's schema, from every routine the statements call, all of which must be usable."""
    dimension_info = await extension_type(reader, version, "_timescaledb_internal", "dimension_info")
    shapes: list[RoutineShape] = [create_shape(dimension_info), by_range_shape(dimension_info), *step_shapes(steps)]
    if any(isinstance(step, AddHashDimension) for step in steps):
        shapes.extend((add_dimension_shape(dimension_info), by_hash_shape(dimension_info)))
    schemas = {(await extension_routine(reader, version, shape)).schema_name for shape in dict.fromkeys(shapes)}
    if len(schemas) != 1:
        raise CreationProblem("The TimescaleDB API is split across schemas")
    return schemas.pop()


def _call(schema: str, routine: str, arguments: sql.Composable) -> str:
    return sql.SQL("SELECT {}({})").format(sql.Identifier(schema, routine), arguments).as_string()


def _render(schema: str, table: sql.Identifier, step: DesignStep) -> list[CreationStatement]:
    relation = sql.SQL("{}::pg_catalog.regclass").format(sql.Literal(table.as_string()))
    match step:
        case AddHashDimension(column=column, partitions=partitions):
            return [CreationStatement(f"Hash dimension {column}", sql.SQL(
                "SELECT dimension_id FROM {}({}, {}({}::pg_catalog.name, {}::pg_catalog.int4), false)"
            ).format(
                sql.Identifier(schema, "add_dimension"), relation, sql.Identifier(schema, "by_hash"),
                sql.Literal(column), sql.Literal(partitions),
            ).as_string())]
        case ConfigureColumnstore():
            return [CreationStatement("Columnstore", item.as_string()) for item in columnstore_statements(table, step)]
        case AddAgePolicy(kind=kind, older_than=older_than):
            return [CreationStatement(_TITLES[kind], _call(schema, _ADD_POLICY[kind], sql.SQL(
                "{}, {}::pg_catalog.interval, false"
            ).format(relation, sql.Literal(older_than.interval_value()))))]
        case AddReorderPolicy(index=index):
            return [CreationStatement("Reorder policy", _call(schema, "add_reorder_policy", sql.SQL(
                "{}, {}::pg_catalog.name, false"
            ).format(relation, sql.Literal(index))))]
    raise CreationProblem("This setting cannot be made while the table is created")


async def creation_statements(
    reader: PostgresReader, schema: str, table_name: str, hyper: TableHypertable,
    columns: dict[str, DraftColumn], unique_keys: list[UniqueKey], index_names: dict[str, str],
) -> list[CreationStatement]:
    """Raises CreationProblem for what the designer shows beside the object at fault."""
    try:
        version = require_available(await discover(reader))
    except ActionRefused as refusal:
        raise CreationProblem(refusal.message) from None
    time_column = columns.get(hyper.time_column_id)
    if time_column is None:
        raise CreationProblem("The time dimension names a column that is not there", field="time_column_id")
    if time_column.type_code not in TIME_TYPES or time_column.array:
        raise CreationProblem(
            f'"{time_column.name}" cannot partition a hypertable; choose a timestamp or date column',
            field="time_column_id",
        )
    if not time_column.not_null:
        raise CreationProblem(
            f'"{time_column.name}" partitions the hypertable, so it must have a value',
            object_id=hyper.time_column_id, field="not_null",
        )
    design = _design(hyper, columns, index_names)
    current = _unborn(schema, table_name, time_column, design, version, columns, unique_keys, index_names)
    if hyper.chunk_interval.unit not in interval_units(current.target):
        allowed = " or ".join(f"{unit}s" for unit in interval_units(current.target))
        raise CreationProblem(f"A chunk interval of this column is counted in {allowed}", field="chunk_interval")
    try:
        steps = plan_steps(current, design)
        routine_schema = await _schema(reader, version, steps)
    except ActionRefused as refusal:
        raise CreationProblem(refusal.message) from None
    table = sql.Identifier(schema, table_name)
    interval = Duration(amount=hyper.chunk_interval.amount, unit=hyper.chunk_interval.unit)
    # No default indexes: the designer shows the time index as one of the table's own.
    statements = [CreationStatement("Hypertable", sql.SQL(
        "SELECT hypertable_id FROM {}({}::pg_catalog.regclass, {}({}::pg_catalog.name, "
        "{}::pg_catalog.interval), false, false, false)"
    ).format(
        sql.Identifier(routine_schema, "create_hypertable"), sql.Literal(table.as_string()),
        sql.Identifier(routine_schema, "by_range"), sql.Literal(time_column.name),
        sql.Literal(interval.interval_value()),
    ).as_string())]
    for step in steps:
        statements.extend(_render(routine_schema, table, step))
    return statements
