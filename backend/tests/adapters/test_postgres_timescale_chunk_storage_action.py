from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.actions import (
    ActionRefused,
    Previews,
    RequiresReviewedPlan,
    TakesParams,
)
from app.adapters.catalog import SchemaNode, TableNode
from app.adapters.operations import OperationTarget, ProducesJob
from app.adapters.postgres.timescale import chunk_storage_action
from app.adapters.postgres.timescale.chunk_storage_action import (
    CompressChunks,
    ConvertChunks,
    DecompressChunks,
    chunk_storage_admission,
)
from app.adapters.postgres.timescale.plans import (
    ChunkStorage,
    ChunkStoragePlan,
    ChunkWindow,
)
from app.adapters.protocol import AdapterError, NodeNotFound

ENDS = datetime(2026, 1, 15, tzinfo=UTC)
PARAMS = {"ends_by": "2026-01-15T00:00:00Z", "starts_from": None}
TARGET = OperationTarget(schema_name="_timescaledb_internal", name="_hyper_1_1_chunk")


def catalog() -> AsyncMock:
    found = AsyncMock()
    found.path_to.return_value = [
        SchemaNode(id="schema-id", name='odd"schema', has_children=True, representations=[]),
        TableNode(id="node-id", name="events", has_children=False, representations=[]),
    ]
    return found


def session() -> MagicMock:
    source = MagicMock()
    source.inspection.return_value.__aenter__.return_value = AsyncMock()
    return source


def plan(*, count: int = 2, already: int = 0, storage: ChunkStorage = "columnstore") -> ChunkStoragePlan:
    return ChunkStoragePlan.model_validate({
        "unit": {
            "target": {
                "database_oid": "42", "relation_oid": "123", "schema_name": 'odd"schema',
                "table_name": "events", "column_name": "time",
                "column_type": "timestamp with time zone",
            },
            "strategy": {
                "storage": storage, "extension_version": "2.18.0",
                "function_schema": "public", "function_oid": "901",
            },
        },
        "window": {"ends_by": ENDS},
        "chunks": [
            {
                "schema_name": "_timescaledb_internal", "name": f"_hyper_1_{number}_chunk",
                "range_start": f"start {number}", "range_end": f"end {number}",
            }
            for number in range(1, count + 1)
        ],
        "already": already,
    })


@pytest.mark.parametrize("action_type", [CompressChunks, DecompressChunks])
def test_chunk_conversion_is_a_reviewed_job_and_nothing_else(action_type: type[ConvertChunks]) -> None:
    action = action_type(session(), catalog())
    assert isinstance(action, ProducesJob)
    assert isinstance(action, Previews)
    assert not isinstance(action, TakesParams)
    assert not isinstance(action, RequiresReviewedPlan)
    assert action.requires == "structure"
    assert action.feature_requirements == ("timescaledb",)
    assert action.applies_to == frozenset({"table"})
    assert not action.bulk and not action.destructive


