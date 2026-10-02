"""What the console asks of the server: prepare, bindings, views, history.

Against a real PostgreSQL, because the point of a binding is what the database
makes of it (D62).
"""

import asyncio
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.queries import history
from app.queries.runs import ExecutionRun
from app.users import storage
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


async def _settled(
    client: AsyncClient, headers: dict[str, str], run_id: str, *, seconds: float = 15.0
) -> dict[str, Any]:
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


async def _run(
    client: AsyncClient, headers: dict[str, str], connector_id: str, text: str, **extra: Any
) -> dict[str, Any]:
    started = await client.post(
        f"{BASE}/runs",
        headers=headers,
        json={
            "run_id": str(uuid.uuid4()),
            "connector_id": connector_id,
            "text": text,
            **extra,
        },
    )
    assert started.status_code == 200, started.text
    return await _settled(client, headers, started.json()["id"])


async def _rows(
    client: AsyncClient, headers: dict[str, str], run: dict[str, Any]
) -> list[list[str | None]]:
    result_id = run["statements"][0]["result_id"]
    page = await client.get(f"{BASE}/results/{result_id}", headers=headers)
    assert page.status_code == 200, page.text
    rows: list[list[str | None]] = page.json()["rows"]
    return rows


# --- preparing --------------------------------------------------------------


async def test_the_source_says_where_the_statements_are(
    client: AsyncClient, db: AsyncSession
) -> None:
    """D62: the browser does not split SQL; it asks the source that owns the dialect."""
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)

    response = await client.post(
        f"{BASE}/prepare",
        headers=headers,
        json={"connector_id": connector_id, "text": "select 'a;b'; select :since"},
    )

    assert response.status_code == 200, response.text
    script = response.json()
    assert [statement["kind"] for statement in script["statements"]] == ["read", "read"]
    assert script["statements"][0]["text"] == "select 'a;b'"
    assert script["parameters"] == ["since"]


async def test_preparing_runs_nothing(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)

    response = await client.post(
        f"{BASE}/prepare",
        headers=headers,
        json={"connector_id": connector_id, "text": "drop table nothing_here"},
    )
    runs = await client.get(f"{BASE}/runs", headers=headers)

    assert response.status_code == 200
    assert response.json()["statements"][0]["kind"] == "ddl"
    assert runs.json()["count"] == 0


# --- bindings ---------------------------------------------------------------


async def test_a_value_is_bound_and_the_server_types_it_by_the_expression(
    client: AsyncClient, db: AsyncSession
) -> None:
    """D62: no type language here — PostgreSQL reads the expression."""
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)

    run = await _run(
        client,
        headers,
        connector_id,
        "select count(*) from generate_series(1, 10) i where i > :from_here",
        parameters=[{"name": "from_here", "value": "7"}],
    )

    assert run["status"] == "succeeded"
    assert await _rows(client, headers, run) == [["3"]]


async def test_a_value_is_never_written_into_the_statement(
    client: AsyncClient, db: AsyncSession
) -> None:
    """The classic injection, which is a value and stays one.

    Cast because a bare parameter in a select list has no expression to infer
    a type from — which is the same answer the hint below gives a person.
    """
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)

    run = await _run(
        client,
        headers,
        connector_id,
        "select :name::text as given",
        parameters=[{"name": "name", "value": "x'; drop table pg_class; --"}],
    )

    assert run["status"] == "succeeded"
    assert await _rows(client, headers, run) == [["x'; drop table pg_class; --"]]


async def test_a_per_cent_sign_survives_a_parameterised_statement(
    client: AsyncClient, db: AsyncSession
) -> None:
    """The driver reads one as a placeholder as soon as anything is bound."""
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)

    run = await _run(
        client,
        headers,
        connector_id,
        "select 'a%b' like '%' || :middle || '%' as matched",
        parameters=[{"name": "middle", "value": "%"}],
    )

    assert run["status"] == "succeeded"
    assert await _rows(client, headers, run) == [["true"]]


async def test_the_same_parameter_twice_is_one_value(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)

    run = await _run(
        client,
        headers,
        connector_id,
        "select :n::int + :n::int as twice",
        parameters=[{"name": "n", "value": "21"}],
    )

    assert await _rows(client, headers, run) == [["42"]]


async def test_sql_null_is_a_value_a_form_can_choose(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)

    run = await _run(
        client,
        headers,
        connector_id,
        "select :maybe::text is null as empty",
        parameters=[{"name": "maybe", "value": None}],
    )

    assert await _rows(client, headers, run) == [["true"]]


async def test_a_parameter_nobody_filled_in_is_named_rather_than_guessed(
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
            "text": "select :missing",
        },
    )

    assert response.status_code == 422
    assert "missing" in response.json()["detail"]


