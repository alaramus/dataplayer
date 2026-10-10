"""The difference between a hypertable and its design, planned without a source (D207)."""

from typing import Any

import pytest

from app.adapters.actions import ActionRefused
from app.adapters.hypertable_design import (
    ChosenByTimescale,
    ColumnstoreDesign,
    DesignDuration,
    ExistingNow,
    HashDimensionDesign,
    HypertableDesign,
    IntegerSpan,
    KeptAsItIs,
    KeptNow,
    NoColumns,
    NowFunction,
    OlderThan,
    OrderColumns,
    OrderKey,
    SegmentColumns,
    SparseColumns,
    SparseIndex,
    TemplateNow,
)
from app.adapters.postgres.timescale.design_plan import (
    AddAgePolicy,
    AddCompactionPolicy,
    AddHashDimension,
    AddReorderPolicy,
    AttachTablespace,
    ConfigureColumnstore,
    Count,
    CreateNowFunction,
    DetachTablespace,
    DisableColumnstore,
    RemovePolicy,
    SetChunkInterval,
    SetIntegerNow,
    SetPartitions,
    plan_steps,
)
from app.adapters.postgres.timescale.design_state import (
    ColumnFact,
    CompactionPolicy,
    CurrentHypertable,
    DesignTarget,
    ReorderPolicy,
    UniqueKey,
    fixed_duration,
    interval_duration,
    sparse_indexes,
)
from app.adapters.postgres.timescale.plans import AgePolicy

WEEK = DesignDuration(amount=1, unit="week")
TARGET = DesignTarget(
    database_oid="1", relation_oid="2", schema_name="lab", table_name="events",
    column_name="observed_at", column_type="timestamp with time zone",
)


def state(**changes: Any) -> CurrentHypertable:
    fields: dict[str, Any] = {
        "extension_version": "2.30.0",
        "target": TARGET,
        "design": HypertableDesign(chunk_interval=WEEK),
        "interval_length": 604_800_000_000,
        "columns": (
            ColumnFact(name="observed_at", type="timestamp with time zone", orderable=True),
            ColumnFact(name="device", type="integer", orderable=True),
            ColumnFact(name="payload", type="json", orderable=False),
        ),
        "unique_keys": (),
        "indexes": ("events_device",),
        "available_tablespaces": ("pg_default", "fast"),
        "retention": None,
        "compression": None,
        "reorder": None,
        "per_chunk_defaults": True,
        "has_chunks": True,
        "compressed_chunks": False,
    }
    fields.update(changes)
    return CurrentHypertable(**fields)


def policy(older_than: str | None = "7 days", *, scheduled: bool = True) -> AgePolicy:
    return AgePolicy(
        job_id="1000", scheduled=scheduled, schedule_interval="1 day",
        older_than=older_than, created_before=None if older_than else "30 days",
    )


def design(**changes: Any) -> HypertableDesign:
    return HypertableDesign(chunk_interval=WEEK).model_copy(update=changes)


def refused(current: CurrentHypertable, requested: HypertableDesign) -> str:
    with pytest.raises(ActionRefused) as refusal:
        plan_steps(current, requested)
    return refusal.value.message


@pytest.mark.parametrize("text,expected", [
    ("7 days", DesignDuration(amount=1, unit="week")),
    ("10 days", DesignDuration(amount=10, unit="day")),
    ("1 mon", DesignDuration(amount=1, unit="month")),
    ("24 mons", DesignDuration(amount=2, unit="year")),
    ("3 years", DesignDuration(amount=3, unit="year")),
    ("06:00:00", DesignDuration(amount=6, unit="hour")),
    ("00:30:00", DesignDuration(amount=30, unit="minute")),
    ("1 day 02:00:00", None),
    ("1 year 2 mons", None),
    ("00:00:00.5", None),
])
def test_only_a_threshold_of_one_field_becomes_a_duration(text: str, expected: DesignDuration | None) -> None:
    assert interval_duration(text) == expected


def test_a_fixed_length_takes_its_largest_whole_unit() -> None:
    assert fixed_duration(604_800_000_000) == DesignDuration(amount=1, unit="week")
    assert fixed_duration(129_600_000_000) == DesignDuration(amount=36, unit="hour")
    assert fixed_duration(1_500_000) is None


