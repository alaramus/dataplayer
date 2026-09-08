import asyncio
from unittest.mock import AsyncMock

import pytest

from app.adapters.postgres.timescale.statistics import inspect_statistics
from app.adapters.protocol import AdapterError
from app.adapters.relation import RelationModel
from app.adapters.specializations import TimescaleContinuousAggregate, TimescaleHypertable
from app.adapters.timescale_metadata import (
    ContinuousAggregateFacts,
    HypertableFacts,
    TimescaleCompression,
    UnavailableTimescaleFacts,
)


def model() -> RelationModel:
    return RelationModel(
        node_id="logical", schema_name='odd.schema"', name="metrics'; DROP TABLE x",
        kind="table", specialization=TimescaleHypertable(),
    )


FACTS = HypertableFacts(num_dimensions=1, num_chunks="2", compression_enabled=True)
FUNCTION = [{"function_schema": 'extension"schema'}]
SIZE = {
    "table_bytes": "9007199254740993", "index_bytes": "100", "toast_bytes": "0",
    "total_bytes": "9007199254741093", "node_name": None,
}
COMPRESSION = {
    field: "100" for field in TimescaleCompression.model_fields if field != "kind"
} | {"total_chunks": "2", "number_compressed_chunks": "1", "node_name": None}


async def test_reads_exact_sizes_and_recorded_compression_with_bound_identities() -> None:
    session = AsyncMock()
    session.query.side_effect = [FUNCTION, [SIZE], FUNCTION, [COMPRESSION]]
    result = await inspect_statistics(session, model(), FACTS)
    assert result is not None and result.size.kind == "size"
    assert result.size.table_bytes == "9007199254740993"
    assert result.compression.kind == "compression"
    assert result.compression.number_compressed_chunks == "1"
    lookups = session.query.await_args_list[::2]
    for lookup in lookups:
        query, params = lookup.args
        assert "dependency.deptype = 'e'" in query
        assert "routine.pronamespace = extension.extnamespace" in query
        assert "routine.prokind = 'f'" in query
        assert "routine.proargtypes[0] = 'pg_catalog.regclass'" in query
        assert "routine.proallargtypes =" in query
        assert "routine.proargmodes =" in query
        assert "has_function_privilege" in query
        assert params[3][-1] == "node_name"
    calls = session.query.await_args_list[1::2]
    for call in calls:
        query, params = call.args
        assert query.endswith("(%s::pg_catalog.regclass) LIMIT 2")
        assert '"extension""schema".' in query
        assert "DROP TABLE" not in query
        assert params == ('"odd.schema"""."metrics\'; DROP TABLE x"',)
    assert all(call.kwargs["inspection"] for call in session.query.await_args_list)


async def test_legacy_api_is_used_only_when_columnstore_shape_is_unavailable() -> None:
    session = AsyncMock()
    session.query.side_effect = [FUNCTION, [SIZE], [], FUNCTION, [COMPRESSION]]
    result = await inspect_statistics(session, model(), FACTS)
    assert result is not None and result.compression.kind == "compression"
    assert '"hypertable_compression_stats"' in session.query.await_args.args[0]


@pytest.mark.parametrize("failure", [
    AdapterError("config", "secret driver details"), ValueError("secret"),
])
async def test_execution_failure_does_not_retry_legacy_or_discard_size(failure: Exception) -> None:
    session = AsyncMock()
    session.query.side_effect = [FUNCTION, [SIZE], FUNCTION, failure]
    result = await inspect_statistics(session, model(), FACTS)
    assert result is not None and result.size.kind == "size"
    assert result.compression.kind == "unavailable"
    assert "secret" not in result.compression.reason
    assert session.query.await_count == 4


@pytest.mark.parametrize("rows", [
    [], [SIZE, SIZE], [SIZE | {"node_name": "remote"}], [SIZE | {"total_bytes": None}],
    [SIZE | {"total_bytes": "-1"}], [SIZE | {"total_bytes": 123}],
    [{"node_name": None}],
])
async def test_empty_remote_ambiguous_or_invalid_sizes_do_not_become_zero(
    rows: list[dict[str, object]],
) -> None:
    session = AsyncMock()
    session.query.side_effect = [FUNCTION, rows, FUNCTION, [COMPRESSION]]
    result = await inspect_statistics(session, model(), FACTS)
    assert result is not None and result.size.kind == "unavailable"
    assert result.compression.kind == "compression"


async def test_null_recorded_sizes_remain_null() -> None:
    compression = COMPRESSION | {
        field: None for field in COMPRESSION if field.endswith("_bytes")
    }
    session = AsyncMock()
    session.query.side_effect = [FUNCTION, [SIZE], FUNCTION, [compression]]
    result = await inspect_statistics(session, model(), FACTS)
    assert result is not None and result.compression.kind == "compression"
    assert result.compression.before_compression_total_bytes is None


async def test_aggregate_size_uses_logical_view_and_compression_uses_materialization() -> None:
    facts = ContinuousAggregateFacts(
        hypertable_schema="source", hypertable_name="metrics",
        materialization_hypertable_schema="internal.with.dot",
        materialization_hypertable_name='materialized"name',
        materialized_only=False, compression_enabled=True,
    )
    aggregate = model().model_copy(update={"specialization": TimescaleContinuousAggregate()})
    session = AsyncMock()
    session.query.side_effect = [FUNCTION, [SIZE], FUNCTION, [COMPRESSION]]
    await inspect_statistics(session, aggregate, facts)
    assert session.query.await_args_list[1].args[1] == (
        '"odd.schema"""."metrics\'; DROP TABLE x"',
    )
    assert session.query.await_args_list[3].args[1] == (
        '"internal.with.dot"."materialized""name"',
    )


async def test_missing_public_apis_never_invoke_a_function() -> None:
    session = AsyncMock()
    session.query.return_value = []
    result = await inspect_statistics(session, model(), FACTS)
    assert result is not None and result.size.kind == "unavailable"
    assert result.compression.kind == "unavailable"
    assert session.query.await_count == 3
    assert all("pg_catalog.pg_proc" in call.args[0] for call in session.query.await_args_list)


async def test_deadline_retains_size_when_compression_is_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_timeout = asyncio.timeout
    budgets: list[float] = []

    def immediate_timeout(seconds: float) -> asyncio.Timeout:
        budgets.append(seconds)
        return original_timeout(0)

    count = 0

    async def query(*_args: object, **_kwargs: object) -> list[dict[str, object]]:
        nonlocal count
        count += 1
        if count == 1:
            return FUNCTION
        if count == 2:
            return [SIZE]
        await asyncio.Future[None]()
        return []

    monkeypatch.setattr("app.adapters.postgres.timescale.statistics.asyncio.timeout", immediate_timeout)
    session = AsyncMock()
    session.query.side_effect = query
    result = await inspect_statistics(session, model(), FACTS)
    assert budgets == [5]
    assert result is not None and result.size.kind == "size"
    assert result.compression.kind == "unavailable"
    assert "timed out" in result.compression.reason


async def test_cancellation_propagates() -> None:
    session = AsyncMock()
    session.query.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await inspect_statistics(session, model(), FACTS)


async def test_ordinary_or_unavailable_metadata_does_not_probe_statistics() -> None:
    session = AsyncMock()
    assert await inspect_statistics(
        session, model().model_copy(update={"specialization": None}), None,
    ) is None
    assert await inspect_statistics(
        session, model(), UnavailableTimescaleFacts(reason="Unavailable"),
    ) is None
    session.query.assert_not_awaited()
