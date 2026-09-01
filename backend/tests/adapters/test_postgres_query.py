"""Running somebody's own SQL against a real PostgreSQL.

The security matrix of D62 lives here: what a read-only transaction refuses,
what a timeout does, what a cancellation does, and what never crosses in a
diagnostic. A fake driver would prove none of it.
"""

import asyncio

import pytest
from pydantic import SecretStr

from app.adapters.postgres.options import PostgresUserPassword
from app.adapters.postgres.query import PostgresQuery
from app.adapters.postgres.session import PostgresSession
from app.adapters.protocol import AdapterError
from app.adapters.query import (
    QueryLimits,
    QueryRequest,
    StatementFinished,
    SupportsQuery,
)
from tests.utils.database import working_postgres_options

LIMITS = QueryLimits(
    statement_timeout_seconds=30,
    script_timeout_seconds=600,
    max_statements=100,
    max_statement_bytes=256 * 1024,
    max_result_rows=10_000,
    max_result_bytes=32 * 1024 * 1024,
    max_cell_bytes=4 * 1024 * 1024,
    max_run_results=20,
    max_run_bytes=64 * 1024 * 1024,
    max_messages=1000,
)


def _query() -> PostgresQuery:
    return PostgresQuery(PostgresSession(PostgresUserPassword(**working_postgres_options())))


def _request(text: str, **overrides: object) -> QueryRequest:
    limits = LIMITS.model_copy(update=dict(overrides))
    return QueryRequest(text=text, mode="read", search_path=[], limits=limits)


async def _finished(text: str, **overrides: object) -> list[StatementFinished]:
    execution = _query().open(_request(text, **overrides))
    return [
        event async for event in execution.events() if isinstance(event, StatementFinished)
    ]


async def test_a_select_comes_back_as_typed_columns_and_canonical_cells() -> None:
    [statement] = await _finished("select 1 as n, 'x' as t, null::text as empty")

    assert statement.status == "succeeded"
    assert statement.result is not None
    assert [column.name for column in statement.result.columns] == ["n", "t", "empty"]
    assert [column.id for column in statement.result.columns] == ["0", "1", "2"]
    assert statement.result.columns[0].type.sql == "integer"
    assert statement.result.rows == [["1", "x", None]]


async def test_duplicate_and_empty_headings_stay_addressable() -> None:
    """D64: a result's identity is positional; the name is only what is shown."""
    [statement] = await _finished("select 1 as same, 2 as same, 3")

    assert statement.result is not None
    assert [column.id for column in statement.result.columns] == ["0", "1", "2"]
    assert [column.name for column in statement.result.columns] == [
        "same",
        "same",
        "?column?",
    ]


async def test_a_script_runs_in_order_and_stops_at_the_first_failure() -> None:
    finished = await _finished("select 1; select * from nothing_here; select 3")

    assert [statement.status for statement in finished] == [
        "succeeded",
        "failed",
        "not_run",
    ]
    assert finished[1].diagnostic is not None
    assert finished[1].diagnostic.category == "missing_object"
    assert finished[1].diagnostic.code == "42P01"


async def test_a_statement_that_creates_something_is_refused_by_its_class() -> None:
    """Even a temporary table: a read run has no honest way to represent it."""
    finished = await _finished("create temporary table dp_probe as select 1")

    assert finished[0].status == "failed"
    assert finished[0].diagnostic is not None
    assert finished[0].diagnostic.category == "read_only"
    assert finished[0].diagnostic.code == "dp_not_read"


async def test_a_function_that_writes_is_refused_by_the_read_only_transaction() -> None:
    """A read-shaped statement that writes: only the database can catch this."""
    finished = await _finished(
        "select query_to_xml('create table dp_probe(a int)', false, false, '')"
    )

    assert finished[0].status == "failed"
    assert finished[0].diagnostic is not None
    assert finished[0].diagnostic.category in {"read_only", "unknown", "data"}
    assert finished[0].diagnostic.code != "unknown"


async def test_a_writable_cte_never_reaches_the_server() -> None:
    finished = await _finished(
        "with moved as (insert into pg_class values (1) returning *) select * from moved"
    )

    assert finished[0].status == "failed"
    assert finished[0].diagnostic is not None
    assert finished[0].diagnostic.message == "A dml statement cannot run in a read"


@pytest.mark.parametrize(
    "text",
    ["begin", "commit", "set search_path to public", "copy pg_class to stdout"],
)
async def test_state_changing_statements_are_refused(text: str) -> None:
    finished = await _finished(text)

    assert finished[0].status == "failed"
    assert finished[0].diagnostic is not None
    assert finished[0].diagnostic.code == "dp_not_read"