async def test_the_preview_names_the_fixed_chunks_and_what_the_job_will_do(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    planned = plan(count=12, already=2)
    planner = AsyncMock(return_value=planned)
    monkeypatch.setattr(chunk_storage_action, "plan_chunk_storage", planner)
    preview = await CompressChunks(session(), catalog()).preview("node-id", PARAMS)
    assert preview.summary == 'Compress 12 chunks of "odd""schema"."events" as a job'
    assert preview.fingerprint == planned.fingerprint()
    assert not preview.blocked
    assert preview.items[0] == f"Whole chunks from the earliest chunk to {ENDS.isoformat()}"
    assert preview.items[1] == '"_timescaledb_internal"."_hyper_1_1_chunk": start 1 to end 1'
    assert preview.items[11] == "…and 2 more"
    assert "Already compressed and left as they are: 2" in preview.items
    assert planned.impact in preview.items and planned.coordination in preview.items
    assert planner.await_args is not None
    assert planner.await_args.args[1:] == ('odd"schema', "events", "columnstore", ChunkWindow(ends_by=ENDS))


@pytest.mark.parametrize("failure,summary", [
    (ActionRefused("not_applicable", "No whole chunk lies inside this window"),
     "No whole chunk lies inside this window"),
    (AdapterError("unknown", "password=secret"), "could not be inspected safely"),
])
async def test_a_plan_that_cannot_be_drawn_blocks_review(
    monkeypatch: pytest.MonkeyPatch, failure: Exception, summary: str,
) -> None:
    monkeypatch.setattr(chunk_storage_action, "plan_chunk_storage", AsyncMock(side_effect=failure))
    preview = await DecompressChunks(session(), catalog()).preview("node-id", PARAMS)
    assert preview.blocked and preview.fingerprint is None
    assert summary in preview.summary and "secret" not in preview.summary


async def test_admission_draws_the_plan_again_and_fixes_its_targets(monkeypatch: pytest.MonkeyPatch) -> None:
    planned = plan(count=2)
    monkeypatch.setattr(chunk_storage_action, "plan_chunk_storage", AsyncMock(return_value=planned))
    action = CompressChunks(session(), catalog())
    admitted = await action.plan_job("node-id", PARAMS, planned.fingerprint())
    assert admitted.targets == (
        TARGET, OperationTarget(schema_name="_timescaledb_internal", name="_hyper_1_2_chunk"),
    )
    assert admitted.unit_fingerprint == planned.unit.fingerprint()
    assert admitted.summary == 'Compress 2 chunks of "odd""schema"."events" as a job'
    with pytest.raises(ActionRefused, match="review it again") as stale:
        await action.plan_job("node-id", PARAMS, "0" * 64)
    assert stale.value.reason == "conflict"


async def test_a_unit_converts_one_named_chunk_of_the_resolved_hypertable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    convert = AsyncMock(return_value="completed")
    monkeypatch.setattr(chunk_storage_action, "convert_chunk", convert)
    source = session()
    assert await DecompressChunks(source, catalog()).run_unit("node-id", PARAMS, "f" * 64, TARGET) == "completed"
    convert.assert_awaited_once_with(source, 'odd"schema', "events", "rowstore", "f" * 64, TARGET)


@pytest.mark.parametrize("failure", [NodeNotFound("node-id"), AdapterError("unknown", "gone")])
async def test_a_hypertable_that_cannot_be_found_refuses_the_unit(
    monkeypatch: pytest.MonkeyPatch, failure: Exception,
) -> None:
    found = catalog()
    found.path_to.side_effect = failure
    convert = AsyncMock()
    monkeypatch.setattr(chunk_storage_action, "convert_chunk", convert)
    with pytest.raises(ActionRefused, match="could not be found"):
        await CompressChunks(session(), found).run_unit("node-id", PARAMS, "f" * 64, TARGET)
    convert.assert_not_awaited()


async def test_reading_back_uses_the_same_hypertable(monkeypatch: pytest.MonkeyPatch) -> None:
    observe = AsyncMock(return_value=["gone"])
    monkeypatch.setattr(chunk_storage_action, "observe_chunks", observe)
    source = session()
    assert await CompressChunks(source, catalog()).observe("node-id", PARAMS, [TARGET]) == ["gone"]
    observe.assert_awaited_once_with(source, 'odd"schema', "events", "columnstore", [TARGET])


async def test_both_directions_are_admitted_from_one_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    async def inspect(_reader: object, _schema: str, _table: str, storage: ChunkStorage) -> None:
        if storage == "rowstore":
            raise ActionRefused("not_applicable", "TimescaleDB is not installed on this database")

    probe = AsyncMock(side_effect=inspect)
    monkeypatch.setattr(chunk_storage_action, "inspect_chunk_unit", probe)
    source = session()
    assert await chunk_storage_admission(source, "lab", "events") == {
        "columnstore": None, "rowstore": "TimescaleDB is not installed on this database",
    }
    source.inspection.assert_called_once_with()
    assert [call.args[3] for call in probe.await_args_list] == ["columnstore", "rowstore"]


async def test_unreadable_admission_explains_both_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        chunk_storage_action, "inspect_chunk_unit",
        AsyncMock(side_effect=AdapterError("unknown", "password=secret")),
    )
    reasons = await chunk_storage_admission(session(), "lab", "events")
    assert set(reasons) == {"columnstore", "rowstore"}
    assert all(reason is not None and "inspected safely" in reason for reason in reasons.values())
