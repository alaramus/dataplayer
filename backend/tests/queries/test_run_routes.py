"""Starting a run, watching it, stopping it, and reading what it captured.

Against a real PostgreSQL connection, because the lifecycle is only worth
anything if the source is really running the statements (D64).
"""

import asyncio
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.queries.execution import recover_interrupted
from app.queries.runs import ExecutionRun, StatementRun
from tests.queries.conftest import silent_connector
from tests.utils.database import working_postgres_options
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import random_email

BASE = f"{settings.API_V1_STR}/queries"
CONNECTORS = f"{settings.API_V1_STR}/connectors"


async def _headers(client: AsyncClient, db: AsyncSession) -> dict[str, str]:
    return await authentication_token_from_email(
        client=client, email=random_email(), db=db
    )


async def _postgres(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        f"{CONNECTORS}/",
        headers=headers,
        json={
            "name": f"pg {uuid.uuid4()}",
            "adapter_type": "postgres",
            "options": working_postgres_options(),
        },
    )
    assert response.status_code == 200, response.text
    return str(response.json()["id"])


async def _file(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        f"{CONNECTORS}/",
        headers=headers,
        json={
            "name": f"files {uuid.uuid4()}",
            "adapter_type": "file",
            "options": {"path": "/"},
        },
    )
    assert response.status_code == 200, response.text
    return str(response.json()["id"])


async def _start(
    client: AsyncClient,
    headers: dict[str, str],
    connector_id: str,
    text: str,
    **extra: Any,
) -> dict[str, Any]:
    body = {
        "run_id": str(uuid.uuid4()),
        "connector_id": connector_id,
        "text": text,
        **extra,
    }
    response = await client.post(f"{BASE}/runs", headers=headers, json=body)
    assert response.status_code == 200, response.text
    started: dict[str, Any] = response.json()
    return started


async def _settled(
    client: AsyncClient, headers: dict[str, str], run_id: str, *, seconds: float = 15.0
) -> dict[str, Any]:
    """Poll the route that is the authority until the run is over."""
    deadline = asyncio.get_running_loop().time() + seconds
    while True:
        response = await client.get(f"{BASE}/runs/{run_id}", headers=headers)
        assert response.status_code == 200, response.text
        run: dict[str, Any] = response.json()
        if run["status"] not in {"accepted", "running", "cancelling"}:
            return run
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"The run never settled: {run['status']}")
        await asyncio.sleep(0.05)


async def test_a_read_run_captures_a_result_a_page_can_be_read_from(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)

    started = await _start(
        client, headers, connector_id, "select i from generate_series(1, 5) i"
    )
    assert started["status"] == "accepted"
    assert started["statement_count"] == 1

    run = await _settled(client, headers, started["id"])

    assert run["status"] == "succeeded"
    [statement] = run["statements"]
    assert statement["status"] == "succeeded"
    assert statement["row_count"] == 5
    result_id = statement["result_id"]
    assert result_id is not None

    page = await client.get(
        f"{BASE}/results/{result_id}", headers=headers, params={"limit": 2}
    )
    assert page.status_code == 200, page.text
    captured = page.json()
    assert captured["total_rows"] == 5
    assert captured["rows"] == [["1"], ["2"]]
    assert captured["truncated"] is False
    assert [column["id"] for column in captured["columns"]] == ["0"]


async def test_paging_reads_the_snapshot_rather_than_the_source(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)
    started = await _start(
        client, headers, connector_id, "select i from generate_series(1, 5) i"
    )
    run = await _settled(client, headers, started["id"])
    result_id = run["statements"][0]["result_id"]

    page = await client.get(
        f"{BASE}/results/{result_id}",
        headers=headers,
        params={"offset": 3, "limit": 100},
    )

    assert page.json()["rows"] == [["4"], ["5"]]
    assert page.json()["offset"] == 3


async def test_a_result_belonging_to_somebody_else_is_not_there(
    client: AsyncClient, db: AsyncSession
) -> None:
    """An opaque id is not an authorisation."""
    headers = await _headers(client, db)
    stranger = await _headers(client, db)
    connector_id = await _postgres(client, headers)
    started = await _start(client, headers, connector_id, "select 1")
    run = await _settled(client, headers, started["id"])
    result_id = run["statements"][0]["result_id"]

    response = await client.get(f"{BASE}/results/{result_id}", headers=stranger)

    assert response.status_code == 404