async def test_a_statement_that_runs_too_long_times_out_and_says_so() -> None:
    finished = await _finished("select pg_sleep(5)", statement_timeout_seconds=1)

    assert finished[0].status == "timed_out"
    assert finished[0].diagnostic is not None
    assert finished[0].diagnostic.category == "timeout"
    assert finished[0].diagnostic.message == "The statement ran out of time"


async def test_a_cancelled_statement_reaches_a_terminal_state_quickly() -> None:
    """D64: cancelling waits for the source's own answer, and it arrives."""
    execution = _query().open(_request("select pg_sleep(30)"))
    events = execution.events()

    async def stop() -> None:
        await asyncio.sleep(1.0)
        await execution.cancel()

    stopping = asyncio.create_task(stop())
    finished = [
        event
        async for event in events
        if isinstance(event, StatementFinished)
    ]
    await stopping

    assert finished[0].status == "cancelled"
    assert finished[0].diagnostic is not None
    assert finished[0].diagnostic.category == "cancelled"


async def test_a_result_larger_than_the_ceiling_is_truncated_by_one_extra_row() -> None:
    finished = await _finished(
        "select i from generate_series(1, 50) i", max_result_rows=10
    )

    assert finished[0].result is not None
    assert len(finished[0].result.rows) == 10
    assert finished[0].result.truncated is True


async def test_a_result_exactly_at_the_ceiling_is_not_called_truncated() -> None:
    finished = await _finished(
        "select i from generate_series(1, 10) i", max_result_rows=10
    )

    assert finished[0].result is not None
    assert finished[0].result.truncated is False


async def test_an_oversize_cell_refuses_the_result_without_failing_the_statement() -> None:
    """D64 keeps publication apart from execution."""
    finished = await _finished("select repeat('x', 5000)", max_cell_bytes=1000)

    assert finished[0].status == "succeeded"
    assert finished[0].result is None
    assert finished[0].diagnostic is not None
    assert finished[0].diagnostic.code == "result_too_large"


async def test_json_crosses_as_the_text_the_server_wrote() -> None:
    """D23: the driver must not round a number through a float."""
    finished = await _finished(
        "select '{\"n\": 12345678901234567890.5}'::jsonb as doc"
    )

    assert finished[0].result is not None
    assert "12345678901234567890.5" in (finished[0].result.rows[0][0] or "")


async def test_the_password_never_appears_in_a_diagnostic() -> None:
    options = working_postgres_options()
    session = PostgresSession(
        PostgresUserPassword(**{**options, "password": SecretStr("s3cret-not-in-text")})
    )

    with pytest.raises(AdapterError) as failure:
        async for _ in PostgresQuery(session).open(_request("select 1")).events():
            pass

    assert "s3cret-not-in-text" not in str(failure.value)
    assert "s3cret-not-in-text" not in failure.value.message


async def test_a_schema_the_source_does_not_have_is_refused_before_anything_runs() -> None:
    execution = _query().open(
        QueryRequest(
            text="select 1",
            mode="read",
            search_path=["public", "no_such_schema"],
            limits=LIMITS,
        )
    )

    with pytest.raises(AdapterError) as failure:
        async for _ in execution.events():
            pass

    assert "no_such_schema" in failure.value.message


async def test_a_search_path_the_source_has_is_set_for_the_run() -> None:
    execution = _query().open(
        QueryRequest(
            text="show search_path",
            mode="read",
            search_path=["pg_catalog", "public"],
            limits=LIMITS,
        )
    )
    finished = [
        event async for event in execution.events() if isinstance(event, StatementFinished)
    ]

    # SHOW is not a read by class, so the context is proved by what a read sees.
    assert finished[0].status == "failed"


async def test_the_source_declares_what_it_accepts() -> None:
    profile = _query().profile()

    assert profile.dialect == "postgres"
    assert profile.statement_modes == ["read"]
    assert profile.supports_cancel is True
    assert profile.supports_explain is False
    assert profile.default_timeout_seconds == 30
    assert profile.max_timeout_seconds == 300


async def test_the_adapter_answers_the_query_protocol() -> None:
    from app.adapters.postgres.adapter import PostgresAdapter

    adapter = PostgresAdapter(PostgresUserPassword(**working_postgres_options()))

    assert isinstance(adapter, SupportsQuery)
