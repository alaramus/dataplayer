"""Chunk maintenance rules that need no source (D208)."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.adapters.actions import ActionRefused
from app.adapters.postgres.timescale.chunk_maintenance_action import (
    AttachParams,
    WindowParams,
)
from app.adapters.postgres.timescale.chunk_maintenance_execution import _observed
from app.adapters.postgres.timescale.chunk_maintenance_plan import (
    MaintenanceArguments,
    MaintenanceStrategy,
    MaintenanceUnit,
    _require_mergeable,
    require_kind,
)
from app.adapters.postgres.timescale.plans import ChunkRef, MaintainedHypertable

TARGET = MaintainedHypertable(
    database_oid="1", relation_oid="2", schema_name="lab", table_name="events",
    column_name="observed_at", column_type="timestamp with time zone",
)


def chunk(name: str, start: str, end: str, *, compressed: bool = False) -> dict[str, object]:
    return {"name": name, "range_start": start, "range_end": end, "is_compressed": compressed}


def unit(maintenance: str, **arguments: str) -> MaintenanceUnit:
    return MaintenanceUnit.model_validate({
        "maintenance": maintenance, "target": TARGET,
        "strategy": MaintenanceStrategy(extension_version="2.30.0"),
        "arguments": MaintenanceArguments(**arguments),
    })


def test_a_merge_takes_two_or_more_chunks_that_touch() -> None:
    _require_mergeable([chunk("a", "1", "2"), chunk("b", "2", "3")], "2.18.0")
    with pytest.raises(ActionRefused, match="at least two"):
        _require_mergeable([chunk("a", "1", "2")], "2.30.0")
    with pytest.raises(ActionRefused, match='"a" and "b" are not adjacent'):
        _require_mergeable([chunk("a", "1", "2"), chunk("b", "3", "4")], "2.30.0")


def test_compressed_chunks_merge_only_from_the_release_that_learned_it() -> None:
    compressed = [chunk("a", "1", "2", compressed=True), chunk("b", "2", "3")]
    with pytest.raises(ActionRefused, match="2.18.0 cannot merge compressed chunks"):
        _require_mergeable(compressed, "2.18.0")
    _require_mergeable(compressed, "2.19.3")


def test_what_reading_back_says_of_each_operation() -> None:
    member = {"tablespace": "fast"}
    assert _observed(unit("drop"), None, exists=False) == "as_requested"
    assert _observed(unit("drop"), member, exists=True) == "unchanged"
    assert _observed(unit("detach"), None, exists=True) == "as_requested"
    assert _observed(unit("detach"), None, exists=False) == "gone"
    assert _observed(unit("attach"), member, exists=True) == "as_requested"
    assert _observed(unit("move", tablespace="fast"), member, exists=True) == "as_requested"
    assert _observed(unit("move", tablespace="slow"), member, exists=True) == "unchanged"
    # Nothing public tells a reordered chunk apart; it is read as not done, and doing it again is harmless.
    assert _observed(unit("reorder", index="events_device"), member, exists=True) == "unchanged"


def test_a_bound_is_an_instant_or_a_whole_number() -> None:
    assert WindowParams.model_validate({"ends_by": "2020-01-03T00:00:00Z"}).selection().ends_by == datetime(
        2020, 1, 3, tzinfo=UTC,
    )
    # Typed into a form, a number arrives as text; it is never read as seconds from 1970.
    window = WindowParams.model_validate({"ends_by": "1000", "starts_from": " 10 "}).selection()
    assert (window.starts_from, window.ends_by) == (10, 1000)
    assert WindowParams.model_validate({"ends_by": 1000, "starts_from": ""}).selection().starts_from is None
    for wrong, message in (
        ({"ends_by": "1000", "starts_from": "2020-01-01T00:00:00Z"}, "Both ends are instants, or both are numbers"),
        ({"ends_by": "10", "starts_from": "20"}, "must start before it ends"),
        ({"ends_by": "2020-01-03T00:00:00"}, "with its time zone"),
        ({"ends_by": True}, "or a whole number"),
        ({"ends_by": str(2**63)}, "outside the range of a bigint"),
    ):
        with pytest.raises(ValidationError, match=message):
            WindowParams.model_validate(wrong)
    with pytest.raises(ValidationError, match="must start before it ends"):
        AttachParams.model_validate({"table_schema": "s", "table_name": "t", "starts_from": "8", "ends_by": "4"})


def test_a_bound_must_be_of_the_kind_the_column_is() -> None:
    ticks = TARGET.model_copy(update={"column_name": "tick", "column_type": "bigint"})
    require_kind(ticks, 1000, None)
    require_kind(TARGET, datetime(2020, 1, 1, tzinfo=UTC))
    with pytest.raises(ActionRefused, match='integer column "tick"; give its values'):
        require_kind(ticks, datetime(2020, 1, 1, tzinfo=UTC))
    with pytest.raises(ActionRefused, match='by time on "observed_at"; give instants'):
        require_kind(TARGET, 1000)


def test_a_window_or_picked_chunks_never_both() -> None:
    picked = [{"schema_name": "_timescaledb_internal", "name": "_hyper_1_1_chunk"}]
    # A hidden field nobody set arrives empty; the window's form still asks for its end.
    assert WindowParams.model_validate({"ends_by": "", "starts_from": "", "chunks": picked}).selection() == (
        ChunkRef(schema_name="_timescaledb_internal", name="_hyper_1_1_chunk"),
    )
    assert "ends_by" in WindowParams.model_json_schema()["required"]
    with pytest.raises(ValidationError, match="Either a window or picked chunks"):
        WindowParams.model_validate({"ends_by": "100", "chunks": picked})
    with pytest.raises(ValidationError, match="Give where the window ends"):
        WindowParams.model_validate({"ends_by": "", "chunks": ""})