async def test_a_script_stops_at_the_first_failure_and_says_what_did_not_run(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)

    started = await _start(
        client,
        headers,
        connector_id,
        "select 1; select * from nothing_here; select 3",
        scope="script",
    )
    run = await _settled(client, headers, started["id"])

    assert run["status"] == "failed"
    assert [statement["status"] for statement in run["statements"]] == [
        "succeeded",
        "failed",
        "not_run",
    ]
    diagnostic = run["statements"][1]["diagnostic"]
    assert diagnostic["code"] == "42P01"
    assert diagnostic["category"] == "missing_object"


async def test_a_statement_this_slice_cannot_run_is_refused_before_a_run_exists(
    client: AsyncClient, db: AsyncSession
) -> None:
    """Nothing happened, so this is a refusal rather than an outcome (D62)."""
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)

    response = await client.post(
        f"{BASE}/runs",
        headers=headers,
        json={
            "run_id": str(uuid.uuid4()),
            "connector_id": connector_id,
            "text": "select 1; delete from pg_class",
            "scope": "script",
        },
    )

    assert response.status_code == 422
    assert "Statement 2" in response.json()["detail"]
    assert "dml" in response.json()["detail"]


async def test_ordinary_run_never_falls_back_to_running_the_lot(
    client: AsyncClient, db: AsyncSession
) -> None:
    """D65: several statements is the other command, and it is asked for."""
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)

    response = await client.post(
        f"{BASE}/runs",
        headers=headers,
        json={
            "run_id": str(uuid.uuid4()),
            "connector_id": connector_id,
            "text": "select 1; select 2",
        },
    )

    assert response.status_code == 422
    assert "script" in response.json()["detail"]


async def test_an_empty_text_is_refused(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)

    response = await client.post(
        f"{BASE}/runs",
        headers=headers,
        json={
            "run_id": str(uuid.uuid4()),
            "connector_id": connector_id,
            "text": "   \n -- nothing here \n",
        },
    )

    assert response.status_code == 422


async def test_the_same_command_twice_is_one_run(
    client: AsyncClient, db: AsyncSession
) -> None:
    """D64: starting a run is idempotent by the id the client chose."""
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)
    body = {
        "run_id": str(uuid.uuid4()),
        "connector_id": connector_id,
        "text": "select 1",
    }

    first = await client.post(f"{BASE}/runs", headers=headers, json=body)
    again = await client.post(f"{BASE}/runs", headers=headers, json=body)

    assert first.status_code == 200, first.text
    assert again.status_code == 200, again.text
    assert again.json()["id"] == first.json()["id"]


async def test_the_same_id_with_another_command_is_a_conflict(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)
    run_id = str(uuid.uuid4())
    await client.post(
        f"{BASE}/runs",
        headers=headers,
        json={"run_id": run_id, "connector_id": connector_id, "text": "select 1"},
    )

    response = await client.post(
        f"{BASE}/runs",
        headers=headers,
        json={"run_id": run_id, "connector_id": connector_id, "text": "select 2"},
    )

    assert response.status_code == 409