async def test_an_ambiguous_parameter_is_answered_with_a_hint(
    client: AsyncClient, db: AsyncSession
) -> None:
    """The server cannot infer a type here, and the way out is a cast."""
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)

    run = await _run(
        client,
        headers,
        connector_id,
        "select :maybe is null",
        parameters=[{"name": "maybe", "value": None}],
    )

    diagnostic = run["statements"][0]["diagnostic"]
    assert diagnostic["code"] == "42P18"
    assert "cast" in diagnostic["hint"]


async def test_a_run_keeps_the_names_of_its_bindings_and_none_of_the_values(
    client: AsyncClient, db: AsyncSession
) -> None:
    """D63: what was typed is not part of what happened."""
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)

    run = await _run(
        client,
        headers,
        connector_id,
        "select :token as given",
        parameters=[{"name": "token", "value": "a-recognisable-secret", "secret": True}],
    )

    assert run["parameters"] == [{"name": "token", "is_null": False, "secret": True}]
    stored = await db.get(ExecutionRun, uuid.UUID(run["id"]))
    assert stored is not None
    assert b"a-recognisable-secret" not in stored.text
    assert "a-recognisable-secret" not in str(stored.parameters)


async def test_a_document_remembers_the_values_it_was_told_to(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)
    created = await client.post(
        f"{BASE}/documents",
        headers=headers,
        json={
            "connector_id": connector_id,
            "body": "select :since",
            "parameters": {"since": "2026-01-01"},
        },
    )
    assert created.status_code == 200, created.text
    document = created.json()
    assert document["parameters"] == {"since": "2026-01-01"}

    read = await client.get(f"{BASE}/documents/{document['id']}", headers=headers)
    stored = await db.get(
        __import__("app.queries.models", fromlist=["QueryDocument"]).QueryDocument,
        uuid.UUID(document["id"]),
    )

    assert read.json()["parameters"] == {"since": "2026-01-01"}
    assert stored is not None
    assert stored.parameters is not None
    assert b"2026-01-01" not in stored.parameters


# --- reading what was captured ---------------------------------------------


async def test_a_snapshot_is_filtered_and_ordered_without_running_anything_again(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)
    run = await _run(
        client, headers, connector_id, "select i from generate_series(1, 12) i"
    )
    result_id = run["statements"][0]["result_id"]

    page = await client.post(
        f"{BASE}/results/{result_id}/page",
        headers=headers,
        json={
            "view": {
                "filters": [{"column": "0", "op": "gt", "value": "9"}],
                "sort": [{"column": "0", "descending": True}],
            },
            "limit": 2,
        },
    )

    assert page.status_code == 200, page.text
    assert page.json()["rows"] == [["12"], ["11"]]
    assert page.json()["total_rows"] == 3


async def test_a_filter_on_a_column_the_result_has_not_got_is_refused(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)
    run = await _run(client, headers, connector_id, "select 1")
    result_id = run["statements"][0]["result_id"]

    page = await client.post(
        f"{BASE}/results/{result_id}/page",
        headers=headers,
        json={"view": {"filters": [{"column": "9", "op": "eq", "value": "1"}]}},
    )

    assert page.status_code == 422


async def test_a_captured_result_is_downloaded_without_the_source(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)
    run = await _run(
        client, headers, connector_id, "select i from generate_series(1, 5) i"
    )
    result_id = run["statements"][0]["result_id"]

    everything = await client.post(
        f"{BASE}/results/{result_id}/download",
        headers=headers,
        json={"scope": "all", "title": "counts"},
    )
    page = await client.post(
        f"{BASE}/results/{result_id}/download",
        headers=headers,
        json={"scope": "page", "limit": 2},
    )

    assert everything.status_code == 200, everything.text
    assert everything.headers["content-type"].startswith("text/csv")
    assert "counts.csv" in everything.headers["content-disposition"]
    assert everything.text.strip().splitlines()[1:] == ['"1"', '"2"', '"3"', '"4"', '"5"']
    assert page.text.strip().splitlines()[1:] == ['"1"', '"2"']


async def test_a_downloaded_result_keeps_the_columns_on_screen_in_their_order(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)
    run = await _run(client, headers, connector_id, "select 1 as a, 2 as b, 3 as c")
    result_id = run["statements"][0]["result_id"]

    chosen = await client.post(
        f"{BASE}/results/{result_id}/download",
        headers=headers,
        json={"scope": "all", "columns": ["2", "0"]},
    )
    unknown = await client.post(
        f"{BASE}/results/{result_id}/download",
        headers=headers,
        json={"scope": "all", "columns": ["0", "9"]},
    )

    assert chosen.status_code == 200, chosen.text
    assert chosen.text.lstrip("﻿").strip().splitlines() == ['"c","a"', '"3","1"']
    # Refused rather than skipped: a layout that names a column the result has
    # not got is stale, and writing around it would shift the headings.
    assert unknown.status_code == 422