def test_an_unchanged_design_plans_nothing() -> None:
    assert plan_steps(state(), design()) == ()


def test_steps_run_in_an_order_each_one_can_rely_on() -> None:
    current = state(
        retention=policy("7 days"), compression=policy("3 days"),
        design=HypertableDesign(
            chunk_interval=WEEK, columnstore=ColumnstoreDesign(enabled=True, segment_by=ChosenByTimescale()),
            retention=OlderThan(older_than=WEEK),
            columnstore_policy=OlderThan(older_than=DesignDuration(amount=3, unit="day")),
            tablespaces=["pg_default"],
        ),
    )
    steps = plan_steps(current, design(
        chunk_interval=DesignDuration(amount=2, unit="day"),
        columnstore=ColumnstoreDesign(enabled=True, segment_by=SegmentColumns(columns=["device"])),
        retention=OlderThan(older_than=DesignDuration(amount=30, unit="day")),
        columnstore_policy=OlderThan(older_than=DesignDuration(amount=3, unit="day")),
        reorder_index="events_device",
        tablespaces=["fast"],
    ))

    assert [type(step) for step in steps] == [
        RemovePolicy, SetChunkInterval, ConfigureColumnstore, DetachTablespace, AttachTablespace,
        AddAgePolicy, AddReorderPolicy,
    ]
    assert steps[0] == RemovePolicy(kind="retention", job_id="1000")


def test_turning_the_columnstore_on_states_both_lists_and_appends_time() -> None:
    (step,) = plan_steps(state(), design(columnstore=ColumnstoreDesign(
        enabled=True, segment_by=NoColumns(),
        order_by=OrderColumns(columns=[OrderKey(column="device", descending=False, nulls_first=False)]),
    )))

    assert isinstance(step, ConfigureColumnstore) and step.enable
    assert step.segment_by == NoColumns()
    assert step.order_by == OrderColumns(columns=[
        OrderKey(column="device", descending=False, nulls_first=False),
        OrderKey(column="observed_at", descending=True, nulls_first=True),
    ])


def test_a_merge_interval_alone_still_repeats_both_lists() -> None:
    enabled = ColumnstoreDesign(enabled=True, segment_by=SegmentColumns(columns=["device"]))
    current = state(design=design(columnstore=enabled))
    (step,) = plan_steps(current, design(columnstore=enabled.model_copy(update={
        "merge_interval": DesignDuration(amount=2, unit="week"),
    })))

    assert isinstance(step, ConfigureColumnstore)
    assert step.segment_by == SegmentColumns(columns=["device"])
    assert (step.segment_changed, step.order_changed, step.merge_changed) == (False, False, True)


@pytest.mark.parametrize("merge", [DesignDuration(amount=5, unit="day"), WEEK])
def test_a_merge_interval_is_a_larger_multiple_of_the_chunk(merge: DesignDuration) -> None:
    requested = design(columnstore=ColumnstoreDesign(enabled=True, merge_interval=merge))
    assert "whole multiple of the chunk interval" in refused(state(), requested)


def test_an_older_release_cannot_go_back_to_its_own_choice() -> None:
    enabled = ColumnstoreDesign(enabled=True, segment_by=SegmentColumns(columns=["device"]))
    current = state(design=design(columnstore=enabled), per_chunk_defaults=False, extension_version="2.19.3")
    requested = design(columnstore=enabled.model_copy(update={"segment_by": ChosenByTimescale()}))

    assert "2.19.3 cannot return a setting to its own choice" in refused(current, requested)


def test_columns_are_checked_against_the_table() -> None:
    assert 'no column "missing"' in refused(state(), design(columnstore=ColumnstoreDesign(
        enabled=True, segment_by=SegmentColumns(columns=["missing"]),
    )))
    assert '"payload" has a type that cannot be used' in refused(state(), design(columnstore=ColumnstoreDesign(
        enabled=True, segment_by=SegmentColumns(columns=["payload"]),
    )))
    assert 'Column "device" is listed more than once' in refused(state(), design(columnstore=ColumnstoreDesign(
        enabled=True, segment_by=SegmentColumns(columns=["device"]),
        order_by=OrderColumns(columns=[OrderKey(column="device", descending=True, nulls_first=True)]),
    )))