async def test_a_run_belonging_to_somebody_else_does_not_exist(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    stranger = await _headers(client, db)
    connector_id = await _postgres(client, headers)
    started = await _start(client, headers, connector_id, "select 1")

    read = await client.get(f"{BASE}/runs/{started['id']}", headers=stranger)
    cancelled = await client.post(
        f"{BASE}/runs/{started['id']}/cancel", headers=stranger
    )

    assert read.status_code == 404
    assert cancelled.status_code == 404


@pytest.mark.usefixtures("silent_source")
async def test_a_source_that_does_not_run_queries_says_so(
    client: AsyncClient, db: AsyncSession
) -> None:
    """A capability is asked for, never assumed from the type of a source."""
    headers = await _headers(client, db)
    connector_id = await silent_connector(client, headers)

    response = await client.post(
        f"{BASE}/runs",
        headers=headers,
        json={
            "run_id": str(uuid.uuid4()),
            "connector_id": connector_id,
            "text": "select 1",
        },
    )
    profile = await client.get(
        f"{BASE}/connectors/{connector_id}/profile", headers=headers
    )

    assert response.status_code == 501
    assert profile.status_code == 501


async def test_a_source_that_does_states_what_it_accepts(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)

    response = await client.get(
        f"{BASE}/connectors/{connector_id}/profile", headers=headers
    )

    assert response.status_code == 200, response.text
    profile = response.json()
    assert profile["dialect"] == "postgres"
    assert profile["statement_modes"] == ["read", "auto_commit", "manual"]
    assert profile["parameter_syntax"] == "named_colon"


async def test_a_long_query_is_cancelled_and_reaches_a_terminal_state(
    client: AsyncClient, db: AsyncSession
) -> None:
    """D64: cancel is a separate command, and the run settles by itself."""
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)
    started = await _start(client, headers, connector_id, "select pg_sleep(20)")

    # Let the task actually reach the server before asking it to stop.
    await asyncio.sleep(1.0)
    cancelling = await client.post(
        f"{BASE}/runs/{started['id']}/cancel", headers=headers
    )
    assert cancelling.status_code == 200, cancelling.text
    assert cancelling.json()["status"] in {"cancelling", "cancelled"}

    run = await _settled(client, headers, started["id"], seconds=10.0)

    assert run["status"] == "cancelled"
    assert run["statements"][0]["status"] == "cancelled"


async def test_cancelling_twice_is_the_same_as_cancelling_once(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)
    started = await _start(client, headers, connector_id, "select 1")
    await _settled(client, headers, started["id"])

    first = await client.post(f"{BASE}/runs/{started['id']}/cancel", headers=headers)
    again = await client.post(f"{BASE}/runs/{started['id']}/cancel", headers=headers)

    assert first.status_code == 200
    assert again.status_code == 200
    assert again.json()["status"] == first.json()["status"]


async def test_a_statement_that_runs_too_long_ends_as_timed_out(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)

    started = await _start(
        client, headers, connector_id, "select pg_sleep(10)", timeout_seconds=1
    )
    run = await _settled(client, headers, started["id"])

    assert run["status"] == "timed_out"
    assert run["statements"][0]["diagnostic"]["category"] == "timeout"


async def test_a_run_keeps_the_text_it_executed_encrypted(
    client: AsyncClient, db: AsyncSession
) -> None:
    """D63: the executed text is a snapshot, and it is not readable in the row."""
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)
    started = await _start(
        client, headers, connector_id, "select 'a-recognisable-literal'"
    )
    await _settled(client, headers, started["id"])

    stored = await db.get(ExecutionRun, uuid.UUID(started["id"]))

    assert stored is not None
    assert b"a-recognisable-literal" not in stored.text


async def test_a_restart_settles_whatever_was_left_running(
    client: AsyncClient, db: AsyncSession
) -> None:
    """D64: non-terminal rows become interrupted, and SQL is never replayed."""
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)
    started = await _start(client, headers, connector_id, "select 1")
    await _settled(client, headers, started["id"])

    stranded = await db.get(ExecutionRun, uuid.UUID(started["id"]))
    assert stranded is not None
    stranded.status = "running"
    db.add(stranded)
    statement = await db.get(StatementRun, (stranded.id, 0))
    assert statement is not None
    statement.status = "running"
    db.add(statement)
    await db.commit()

    settled = await recover_interrupted(db)

    assert settled >= 1
    read = await client.get(f"{BASE}/runs/{started['id']}", headers=headers)
    assert read.json()["status"] == "interrupted"
    assert read.json()["statements"][0]["status"] == "not_run"


@pytest.mark.parametrize("field", ["run_id", "connector_id"])
async def test_a_malformed_command_is_refused_by_the_schema(
    client: AsyncClient, db: AsyncSession, field: str
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)
    body = {
        "run_id": str(uuid.uuid4()),
        "connector_id": connector_id,
        "text": "select 1",
        field: "not a uuid",
    }

    response = await client.post(f"{BASE}/runs", headers=headers, json=body)

    assert response.status_code == 422


