"""`POST /search`: what a person finds, what nobody else does, and when it ends (S1)."""

import asyncio
import json
import logging
import time
import uuid
from collections.abc import Iterator
from dataclasses import replace
from typing import Any

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.main import app
from app.search.engine import SearchEngine
from app.search.models import Cost, ObjectsPlace
from app.search.providers import Asked, Found, ProviderCell
from tests.utils.database import working_postgres_options
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import random_email

SEARCH = f"{settings.API_V1_STR}/search"
CONNECTORS = f"{settings.API_V1_STR}/connectors"


def _engine() -> SearchEngine:
    engine: SearchEngine = app.state.search_engine
    return engine


async def _person(client: AsyncClient, db: AsyncSession) -> dict[str, str]:
    return await authentication_token_from_email(client=client, email=random_email(), db=db)


async def _postgres(
    client: AsyncClient, headers: dict[str, str], name: str, host: str = "localhost"
) -> str:
    response = await client.post(
        f"{CONNECTORS}/",
        headers=headers,
        json={
            "name": name,
            "adapter_type": "postgres",
            "options": {**working_postgres_options(), "host": host},
        },
    )
    assert response.status_code == 200, response.text
    return str(response.json()["id"])


async def _search(
    client: AsyncClient, headers: dict[str, str], words: str, **extra: Any
) -> list[dict[str, Any]]:
    response = await client.post(
        SEARCH, headers=headers, json={"words": words, "mode": "search", **extra}
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/jsonl")
    return [json.loads(line) for line in response.text.splitlines() if line]


def _hits(lines: list[dict[str, Any]], group: str | None = None) -> list[dict[str, Any]]:
    keys = {
        cell["key"]
        for line in lines
        if line["type"] == "plan"
        for cell in line["cells"]
        if group is None or cell["group"]["key"] == group
    }
    return [
        hit
        for line in lines
        if line["type"] == "cell" and line["key"] in keys
        for hit in line["hits"]
    ]


def _connection_ids(lines: list[dict[str, Any]]) -> set[str]:
    return {
        hit["target"]["connector_id"]
        for hit in _hits(lines, "connections")
        if hit["target"]["kind"] == "connection"
    }


def _settled(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """An answer with its cells in key order: a cell is sent as it finishes,
    and no two answers need finish theirs in the same order (D201)."""
    return [line for line in lines if line["type"] != "cell"] + sorted(
        (line for line in lines if line["type"] == "cell"), key=lambda line: line["key"]
    )


async def test_a_connection_is_found_by_its_name_its_type_and_its_host(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _person(client, db)
    marker = uuid.uuid4().hex[:8]
    connector_id = await _postgres(
        client, headers, f"Warehouse {marker}", host=f"db-{marker}.internal"
    )

    by_name = await _search(client, headers, f"warehouse {marker}")
    by_type = await _search(client, headers, "postgresql")
    by_host = await _search(client, headers, f"db-{marker}")

    assert connector_id in _connection_ids(by_name)
    assert connector_id in _connection_ids(by_type)
    assert connector_id in _connection_ids(by_host)
    [found] = [hit for hit in _hits(by_name) if hit["key"] == f"connection:{connector_id}"]
    assert found["match"]["field"] == "name"
    assert found["access"] == "own"
    assert found["open"] == "catalog"
    [hosted] = [hit for hit in _hits(by_host) if hit["key"] == f"connection:{connector_id}"]
    assert hosted["match"]["field"] == "details"
    assert [part["text"] for part in hosted["match"]["excerpt"] if part["hit"]] == [
        f"db-{marker}"
    ]


async def test_somebody_else_s_connection_is_found_by_nobody(
    client: AsyncClient, db: AsyncSession, superuser_token_headers: dict[str, str]
) -> None:
    owner = await _person(client, db)
    stranger = await _person(client, db)
    marker = uuid.uuid4().hex[:8]
    connector_id = await _postgres(client, owner, f"Ledger {marker}")

    assert connector_id in _connection_ids(await _search(client, owner, marker))
    assert _connection_ids(await _search(client, stranger, marker)) == set()
    # An administrator holds rights over accounts, not over data (D34).
    assert _connection_ids(await _search(client, superuser_token_headers, marker)) == set()


async def test_a_switched_off_connection_is_found_and_says_it_is_off(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _person(client, db)
    marker = uuid.uuid4().hex[:8]
    connector_id = await _postgres(client, headers, f"Archive {marker}")
    switched = await client.patch(
        f"{CONNECTORS}/{connector_id}", headers=headers, json={"enabled": False}
    )
    assert switched.status_code == 200, switched.text

    [found] = [
        hit
        for hit in _hits(await _search(client, headers, marker))
        if hit["key"] == f"connection:{connector_id}"
    ]

    assert found["facts"]["switched_off"] is True
    assert "Switched off" in found["detail"]
    # Not a source: it opens on its window, where it is switched back on.
    assert found["open"] == "connection"


@pytest.mark.parametrize("enabled", [True, False])
async def test_another_person_s_connection_named_by_the_browser_is_an_unknown_id(
    client: AsyncClient, db: AsyncSession, enabled: bool
) -> None:
    owner = await _person(client, db)
    stranger = await _person(client, db)
    theirs = await _postgres(client, owner, f"Private {uuid.uuid4().hex[:8]}")
    if not enabled:
        await client.patch(f"{CONNECTORS}/{theirs}", headers=owner, json={"enabled": False})
    unknown = str(uuid.uuid4())

    hinted = await _search(client, stranger, "private", context=[theirs])
    unhinted = await _search(client, stranger, "private", context=[unknown])
    scoped = await client.post(
        SEARCH,
        headers=stranger,
        json={
            "words": "private",
            "mode": "search",
            "only": [{"kind": "connection", "connector_id": theirs}],
        },
    )
    nowhere = await client.post(
        SEARCH,
        headers=stranger,
        json={
            "words": "private",
            "mode": "search",
            "only": [{"kind": "connection", "connector_id": unknown}],
        },
    )

    assert _settled(hinted) == _settled(unhinted)
    assert scoped.status_code == nowhere.status_code == 404
    assert scoped.json() == nowhere.json()


async def test_timescaledb_finds_postgresql(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    lines = await _search(client, normal_user_token_headers, "timescaledb")

    found = [hit["target"]["object_id"] for hit in _hits(lines, "objects:source_types")]
    assert "postgres" in found


async def test_a_guide_page_is_found_by_a_word_in_its_body(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    lines = await _search(client, normal_user_token_headers, "magnifier")

    [page] = [
        hit for hit in _hits(lines, "objects:guide") if hit["target"]["object_id"] == "connections"
    ]
    assert page["match"]["field"] == "body"
    assert page["match"]["match_class"] == "text"
    assert any(part["hit"] for part in page["match"]["excerpt"])


async def test_the_type_catalog_asks_its_one_provider(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    lines = await _search(
        client,
        normal_user_token_headers,
        "redis",
        lane="types",
        only=[{"kind": "objects", "provider": "source_types"}],
    )

    [plan] = [line for line in lines if line["type"] == "plan"]
    assert [cell["key"] for cell in plan["cells"]] == ["objects:source_types/names"]
    assert _hits(lines)[0]["target"]["object_id"] == "redis"
    assert _hits(lines)[0]["match"]["match_class"] == "exact"


@pytest.mark.parametrize("words", ["a", " b ", "one two three four five six seven eight nine"])
async def test_what_a_search_refuses(
    client: AsyncClient, normal_user_token_headers: dict[str, str], words: str
) -> None:
    response = await client.post(
        SEARCH, headers=normal_user_token_headers, json={"words": words, "mode": "typing"}
    )

    assert response.status_code == 422


# --- a provider that never answers -------------------------------------------


class _NeverAnswers:
    """Waits for ever, and says whether it was told to stop."""

    place = ObjectsPlace(provider="pipelines")
    title = "Never"

    def __init__(self, cost: Cost = "instant") -> None:
        self._cost = cost
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()

    def cells(self) -> tuple[ProviderCell, ...]:
        return (ProviderCell(field="names", cost=self._cost),)

    async def search(self, asked: Asked) -> Found:
        self.started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        return Found()


@pytest.fixture
def quick() -> Iterator[None]:
    """Deadlines short enough for a test to wait them out."""
    engine = _engine()
    kept = engine.limits
    engine.limits = replace(kept, cheap_seconds=0.3, costly_seconds=0.5, total_seconds=1.0)
    try:
        yield
    finally:
        engine.limits = kept


@pytest.fixture
def never() -> Iterator[_NeverAnswers]:
    provider = _NeverAnswers()
    with _engine().providing(provider):
        yield provider


@pytest.fixture
def never_costly() -> Iterator[_NeverAnswers]:
    provider = _NeverAnswers("costly")
    with _engine().providing(provider):
        yield provider


async def test_a_provider_that_never_answers_is_late_and_the_stream_ends_on_time(
    client: AsyncClient, normal_user_token_headers: dict[str, str], never: _NeverAnswers
) -> None:
    started = time.monotonic()
    response = await client.post(
        SEARCH,
        headers=normal_user_token_headers,
        json={"words": "never mind", "mode": "typing"},
    )
    took = time.monotonic() - started

    lines = [json.loads(line) for line in response.text.splitlines()]
    [late] = [
        line for line in lines if line["type"] == "cell" and line["key"] == "objects:pipelines/names"
    ]
    assert late["outcome"]["status"] == "late"
    assert late["outcome"]["deadline_seconds"] == settings.SEARCH_TYPING_SECONDS
    assert lines[-1]["type"] == "end"
    assert lines[-1]["superseded"] is False
    assert took < settings.SEARCH_TYPING_SECONDS + 1.5
    assert never.cancelled.is_set()


@pytest.mark.usefixtures("quick")
async def test_a_newer_request_ends_the_older_and_its_work(
    client: AsyncClient, normal_user_token_headers: dict[str, str], never_costly: _NeverAnswers
) -> None:
    older = asyncio.create_task(
        client.post(
            SEARCH,
            headers=normal_user_token_headers,
            json={
                "words": "first words",
                "mode": "search",
                "only": [{"kind": "objects", "provider": "pipelines"}],
            },
        )
    )
    await asyncio.wait_for(never_costly.started.wait(), 5)

    newer = await client.post(
        SEARCH,
        headers=normal_user_token_headers,
        json={
            "words": "second words",
            "mode": "search",
            "only": [{"kind": "objects", "provider": "guide"}],
        },
    )
    ended = await asyncio.wait_for(older, 5)

    assert newer.status_code == 200
    last = json.loads(ended.text.splitlines()[-1])
    assert last["type"] == "end" and last["superseded"] is True
    await asyncio.wait_for(never_costly.cancelled.wait(), 5)


async def test_the_words_reach_no_log_line(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    marker = f"wombat{uuid.uuid4().hex[:8]}"
    caplog.set_level(logging.DEBUG)

    await _search(client, normal_user_token_headers, marker)

    assert not [one for one in caplog.records if marker in one.getMessage()]