async def test_a_kept_result_is_filed_among_the_owner_s_files_and_not_sent_back(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)
    run = await _run(
        client, headers, connector_id, "select i from generate_series(1, 5) i"
    )
    result_id = run["statements"][0]["result_id"]

    response = await client.post(
        f"{BASE}/results/{result_id}/download/keep",
        headers=headers,
        json={"scope": "page", "limit": 3, "title": "counts"},
    )

    assert response.status_code == 200, response.text
    answer = response.json()
    assert answer["row_count"] == 3
    assert answer["filename"].startswith("counts-")
    assert "download_url" not in answer
    me = await client.get(f"{settings.API_V1_STR}/users/me", headers=headers)
    home = storage.home_dir(uuid.UUID(me.json()["id"]))
    saved = home / "downloads" / "results" / answer["filename"]
    assert saved.read_text(encoding="utf-8-sig").splitlines() == [
        '"i"',
        '"1"',
        '"2"',
        '"3"',
    ]


async def test_a_download_of_somebody_else_s_result_is_not_there(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    stranger = await _headers(client, db)
    connector_id = await _postgres(client, headers)
    run = await _run(client, headers, connector_id, "select 1")
    result_id = run["statements"][0]["result_id"]

    response = await client.post(
        f"{BASE}/results/{result_id}/download", headers=stranger, json={"scope": "all"}
    )

    assert response.status_code == 404


# --- history ----------------------------------------------------------------


async def test_history_lists_what_was_run_and_can_be_searched(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)
    await _run(client, headers, connector_id, "select 'invoices-marker'")
    await _run(client, headers, connector_id, "select 'people-marker'")

    listed = await client.get(f"{BASE}/runs", headers=headers)
    found = await client.get(
        f"{BASE}/runs", headers=headers, params={"search": "INVOICES-MARKER"}
    )

    assert listed.json()["count"] == 2
    assert found.json()["count"] == 1
    assert "invoices-marker" in found.json()["data"][0]["preview"]


async def test_history_search_decrypts_off_the_event_loop(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)
    await _run(client, headers, connector_id, "select 'ledger-marker'")
    on_loop: list[bool] = []
    original = history.text_of

    def watched(run: ExecutionRun) -> str:
        try:
            asyncio.get_running_loop()
            on_loop.append(True)
        except RuntimeError:
            on_loop.append(False)
        return original(run)

    monkeypatch.setattr(history, "text_of", watched)

    found = await client.get(
        f"{BASE}/runs", headers=headers, params={"search": "ledger-marker"}
    )

    assert found.json()["count"] == 1
    assert on_loop and not any(on_loop)


async def test_history_is_one_person_s_own(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    stranger = await _headers(client, db)
    connector_id = await _postgres(client, headers)
    run = await _run(client, headers, connector_id, "select 1")

    theirs = await client.get(f"{BASE}/runs", headers=stranger)
    text = await client.get(f"{BASE}/runs/{run['id']}/text", headers=stranger)

    assert theirs.json()["count"] == 0
    assert text.status_code == 404


async def test_the_text_of_a_run_is_asked_for_on_its_own(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)
    run = await _run(client, headers, connector_id, "select 'exactly this'")

    response = await client.get(f"{BASE}/runs/{run['id']}/text", headers=headers)

    assert response.status_code == 200
    assert response.json()["text"] == "select 'exactly this'"


async def test_deleting_history_leaves_nothing_behind(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)
    first = await _run(client, headers, connector_id, "select 1")
    await _run(client, headers, connector_id, "select 2")

    one = await client.post(
        f"{BASE}/runs/delete",
        headers=headers,
        json={"kind": "selected", "ids": [first["id"]]},
    )
    assert one.status_code == 200, one.text
    assert (await client.get(f"{BASE}/runs", headers=headers)).json()["count"] == 1
    assert await db.get(ExecutionRun, uuid.UUID(first["id"])) is None

    everything = await client.post(
        f"{BASE}/runs/delete", headers=headers, json={"kind": "all"}
    )

    assert everything.status_code == 200
    assert (await client.get(f"{BASE}/runs", headers=headers)).json()["count"] == 0


async def test_retention_is_chosen_from_what_the_interface_offers(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)

    default = await client.get(f"{BASE}/retention", headers=headers)
    chosen = await client.put(f"{BASE}/retention", headers=headers, json={"days": 7})
    refused = await client.put(f"{BASE}/retention", headers=headers, json={"days": 3})

    assert default.json() == {"days": 90, "max_runs": settings.QUERY_HISTORY_MAX_RUNS}
    assert chosen.status_code == 200, chosen.text
    assert chosen.json()["days"] == 7
    assert refused.status_code == 422


async def test_choosing_no_retention_lets_the_sweep_take_finished_runs(
    client: AsyncClient, db: AsyncSession
) -> None:
    """D63: with retention off, a row lasts through terminal publication only."""
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)
    run = await _run(client, headers, connector_id, "select 1")
    await client.put(f"{BASE}/retention", headers=headers, json={"days": 0})

    await history.sweep(db)

    assert await db.get(ExecutionRun, uuid.UUID(run["id"])) is None
    assert (await client.get(f"{BASE}/runs", headers=headers)).json()["count"] == 0