async def _document(
    client: AsyncClient, headers: dict[str, str], connector_id: str
) -> str:
    response = await client.post(
        f"{BASE}/documents",
        headers=headers,
        json={"connector_id": connector_id, "body": "select 1"},
    )
    assert response.status_code == 200, response.text
    return str(response.json()["id"])


async def _stop(client: AsyncClient, headers: dict[str, str], run_id: str) -> None:
    await client.post(f"{BASE}/runs/{run_id}/cancel", headers=headers)
    await _settled(client, headers, run_id, seconds=10.0)


async def test_more_runs_at_once_than_allowed_are_refused_rather_than_queued(
    client: AsyncClient, db: AsyncSession
) -> None:
    """D64: excess is refused immediately, not put in an invisible queue."""
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)
    started = [
        await _start(client, headers, connector_id, "select pg_sleep(5)")
        for _ in range(settings.QUERY_MAX_ACTIVE_RUNS)
    ]
    # The tasks have to have actually started before the count means anything.
    await asyncio.sleep(0.5)

    try:
        refused = await client.post(
            f"{BASE}/runs",
            headers=headers,
            json={
                "run_id": str(uuid.uuid4()),
                "connector_id": connector_id,
                "text": "select 1",
            },
        )

        assert refused.status_code == 429
        assert str(settings.QUERY_MAX_ACTIVE_RUNS) in refused.json()["detail"]
    finally:
        for run in started:
            await _stop(client, headers, run["id"])


async def test_one_document_runs_one_thing_at_a_time(
    client: AsyncClient, db: AsyncSession
) -> None:
    """Another document is the explicit way to run two things at once (D64)."""
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)
    document_id = await _document(client, headers, connector_id)
    first = await _start(
        client,
        headers,
        connector_id,
        "select pg_sleep(5)",
        document_id=document_id,
        document_revision=1,
    )
    await asyncio.sleep(0.5)

    try:
        second = await client.post(
            f"{BASE}/runs",
            headers=headers,
            json={
                "run_id": str(uuid.uuid4()),
                "connector_id": connector_id,
                "text": "select 2",
                "document_id": document_id,
                "document_revision": 1,
            },
        )

        assert second.status_code == 409
    finally:
        await _stop(client, headers, first["id"])


async def test_a_run_takes_the_schema_context_of_its_document(
    client: AsyncClient, db: AsyncSession
) -> None:
    """D63: the context is captured with the run rather than sent by a client."""
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)
    created = await client.post(
        f"{BASE}/documents",
        headers=headers,
        json={
            "connector_id": connector_id,
            "body": "select 1",
            "search_path": ["no_such_schema"],
        },
    )
    assert created.status_code == 200, created.text
    document_id = created.json()["id"]

    started = await _start(
        client,
        headers,
        connector_id,
        "select 1",
        document_id=document_id,
        document_revision=1,
    )
    run = await _settled(client, headers, started["id"])

    assert run["status"] == "failed"
    assert "no_such_schema" in (run["error"] or "")


async def test_a_document_belonging_to_somebody_else_cannot_be_run(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    stranger = await _headers(client, db)
    connector_id = await _postgres(client, headers)
    document_id = await _document(client, headers, connector_id)
    # The stranger can see the connection, so only the document stands in
    # their way.
    grant = await client.put(
        f"{CONNECTORS}/{connector_id}/grants",
        headers=headers,
        json={"user_id": str(await _user_id(client, stranger)), "access": "read"},
    )
    assert grant.status_code == 200, grant.text

    response = await client.post(
        f"{BASE}/runs",
        headers=stranger,
        json={
            "run_id": str(uuid.uuid4()),
            "connector_id": connector_id,
            "text": "select 1",
            "document_id": document_id,
        },
    )

    assert response.status_code == 404


async def _user_id(client: AsyncClient, headers: dict[str, str]) -> uuid.UUID:
    response = await client.get(f"{settings.API_V1_STR}/users/me", headers=headers)
    assert response.status_code == 200, response.text
    return uuid.UUID(response.json()["id"])