def test_the_columnstore_turns_off_without_compressed_chunks_or_its_policy() -> None:
    enabled = design(columnstore=ColumnstoreDesign(enabled=True))
    with_policy = state(design=enabled.model_copy(update={"columnstore_policy": OlderThan(older_than=WEEK)}),
                        compression=policy())
    off = design(columnstore=ColumnstoreDesign(enabled=False), columnstore_policy=OlderThan(older_than=WEEK))
    assert "Remove the columnstore policy" in refused(with_policy, off)

    compressed = state(design=enabled, compressed_chunks=True)
    assert "decompress them first" in refused(compressed, design())

    assert plan_steps(state(design=enabled), design()) == (DisableColumnstore(),)


def test_an_emptied_policy_is_removed_and_a_kept_one_is_left() -> None:
    current = state(
        retention=policy("1 day 02:00:00"), reorder=ReorderPolicy(job_id="1001", scheduled=True, index_name="x"),
        design=design(retention=KeptAsItIs(), reorder_index="x"),
    )
    assert plan_steps(current, design(retention=KeptAsItIs(), reorder_index="x")) == ()
    assert plan_steps(current, design()) == (
        RemovePolicy(kind="retention", job_id="1000"), RemovePolicy(kind="reorder", job_id="1001"),
    )
    assert "no retention policy to keep" in refused(state(), design(retention=KeptAsItIs()))


def test_a_paused_policy_is_not_replaced_behind_its_back() -> None:
    current = state(retention=policy(scheduled=False), design=design(retention=KeptAsItIs()))
    requested = design(retention=OlderThan(older_than=DesignDuration(amount=2, unit="week")))
    assert "paused; remove it" in refused(current, requested)


def test_a_date_dimension_refuses_hours() -> None:
    dated = state(target=TARGET.model_copy(update={"column_type": "date"}))
    assert "cannot count in hours" in refused(
        dated, design(retention=OlderThan(older_than=DesignDuration(amount=6, unit="hour"))),
    )
    assert "counted in days or weeks" in refused(dated, design(chunk_interval=DesignDuration(amount=6, unit="hour")))


def test_hash_dimensions_are_added_only_while_empty_and_never_removed() -> None:
    hashed = [HashDimensionDesign(column="device", partitions=4)]
    assert "holds no chunks" in refused(state(), design(hash_dimensions=hashed))
    assert plan_steps(state(has_chunks=False), design(hash_dimensions=hashed)) == (
        AddHashDimension(column="device", partitions=4),
    )
    keyed = state(has_chunks=False, unique_keys=(UniqueKey(name="events_key", columns=("observed_at",)),))
    assert 'Unique key "events_key" must include "device"' in refused(keyed, design(hash_dimensions=hashed))

    existing = state(design=design(hash_dimensions=hashed))
    assert plan_steps(existing, design(hash_dimensions=[HashDimensionDesign(column="device", partitions=8)])) == (
        SetPartitions(column="device", partitions=8),
    )
    assert "cannot remove the hash dimension" in refused(existing, design())


def test_only_tablespaces_this_role_may_use_are_attached() -> None:
    assert 'Tablespace "elsewhere" does not exist' in refused(state(), design(tablespaces=["elsewhere"]))
    assert plan_steps(state(), design(tablespaces=["fast"])) == (AttachTablespace(name="fast"),)


def test_a_reorder_index_must_belong_to_the_table() -> None:
    assert 'no index "other"' in refused(state(), design(reorder_index="other"))


def test_a_paused_reorder_policy_is_not_resumed_by_a_new_index() -> None:
    current = state(
        indexes=("events_device", "events_time"),
        reorder=ReorderPolicy(job_id="1001", scheduled=False, index_name="events_device"),
        design=design(reorder_index="events_device"),
    )
    assert plan_steps(current, design(reorder_index="events_device")) == ()
    assert "reorder policy is paused" in refused(current, design(reorder_index="events_time"))
    assert plan_steps(current, design()) == (RemovePolicy(kind="reorder", job_id="1001"),)


