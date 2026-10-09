"""The difference between a hypertable and its design, planned without a source (D207)."""

from typing import Any

import pytest

from app.adapters.actions import ActionRefused
from app.adapters.hypertable_design import (
    ChosenByTimescale,
    ColumnstoreDesign,
    DesignDuration,
    HashDimensionDesign,
    HypertableDesign,
    KeptAsItIs,
    NoColumns,
    OlderThan,
    OrderColumns,
    OrderKey,
    SegmentColumns,
)
from app.adapters.postgres.timescale.design_plan import (
    AddAgePolicy,
    AddHashDimension,
    AddReorderPolicy,
    AttachTablespace,
    ConfigureColumnstore,
    DetachTablespace,
    DisableColumnstore,
    RemovePolicy,
    SetChunkInterval,
    SetPartitions,
    plan_steps,
)
from app.adapters.postgres.timescale.design_state import (
    ColumnFact,
    CurrentHypertable,
    DesignTarget,
    ReorderPolicy,
    UniqueKey,
    fixed_duration,
    interval_duration,
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
        "interval_microseconds": 604_800_000_000,
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
