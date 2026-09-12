import asyncio
from collections.abc import Mapping
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import psycopg
import pytest

from app.adapters.actions import ActionRefused
from app.adapters.operations import OperationTarget
from app.adapters.postgres.timescale import chunk_storage_execution
from app.adapters.postgres.timescale.chunk_storage_execution import (
    convert_chunk,
    member,
    observe_chunks,
)
from app.adapters.postgres.timescale.plans import (
    ChunkStorage,
    ChunkStorageUnit,
    TimeHypertable,
)
from app.adapters.protocol import AdapterError

TARGET = TimeHypertable(
    database_oid="42", relation_oid="123", schema_name='odd"schema', table_name="events",
    column_name="time", column_type="timestamp with time zone",
)
CHUNK = OperationTarget(schema_name="_timescaledb_internal", name="_hyper_1_2_chunk")
REVIEWED = "f" * 64


def unit(storage: ChunkStorage = "columnstore", version: str = "2.18.0") -> ChunkStorageUnit:
    return ChunkStorageUnit.model_validate({
        "target": TARGET,
        "strategy": {
            "storage": storage, "extension_version": version,
            "function_schema": 'ext"schema', "function_oid": "901",
        },
    })


def source_session() -> tuple[MagicMock, MagicMock]:
    session = MagicMock()
    connection = MagicMock()
    connection.execute = AsyncMock()
    session.acquire.return_value.__aenter__.return_value = connection
    return session, connection


def admitted(monkeypatch: pytest.MonkeyPatch, storage: ChunkStorage, *, compressed: bool) -> AsyncMock:
    found = AsyncMock(return_value=(unit(storage), "555", compressed))
    monkeypatch.setattr(chunk_storage_execution, "member", found)
    return found


@pytest.mark.parametrize("storage,routine", [
    ("columnstore", "compress_chunk"), ("rowstore", "decompress_chunk"),
])
async def test_one_chunk_is_converted_in_one_transaction_after_its_membership(
    monkeypatch: pytest.MonkeyPatch, storage: ChunkStorage, routine: str,
) -> None:
    session, connection = source_session()
    found = admitted(monkeypatch, storage, compressed=storage == "rowstore")
    assert await convert_chunk(session, "lab", "events", storage, REVIEWED, CHUNK) == "completed"
    calls = connection.execute.await_args_list
    assert [call.args[0] for call in calls[:3]] == [
        "SET TRANSACTION ISOLATION LEVEL READ COMMITTED, READ WRITE",
        "SET LOCAL lock_timeout = '5s'",
        "SET LOCAL statement_timeout = '15min'",
    ]
    assert (calls[3].args[0].as_string(), calls[3].args[1]) == (
        f'SELECT "ext""schema"."{routine}"(%s::pg_catalog.regclass, true)', ("555",),
    )
    assert len(calls) == 4
    assert found.await_args is not None
    assert found.await_args.args[1:] == ("lab", "events", storage, REVIEWED, CHUNK)
    connection.transaction.return_value.__aexit__.assert_awaited_once_with(None, None, None)


@pytest.mark.parametrize("storage", ["columnstore", "rowstore"])
async def test_a_chunk_already_stored_as_requested_is_left_alone(
    monkeypatch: pytest.MonkeyPatch, storage: ChunkStorage,
) -> None:
    session, connection = source_session()
    admitted(monkeypatch, storage, compressed=storage == "columnstore")
    assert await convert_chunk(session, "lab", "events", storage, REVIEWED, CHUNK) == "already"
    assert connection.execute.await_count == 3


async def test_a_membership_refusal_sends_no_conversion(monkeypatch: pytest.MonkeyPatch) -> None:
    session, connection = source_session()
    monkeypatch.setattr(chunk_storage_execution, "member", AsyncMock(
        side_effect=ActionRefused("not_applicable", "This chunk is no longer part of the hypertable"),
    ))
    with pytest.raises(ActionRefused, match="no longer part"):
        await convert_chunk(session, "lab", "events", "columnstore", REVIEWED, CHUNK)
    assert connection.execute.await_count == 3


@pytest.mark.parametrize("error,expected,words", [
    (psycopg.errors.LockNotAvailable("secret"), ActionRefused, "in use"),
    (psycopg.errors.DeadlockDetected("secret"), ActionRefused, "in use"),
    (psycopg.errors.QueryCanceled("secret"), ActionRefused, "rolled back"),
    (psycopg.errors.InsufficientPrivilege("secret"), ActionRefused, "may not convert"),
    (psycopg.errors.RaiseException("secret"), ActionRefused, "refused to convert"),
    (psycopg.errors.AdminShutdown("secret"), AdapterError, "outcome is unknown"),
    (psycopg.OperationalError("secret"), AdapterError, "outcome is unknown"),
])
async def test_a_failed_conversion_is_refused_or_unknown_and_never_retried(
    monkeypatch: pytest.MonkeyPatch, error: Exception, expected: type[Exception], words: str,
) -> None:
    session, connection = source_session()
    admitted(monkeypatch, "columnstore", compressed=False)
    connection.execute.side_effect = [None, None, None, error]
    with pytest.raises(expected, match=words) as raised:
        await convert_chunk(session, "lab", "events", "columnstore", REVIEWED, CHUNK)
    assert "secret" not in str(raised.value.args)
    assert connection.execute.await_count == 4


