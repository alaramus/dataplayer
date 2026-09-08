import asyncio
from unittest.mock import AsyncMock

import pytest

from app.adapters.postgres.timescale.details import inspect_details
from app.adapters.protocol import AdapterError
from app.adapters.relation import RelationModel
from app.adapters.specializations import TimescaleContinuousAggregate, TimescaleHypertable
from app.adapters.timescale_metadata import ContinuousAggregateFacts, HypertableFacts


def model() -> RelationModel:
    return RelationModel(
        node_id="not-split", schema_name="schema.with.dot", name="table'; DROP TABLE x",
        kind="table", specialization=TimescaleHypertable(),
    )


def session_for(values: dict[str, object], *, aggregate: bool = False) -> AsyncMock:
    identity = ("view_schema", "view_name") if aggregate else (
        "hypertable_schema", "hypertable_name",
    )
    session = AsyncMock()
    session.query.side_effect = [
        [{"column_name": name} for name in dict.fromkeys((*identity, *values))],
        [values],
    ]
    return session


async def test_hypertable_counts_keep_exact_decimal_text_and_bound_identity() -> None:
    values = {"num_dimensions": 2, "num_chunks": "9007199254740993",
              "compression_enabled": False}
    session = session_for(values)
    facts = await inspect_details(session, model())
    assert isinstance(facts, HypertableFacts)
    assert facts.num_chunks == "9007199254740993"
    assert facts.compression_enabled is False
    query, params = session.query.await_args.args
    assert params == (model().schema_name, model().name)
    assert "DROP TABLE" not in query
    assert '"num_chunks"::text AS "num_chunks"' in query
    assert query.endswith("LIMIT 2")
    assert all(call.kwargs["inspection"] for call in session.query.await_args_list)


async def test_aggregate_returns_public_source_and_materialization_facts() -> None:
    values = {
        "hypertable_schema": "source", "hypertable_name": "metrics",
        "materialization_hypertable_schema": "internal",
        "materialization_hypertable_name": "materialized",
        "materialized_only": False, "compression_enabled": True,
    }
    session = session_for(values, aggregate=True)
    aggregate = model().model_copy(update={"specialization": TimescaleContinuousAggregate()})
    facts = await inspect_details(session, aggregate)
    assert isinstance(facts, ContinuousAggregateFacts)
    assert facts.hypertable_schema == "source"
    assert facts.materialized_only is False
    assert '"view_schema" = %s AND "view_name" = %s' in session.query.await_args.args[0]


@pytest.mark.parametrize("failure", [
    AdapterError("timeout", "secret driver detail"),
    AdapterError("config", "secret driver detail"),
    ValueError("secret driver detail"),
    TimeoutError(),
])
async def test_optional_failure_has_a_safe_unavailable_answer(failure: Exception) -> None:
    session = AsyncMock()
    session.query.side_effect = failure
    result = await inspect_details(session, model())
    assert result is not None and result.kind == "unavailable"
    assert "secret" not in result.reason


@pytest.mark.parametrize("rows", [[], [{}, {}], [{"num_chunks": -1}]])
async def test_missing_ambiguous_or_invalid_metadata_is_not_reported_as_zero(
    rows: list[dict[str, object]],
) -> None:
    session = session_for({"num_dimensions": 1, "num_chunks": "0", "compression_enabled": True})
    columns = [
        {"column_name": name} for name in (
            "hypertable_schema", "hypertable_name", "num_dimensions", "num_chunks",
            "compression_enabled",
        )
    ]
    session.query.side_effect = [columns, rows]
    result = await inspect_details(session, model())
    assert result is not None and result.kind == "unavailable"


async def test_cancellation_is_not_swallowed_as_optional_failure() -> None:
    session = AsyncMock()
    session.query.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await inspect_details(session, model())


async def test_shared_deadline_cancels_a_pending_metadata_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_timeout = asyncio.timeout
    budgets: list[float] = []

    def immediate_timeout(seconds: float) -> asyncio.Timeout:
        budgets.append(seconds)
        return original_timeout(0)

    async def pending(*_args: object, **_kwargs: object) -> None:
        await asyncio.Future[None]()

    monkeypatch.setattr("app.adapters.postgres.timescale.details.asyncio.timeout", immediate_timeout)
    session = AsyncMock()
    session.query.side_effect = pending
    result = await inspect_details(session, model())
    assert budgets == [5]
    assert result is not None and result.kind == "unavailable"
    assert "timed out" in result.reason


async def test_ordinary_relation_does_not_probe_timescale() -> None:
    session = AsyncMock()
    assert await inspect_details(session, model().model_copy(update={"specialization": None})) is None
    session.query.assert_not_awaited()