COUNT = IntegerSpan(amount="100000")
CLOCK = NowFunction(schema_name="lab", name="unix_now", type="bigint")


def integer_state(**changes: Any) -> CurrentHypertable:
    fields: dict[str, Any] = {
        "target": TARGET.model_copy(update={"column_name": "tick", "column_type": "bigint"}),
        "design": HypertableDesign(chunk_interval=COUNT),
        "interval_length": 100_000,
        "columns": (ColumnFact(name="tick", type="bigint", orderable=True),),
        "now_functions": (CLOCK,),
    }
    fields.update(changes)
    return state(**fields)


def integer_design(**changes: Any) -> HypertableDesign:
    return HypertableDesign(chunk_interval=COUNT).model_copy(update=changes)


def test_an_integer_chunk_interval_is_a_count_within_the_type() -> None:
    assert plan_steps(integer_state(), integer_design(chunk_interval=IntegerSpan(amount="5000"))) == (
        SetChunkInterval(interval=Count(amount=5000)),
    )
    small = integer_state(target=TARGET.model_copy(update={"column_name": "tick", "column_type": "smallint"}))
    assert "at most 32,767" in refused(small, integer_design(chunk_interval=IntegerSpan(amount="40000")))
    assert "number of its values" in refused(integer_state(), integer_design(chunk_interval=WEEK))
    assert "counted in minutes" in refused(state(), design(chunk_interval=COUNT))


def test_an_age_policy_on_integer_time_needs_integer_now() -> None:
    retention = OlderThan(older_than=IntegerSpan(amount="86400"))
    assert "needs an integer_now function" in refused(integer_state(), integer_design(retention=retention))

    steps = plan_steps(integer_state(), integer_design(
        retention=retention, integer_now=TemplateNow(template="epoch_seconds", name="unix_seconds"),
    ))
    assert steps == (
        CreateNowFunction(schema_name="lab", name="unix_seconds", template="epoch_seconds", column_type="bigint"),
        SetIntegerNow(schema_name="lab", name="unix_seconds", replace=False),
        AddAgePolicy(kind="retention", older_than=Count(amount=86400)),
    )


def test_an_integer_age_is_a_count_the_column_can_hold() -> None:
    clocked = integer_state(
        target=TARGET.model_copy(update={"column_name": "tick", "column_type": "integer"}),
        design=integer_design(integer_now=ExistingNow(schema_name="lab", name="unix_now")),
    )
    kept = {"integer_now": KeptNow()}
    assert "at most 2,147,483,647" in refused(clocked, integer_design(
        retention=OlderThan(older_than=IntegerSpan(amount="3000000000")), **kept,
    ))
    assert "number of its values" in refused(clocked, integer_design(retention=OlderThan(older_than=WEEK), **kept))
    assert "cannot count in plain numbers" in refused(state(), design(retention=OlderThan(older_than=COUNT)))


def test_an_unchanged_integer_policy_plans_nothing() -> None:
    current = integer_state(
        retention=AgePolicy(job_id="1000", scheduled=True, schedule_interval="1 day", older_than_count="86400"),
        design=integer_design(
            retention=OlderThan(older_than=IntegerSpan(amount="86400")), integer_now=KeptNow(),
        ),
    )
    assert plan_steps(current, current.design) == ()


def test_a_template_must_fit_the_column_type() -> None:
    narrow = integer_state(target=TARGET.model_copy(update={"column_name": "tick", "column_type": "integer"}))
    assert "cannot hold the milliseconds since 1970" in refused(narrow, integer_design(
        integer_now=TemplateNow(template="epoch_milliseconds", name="unix_ms"),
    ))


def test_an_existing_integer_now_must_be_one_timescale_accepts() -> None:
    assert "is not a function TimescaleDB accepts" in refused(integer_state(), integer_design(
        integer_now=ExistingNow(schema_name="lab", name="other"),
    ))
    current = integer_state(design=integer_design(integer_now=KeptNow()))
    assert plan_steps(current, integer_design(integer_now=ExistingNow(schema_name="lab", name="unix_now"))) == (
        SetIntegerNow(schema_name="lab", name="unix_now", replace=True),
    )
    assert plan_steps(current, integer_design(integer_now=KeptNow())) == ()
    assert "cannot take an integer_now function away" in refused(current, integer_design())
    assert "no integer_now function to keep" in refused(integer_state(), integer_design(integer_now=KeptNow()))


