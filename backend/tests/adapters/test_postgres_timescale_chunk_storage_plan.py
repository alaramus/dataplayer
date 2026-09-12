from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.adapters.actions import ActionRefused
from app.adapters.features import SourceFeature
from app.adapters.postgres.timescale import chunk_storage_plan
from app.adapters.postgres.timescale.api import ExtensionRoutine
from app.adapters.postgres.timescale.chunk_storage_action import ChunkWindowParams
from app.adapters.postgres.timescale.chunk_storage_plan import (
    CHUNK_COLUMNS,
    ROUTINES,
    inspect_chunk_unit,
    plan_chunk_storage,
)
from app.adapters.postgres.timescale.plans import (
    ChunkStorage,
    ChunkStorageUnit,
    ChunkWindow,
    TimeHypertable,
)
from app.adapters.postgres.timescale.profile import TimescaleProfile
from app.adapters.protocol import AdapterError

TARGET = TimeHypertable(
    database_oid="42", relation_oid="123", schema_name='odd"schema', table_name="events",
    column_name="time", column_type="timestamp with time zone",
)
ENDS = datetime(2026, 1, 15, tzinfo=UTC)
STARTS = datetime(2026, 1, 1, tzinfo=UTC)


def unit(storage: ChunkStorage = "columnstore") -> ChunkStorageUnit:
    return ChunkStorageUnit.model_validate({
        "target": TARGET,
        "strategy": {
            "storage": storage, "extension_version": "2.18.0",
            "function_schema": "public", "function_oid": "901",
        },
    })


def chunk(number: int) -> dict[str, Any]:
    return {
        "schema_name": "_timescaledb_internal", "name": f"_hyper_1_{number}_chunk",
        "range_start": f"start {number}", "range_end": f"end {number}",
    }


class Reader:
    """Answers the selection, then the count, and records what it was asked."""

    def __init__(self, chunks: list[dict[str, Any]], already: object = 0) -> None:
        self.asked: list[tuple[object, ...] | None] = []
        self._answers = [chunks, [{"already": already}]]

    async def query(
        self, sql: str, params: tuple[object, ...] | None = None, *,
        refusals: Mapping[str, str] | None = None, inspection: bool = False,
    ) -> list[dict[str, Any]]:
        assert inspection
        self.asked.append(params)
        return self._answers[len(self.asked) - 1]


