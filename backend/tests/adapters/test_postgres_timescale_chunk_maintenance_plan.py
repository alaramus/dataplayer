"""Chunk maintenance rules that need no source (D208)."""

import pytest

from app.adapters.actions import ActionRefused
from app.adapters.postgres.timescale.chunk_maintenance_execution import _observed
from app.adapters.postgres.timescale.chunk_maintenance_plan import (
    MaintenanceArguments,
    MaintenanceStrategy,
    MaintenanceUnit,
    _require_mergeable,
)
from app.adapters.postgres.timescale.plans import TimeHypertable

TARGET = TimeHypertable(
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