def test_only_integer_time_takes_integer_now_and_only_time_merges() -> None:
    assert "Only a hypertable partitioned by an integer column" in refused(
        state(), design(integer_now=ExistingNow(schema_name="lab", name="unix_now")),
    )
    assert "integer column does not count in" in refused(integer_state(), integer_design(
        columnstore=ColumnstoreDesign(enabled=True, merge_interval=WEEK),
    ))


BLOOM = SparseColumns(indexes=[SparseIndex(column="device", kind="bloom")])
ORDERED = OrderColumns(columns=[OrderKey(column="observed_at", descending=True, nulls_first=True)])


@pytest.mark.parametrize("raw,expected", [
    (None, ChosenByTimescale()),
    ('[{"type": "minmax", "column": "observed_at", "source": "orderby"}]', ChosenByTimescale()),
    ('[{"source": "config"}, {"type": "minmax", "column": "observed_at", "source": "orderby"}]', NoColumns()),
    ('[{"type": "bloom", "column": "device", "source": "config"}]', BLOOM),
])
def test_only_the_sparse_indexes_that_were_set_are_the_design(raw: str | None, expected: object) -> None:
    assert sparse_indexes(raw) == expected


def test_a_sparse_index_of_an_unknown_kind_is_left_to_sql() -> None:
    with pytest.raises(ActionRefused, match="kind this editor does not know"):
        sparse_indexes('[{"type": "firstlast", "column": "observed_at", "source": "config"}]')


def test_sparse_indexes_are_set_with_the_columnstore_where_the_release_has_them() -> None:
    requested = design(columnstore=ColumnstoreDesign(enabled=True, order_by=ORDERED, sparse_indexes=BLOOM))
    assert "has no sparse indexes; they arrived in 2.22" in refused(state(), requested)
    supported = state(sparse_indexes_supported=True)
    assert "need the order to be named" in refused(supported, design(
        columnstore=ColumnstoreDesign(enabled=True, sparse_indexes=BLOOM),
    ))
    (step,) = plan_steps(supported, requested)
    assert isinstance(step, ConfigureColumnstore) and step.sparse_changed and step.sparse_indexes == BLOOM
    assert '"payload" has a type that cannot be used as a minmax' in refused(supported, design(
        columnstore=ColumnstoreDesign(enabled=True, order_by=ORDERED, sparse_indexes=SparseColumns(indexes=[
            SparseIndex(column="payload", kind="minmax"),
        ])),
    ))
    assert "same sparse index twice" in refused(supported, design(
        columnstore=ColumnstoreDesign(enabled=True, order_by=ORDERED, sparse_indexes=SparseColumns(indexes=[
            SparseIndex(column="device", kind="bloom"), SparseIndex(column="device", kind="bloom"),
        ])),
    ))
    enabled = supported.model_copy(update={"design": requested})
    assert plan_steps(enabled, requested) == ()


def test_a_compaction_policy_needs_the_columnstore_and_a_release_that_has_it() -> None:
    on = design(columnstore=ColumnstoreDesign(enabled=True), compaction_policy=True)
    current = state(design=design(columnstore=ColumnstoreDesign(enabled=True)))
    assert "has no compaction policy; it arrived in 2.29" in refused(current, on)
    capable = current.model_copy(update={"compaction_supported": True})
    assert plan_steps(capable, on) == (AddCompactionPolicy(),)
    assert "turn the columnstore off" in refused(capable, design(compaction_policy=True))

    existing = capable.model_copy(update={
        "compaction": CompactionPolicy(job_id="1002", scheduled=True), "design": on,
    })
    assert plan_steps(existing, on) == ()
    assert plan_steps(existing, design()) == (
        RemovePolicy(kind="compaction", job_id="1002"), DisableColumnstore(),
    )