async def test_a_connection_lost_at_commit_leaves_the_outcome_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, connection = source_session()
    admitted(monkeypatch, "columnstore", compressed=False)
    connection.transaction.return_value.__aexit__.side_effect = psycopg.OperationalError("secret")
    with pytest.raises(AdapterError, match="outcome is unknown"):
        await convert_chunk(session, "lab", "events", "columnstore", REVIEWED, CHUNK)


async def test_a_failure_before_the_conversion_is_sent_changed_nothing() -> None:
    session, connection = source_session()
    connection.execute.side_effect = psycopg.OperationalError("secret")
    with pytest.raises(ActionRefused, match="nothing was converted") as raised:
        await convert_chunk(session, "lab", "events", "columnstore", REVIEWED, CHUNK)
    assert "secret" not in raised.value.message


async def test_an_unreachable_source_changed_nothing() -> None:
    session = MagicMock()
    session.acquire.return_value.__aenter__.side_effect = AdapterError("unknown", "password=secret")
    with pytest.raises(ActionRefused, match="could not be reached"):
        await convert_chunk(session, "lab", "events", "columnstore", REVIEWED, CHUNK)


async def test_cancellation_propagates_once_the_transaction_unwinds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, connection = source_session()
    admitted(monkeypatch, "columnstore", compressed=False)
    connection.execute.side_effect = [None, None, None, asyncio.CancelledError()]
    with pytest.raises(asyncio.CancelledError):
        await convert_chunk(session, "lab", "events", "columnstore", REVIEWED, CHUNK)
    unwound = connection.transaction.return_value.__aexit__.await_args
    assert unwound is not None and unwound.args[0] is asyncio.CancelledError


class Reader:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.asked: list[tuple[object, ...] | None] = []

    async def query(
        self, sql: str, params: tuple[object, ...] | None = None, *,
        refusals: Mapping[str, str] | None = None, inspection: bool = False,
    ) -> list[dict[str, Any]]:
        assert inspection
        self.asked.append(params)
        return self.rows


@pytest.fixture
def inspected(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    probe = AsyncMock(return_value=unit())
    monkeypatch.setattr(chunk_storage_execution, "inspect_chunk_unit", probe)
    return probe


@pytest.mark.usefixtures("inspected")
async def test_membership_is_resolved_under_the_admitted_unit() -> None:
    reader = Reader([{"relation_oid": "555", "is_compressed": False}])
    found = await member(reader, "lab", "events", "columnstore", unit().fingerprint(), CHUNK)
    assert found == (unit(), "555", False)
    assert reader.asked == [('odd"schema', "events", "_timescaledb_internal", "_hyper_1_2_chunk")]


@pytest.mark.usefixtures("inspected")
async def test_a_changed_unit_refuses_the_chunk() -> None:
    reader = Reader([{"relation_oid": "555", "is_compressed": False}])
    with pytest.raises(ActionRefused, match="changed after review") as refused:
        await member(reader, "lab", "events", "columnstore", "0" * 64, CHUNK)
    assert refused.value.reason == "conflict"


@pytest.mark.usefixtures("inspected")
@pytest.mark.parametrize("rows", [
    [],
    [{"relation_oid": "555", "is_compressed": False}] * 2,
    [{"relation_oid": "555", "is_compressed": None}],
])
async def test_a_chunk_outside_its_parent_is_refused(rows: list[dict[str, Any]]) -> None:
    with pytest.raises(ActionRefused, match="no longer part"):
        await member(Reader(rows), "lab", "events", "columnstore", unit().fingerprint(), CHUNK)


async def test_unreadable_metadata_refuses_without_driver_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        chunk_storage_execution, "inspect_chunk_unit",
        AsyncMock(side_effect=AdapterError("unknown", "password=secret")),
    )
    with pytest.raises(ActionRefused, match="checked safely") as refused:
        await member(Reader([]), "lab", "events", "columnstore", REVIEWED, CHUNK)
    assert "secret" not in refused.value.message


async def test_reading_back_names_each_target_as_requested_unchanged_or_gone() -> None:
    reader = Reader([
        {"schema_name": "_timescaledb_internal", "name": "_hyper_1_1_chunk", "is_compressed": True},
        {"schema_name": "_timescaledb_internal", "name": "_hyper_1_2_chunk", "is_compressed": False},
    ])
    session = MagicMock()
    session.inspection.return_value.__aenter__.return_value = reader
    targets = [
        OperationTarget(schema_name="_timescaledb_internal", name=f"_hyper_1_{number}_chunk")
        for number in (1, 2, 3)
    ]
    assert await observe_chunks(session, "lab", "events", "columnstore", targets) == [
        "as_requested", "unchanged", "gone",
    ]
    assert await observe_chunks(session, "lab", "events", "rowstore", targets) == [
        "unchanged", "as_requested", "gone",
    ]
    assert reader.asked[0] == (
        "lab", "events", ["_timescaledb_internal"] * 3,
        ["_hyper_1_1_chunk", "_hyper_1_2_chunk", "_hyper_1_3_chunk"],
    )