@pytest.fixture
def inspected(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    async def inspect(_reader: object, _schema: str, _table: str, storage: ChunkStorage) -> ChunkStorageUnit:
        return unit(storage)

    probe = AsyncMock(side_effect=inspect)
    monkeypatch.setattr(chunk_storage_plan, "inspect_chunk_unit", probe)
    return probe


@pytest.mark.usefixtures("inspected")
@pytest.mark.parametrize("storage,selected,counted", [
    ("columnstore", False, True), ("rowstore", True, False),
])
async def test_the_plan_fixes_whole_chunks_needing_the_change_and_counts_the_rest(
    storage: ChunkStorage, selected: bool, counted: bool,
) -> None:
    reader = Reader([chunk(1), chunk(2)], already=3)
    plan = await plan_chunk_storage(
        reader, 'odd"schema', "events", storage, ChunkWindow(ends_by=ENDS, starts_from=STARTS),
    )
    assert [item.name for item in plan.chunks] == ["_hyper_1_1_chunk", "_hyper_1_2_chunk"]
    assert plan.already == 3
    assert plan.unit == unit(storage)
    assert reader.asked == [
        ('odd"schema', "events", selected, ENDS, STARTS, STARTS),
        ('odd"schema', "events", counted, ENDS, STARTS, STARTS),
    ]


def test_the_selection_reads_one_chunk_past_what_a_job_may_hold() -> None:
    assert "LIMIT 1001" in chunk_storage_plan._SELECTED


@pytest.mark.usefixtures("inspected")
async def test_a_window_larger_than_a_job_is_refused_rather_than_cut() -> None:
    reader = Reader([chunk(number) for number in range(1, 1002)])
    with pytest.raises(ActionRefused, match="More than 1000 chunks") as refused:
        await plan_chunk_storage(reader, "lab", "events", "columnstore", ChunkWindow(ends_by=ENDS))
    assert refused.value.reason == "too_large"


@pytest.mark.usefixtures("inspected")
@pytest.mark.parametrize("storage,already,message", [
    ("columnstore", 2, "Every whole chunk inside this window is already compressed"),
    ("rowstore", 2, "No whole chunk inside this window is compressed"),
    ("columnstore", 0, "No whole chunk lies inside this window"),
    ("rowstore", 0, "No whole chunk lies inside this window"),
])
async def test_an_empty_selection_is_refused_and_never_widened(
    storage: ChunkStorage, already: int, message: str,
) -> None:
    with pytest.raises(ActionRefused, match=message):
        await plan_chunk_storage(Reader([], already), "lab", "events", storage, ChunkWindow(ends_by=ENDS))


@pytest.mark.usefixtures("inspected")
@pytest.mark.parametrize("already", [None, True, "3"])
async def test_an_unreadable_count_refuses(already: object) -> None:
    with pytest.raises(ActionRefused, match="could not be"):
        await plan_chunk_storage(
            Reader([chunk(1)], already), "lab", "events", "columnstore", ChunkWindow(ends_by=ENDS),
        )


async def test_source_failures_refuse_in_the_applications_words(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        chunk_storage_plan, "inspect_chunk_unit",
        AsyncMock(side_effect=AdapterError("unknown", "password=secret")),
    )
    with pytest.raises(ActionRefused, match="could not be inspected safely") as refused:
        await plan_chunk_storage(Reader([]), "lab", "events", "columnstore", ChunkWindow(ends_by=ENDS))
    assert "secret" not in refused.value.message


async def test_an_inspection_refusal_keeps_its_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(chunk_storage_plan, "inspect_chunk_unit", AsyncMock(
        side_effect=ActionRefused("not_applicable", "Enable compression on this hypertable first"),
    ))
    with pytest.raises(ActionRefused, match="Enable compression on this hypertable first"):
        await plan_chunk_storage(Reader([]), "lab", "events", "columnstore", ChunkWindow(ends_by=ENDS))


@pytest.mark.usefixtures("inspected")
async def test_the_fingerprint_covers_the_selection_and_the_unit_does_not() -> None:
    window = ChunkWindow(ends_by=ENDS)
    first = await plan_chunk_storage(Reader([chunk(1)]), "lab", "events", "columnstore", window)
    second = await plan_chunk_storage(Reader([chunk(1), chunk(2)]), "lab", "events", "columnstore", window)
    wider = await plan_chunk_storage(
        Reader([chunk(1)]), "lab", "events", "columnstore", ChunkWindow(ends_by=ENDS + timedelta(days=1)),
    )
    assert len({first.fingerprint(), second.fingerprint(), wider.fingerprint()}) == 3
    assert first.unit.fingerprint() == second.unit.fingerprint() == wider.unit.fingerprint()
    with pytest.raises(ActionRefused, match="review it again"):
        second.require_unchanged(first.fingerprint())


def profile(version: str) -> TimescaleProfile:
    return TimescaleProfile(SourceFeature(
        code="timescaledb", title="TimescaleDB", state="available", installed_version=version,
    ))


@pytest.mark.parametrize("storage", ["columnstore", "rowstore"])
@pytest.mark.parametrize("version", ["2.17.2", "2.18.0"])
async def test_the_unit_verifies_the_installed_versions_own_routine(
    monkeypatch: pytest.MonkeyPatch, storage: ChunkStorage, version: str,
) -> None:
    routine = AsyncMock(return_value=ExtensionRoutine(oid="901", schema_name="public"))
    compression = AsyncMock()
    view = AsyncMock()
    monkeypatch.setattr(chunk_storage_plan, "discover", AsyncMock(return_value=profile(version)))
    monkeypatch.setattr(chunk_storage_plan, "require_tested_server", AsyncMock())
    monkeypatch.setattr(chunk_storage_plan, "time_hypertable", AsyncMock(return_value=TARGET))
    monkeypatch.setattr(chunk_storage_plan, "require_compression", compression)
    monkeypatch.setattr(chunk_storage_plan, "require_public_view", view)
    monkeypatch.setattr(chunk_storage_plan, "extension_routine", routine)
    reader = AsyncMock()
    found = await inspect_chunk_unit(reader, "lab", "events", storage)
    assert found.target == TARGET
    assert (found.strategy.storage, found.strategy.extension_version) == (storage, version)
    assert (found.strategy.function_schema, found.strategy.function_oid) == ("public", "901")
    routine.assert_awaited_once_with(reader, version, ROUTINES[storage][version])
    compression.assert_awaited_once_with(reader, TARGET)
    view.assert_awaited_once_with(reader, "chunks", CHUNK_COLUMNS)


async def test_an_untested_version_refuses_before_reading_the_hypertable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = AsyncMock()
    monkeypatch.setattr(chunk_storage_plan, "discover", AsyncMock(return_value=profile("2.19.0")))
    monkeypatch.setattr(chunk_storage_plan, "time_hypertable", target)
    with pytest.raises(ActionRefused, match="No supported TimescaleDB chunk compression API"):
        await inspect_chunk_unit(AsyncMock(), "lab", "events", "columnstore")
    target.assert_not_awaited()


def test_routine_shapes_follow_each_versions_declaration() -> None:
    legacy, columnstore = ROUTINES["columnstore"]["2.17.2"], ROUTINES["columnstore"]["2.18.0"]
    assert (legacy.name, legacy.argument_types, legacy.defaults) == ("compress_chunk", "2205 16 16", 2)
    assert (columnstore.argument_types, columnstore.defaults) == ("2205 16 16 16", 3)
    assert {(shape.name, shape.argument_types, shape.defaults) for shape in ROUTINES["rowstore"].values()} == {
        ("decompress_chunk", "2205 16", 1),
    }
    assert all(
        shape.kind == "f" and shape.result_type == 2205 and shape.exclusive
        for shapes in ROUTINES.values() for shape in shapes.values()
    )


def test_an_emptied_start_means_every_earlier_chunk() -> None:
    params = ChunkWindowParams.model_validate({"ends_by": "2026-01-15T03:00:00+03:00", "starts_from": "  "})
    assert params.starts_from is None
    assert params.window() == ChunkWindow(ends_by=ENDS)


@pytest.mark.parametrize("raw", [
    {"ends_by": "2026-01-15T00:00:00"},
    {"ends_by": ""},
    {"ends_by": "2026-01-15T00:00:00Z", "starts_from": "2026-01-15T00:00:00Z"},
    {"ends_by": "2026-01-15T00:00:00Z", "starts_from": "2026-01-16T00:00:00+03:00"},
    {"ends_by": "2026-01-15T00:00:00Z", "chunks": ["_hyper_1_1_chunk"]},
])
def test_a_window_takes_zoned_ordered_instants_and_nothing_else(raw: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ChunkWindowParams.model_validate(raw)
