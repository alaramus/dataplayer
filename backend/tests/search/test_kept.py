"""Kept lists of names: the owner's switch, the passes, and the cell they answer
(D212–D216).

A pass is run here by calling the worker's own function, as the process would
on its tick: the suite does not start the process.
"""

import json
import uuid
from collections.abc import AsyncGenerator, AsyncIterator
from pathlib import Path
from typing import Any, ClassVar

import pytest
from httpx import AsyncClient, Response
from pydantic import BaseModel
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters import registry
from app.adapters.catalog import FileNode
from app.adapters.protocol import AdapterError, ConnectionCheckResult
from app.adapters.search import KeptName, NameBatch, SearchBounds
from app.connectors.models import Connector
from app.core.config import settings
from app.core.db import async_session_maker
from app.core.schemas import get_datetime_utc
from app.search import kept, keeper
from app.search.keep import SearchKeep, SearchName
from app.users import crud
from tests.utils.database import working_postgres_options
from tests.utils.keyspace import empty_keyspace, redis_options
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import random_email

SEARCH = f"{settings.API_V1_STR}/search"
KEPT = f"{settings.API_V1_STR}/search/kept"
CONNECTORS = f"{settings.API_V1_STR}/connectors"


@pytest.fixture
async def person(client: AsyncClient, db: AsyncSession) -> dict[str, str]:
    return await authentication_token_from_email(client=client, email=random_email(), db=db)


async def _connector(
    client: AsyncClient, headers: dict[str, str], adapter_type: str, options: dict[str, Any]
) -> str:
    response = await client.post(
        f"{CONNECTORS}/",
        headers=headers,
        json={
            "name": f"{adapter_type} {uuid.uuid4().hex[:8]}",
            "adapter_type": adapter_type,
            "options": options,
        },
    )
    assert response.status_code == 200, response.text
    return str(response.json()["id"])


async def _keep(
    client: AsyncClient, headers: dict[str, str], connector_id: str, keep: bool = True
) -> Response:
    return await client.put(
        f"{KEPT}/{connector_id}", headers=headers, json={"keep": keep, "window_seconds": 3600}
    )


async def _pass(connector_id: str) -> None:
    async with async_session_maker() as session:
        connector = await session.get(Connector, uuid.UUID(connector_id))
    assert connector is not None
    await keeper.run_pass(connector)


async def _kept_postgres(client: AsyncClient, headers: dict[str, str]) -> str:
    connector_id = await _connector(client, headers, "postgres", working_postgres_options())
    assert (await _keep(client, headers, connector_id)).status_code == 200
    await _pass(connector_id)
    return connector_id


async def _search(
    client: AsyncClient, headers: dict[str, str], words: str, mode: str = "typing"
) -> list[dict[str, Any]]:
    response = await client.post(SEARCH, headers=headers, json={"words": words, "mode": mode})
    assert response.status_code == 200, response.text
    return [json.loads(line) for line in response.text.splitlines() if line]


def _names_cell(lines: list[dict[str, Any]], connector_id: str) -> dict[str, Any]:
    [plan] = [line for line in lines if line["type"] == "plan"]
    [planned] = [
        cell
        for cell in plan["cells"]
        if cell["connector_id"] == connector_id and cell["cell"]["field"] == "names"
    ]
    finished = {line["key"]: line for line in lines if line["type"] == "cell"}
    return {**planned, **finished.get(planned["key"], {})}


async def _count(connector_id: str) -> int:
    async with async_session_maker() as session:
        return (
            await session.exec(
                select(func.count())
                .select_from(SearchName)
                .where(col(SearchName.connector_id) == uuid.UUID(connector_id))
            )
        ).one()


async def _row(connector_id: str) -> SearchKeep:
    async with async_session_maker() as session:
        row = await session.get(SearchKeep, uuid.UUID(connector_id))
    assert row is not None
    return row


# --- the cell a kept list answers --------------------------------------------


async def test_a_kept_list_answers_while_typing_without_asking_the_server(
    client: AsyncClient, person: dict[str, str]
) -> None:
    """Against the system catalog, which always holds hundreds of relations.
    Not in context and still asked while typing: a kept cell is instant."""
    connector_id = await _kept_postgres(client, person)

    state = (await client.get(f"{KEPT}/{connector_id}", headers=person)).json()
    cell = _names_cell(await _search(client, person, "class"), connector_id)

    assert state["status"] == "kept"
    assert state["names"] > 100
    assert state["kept_at"] is not None
    assert cell["way"] == "kept"
    assert cell["cost"] == "instant"
    assert cell["outcome"]["way"] == "kept"
    assert cell["outcome"]["as_of"] is not None
    [pg_class] = [
        hit for hit in cell["hits"] if hit["target"]["node_id"] == "pg_catalog.pg_class"
    ]
    assert pg_class["via"] == "kept"
    assert pg_class["as_of"] == cell["outcome"]["as_of"]
    assert pg_class["target"]["parent_id"] == "pg_catalog"
    assert pg_class["target"]["node"]["kind"] == "table"
    assert pg_class["match"]["match_class"] == "word"


async def test_an_exact_name_comes_first_from_a_kept_list(
    client: AsyncClient, person: dict[str, str]
) -> None:
    connector_id = await _kept_postgres(client, person)

    cell = _names_cell(await _search(client, person, "pg_class", "search"), connector_id)

    assert cell["hits"][0]["target"]["name"] == "pg_class"
    assert cell["hits"][0]["match"]["match_class"] == "exact"


async def test_a_percent_sign_in_a_kept_list_is_a_character(
    client: AsyncClient, person: dict[str, str]
) -> None:
    connector_id = await _kept_postgres(client, person)

    cell = _names_cell(await _search(client, person, "100%", "search"), connector_id)

    assert cell["way"] == "kept"
    assert cell["hits"] == []


async def test_words_too_short_for_trigrams_are_asked_live(
    client: AsyncClient, person: dict[str, str]
) -> None:
    connector_id = await _kept_postgres(client, person)

    cell = _names_cell(await _search(client, person, "pg", "search"), connector_id)

    assert cell["way"] == "live"


async def test_a_stale_list_is_not_asked_until_it_is_read_again(
    client: AsyncClient, person: dict[str, str]
) -> None:
    connector_id = await _kept_postgres(client, person)

    await kept.names_changed(uuid.UUID(connector_id))
    stale = _names_cell(await _search(client, person, "class", "search"), connector_id)
    row = await _row(connector_id)
    due = keeper.due(row, get_datetime_utc())
    await _pass(connector_id)
    fresh = _names_cell(await _search(client, person, "class", "search"), connector_id)

    assert stale["way"] == "live"
    assert due
    assert fresh["way"] == "kept"


async def test_a_list_older_than_its_window_is_not_asked(
    client: AsyncClient, person: dict[str, str]
) -> None:
    connector_id = await _kept_postgres(client, person)
    async with async_session_maker() as session:
        row = await session.get(SearchKeep, uuid.UUID(connector_id))
        assert row is not None and row.kept_at is not None
        row.window_seconds = 3600
        row.kept_at = row.kept_at.replace(year=row.kept_at.year - 1)
        session.add(row)
        await session.commit()

    cell = _names_cell(await _search(client, person, "class", "search"), connector_id)

    assert cell["way"] == "live"


async def test_a_switched_off_connection_s_names_are_found_by_nobody(
    client: AsyncClient, person: dict[str, str]
) -> None:
    connector_id = await _kept_postgres(client, person)
    await client.patch(f"{CONNECTORS}/{connector_id}", headers=person, json={"enabled": False})
    me = (await client.get(f"{settings.API_V1_STR}/users/me", headers=person)).json()

    cell = _names_cell(await _search(client, person, "class", "search"), connector_id)
    async with async_session_maker() as session:
        found = await kept.find(
            session, uuid.UUID(me["id"]), uuid.UUID(connector_id), ("class",), 10
        )

    assert cell["outcome"]["reason"] == "switched_off"
    assert found == []


async def test_somebody_without_standing_finds_nothing_in_a_kept_list(
    client: AsyncClient, person: dict[str, str]
) -> None:
    """The standing is inside the query, whatever asked it (D199)."""
    connector_id = await _kept_postgres(client, person)

    async with async_session_maker() as session:
        found = await kept.find(session, uuid.uuid4(), uuid.UUID(connector_id), ("class",), 10)

    assert found == []


# --- the owner's switch --------------------------------------------------------


@pytest.fixture
async def colleague(client: AsyncClient, db: AsyncSession) -> tuple[str, dict[str, str]]:
    email = random_email()
    headers = await authentication_token_from_email(client=client, email=email, db=db)
    user = await crud.get_user_by_email(session=db, email=email)
    assert user is not None
    return str(user.id), headers


async def test_only_the_owner_keeps_a_list_and_a_grantee_sees_its_state(
    client: AsyncClient, person: dict[str, str], colleague: tuple[str, dict[str, str]]
) -> None:
    connector_id = await _kept_postgres(client, person)
    colleague_id, theirs = colleague
    granted = await client.put(
        f"{CONNECTORS}/{connector_id}/grants",
        headers=person,
        json={"user_id": colleague_id, "access": "structure"},
    )
    assert granted.status_code == 200, granted.text

    refused = await _keep(client, theirs, connector_id, keep=False)
    refresh = await client.post(f"{KEPT}/{connector_id}/refresh", headers=theirs)
    state = await client.get(f"{KEPT}/{connector_id}", headers=theirs)
    overview = await client.get(KEPT, headers=theirs)

    assert refused.status_code == 403
    assert refresh.status_code == 403
    assert state.json()["may_change"] is False
    assert state.json()["status"] == "kept"
    assert state.json()["owner_email"] is not None
    assert connector_id in [one["connector_id"] for one in overview.json()["lists"]]
    assert await _count(connector_id) > 0


async def test_somebody_without_standing_is_told_nothing(
    client: AsyncClient, person: dict[str, str], colleague: tuple[str, dict[str, str]]
) -> None:
    connector_id = await _kept_postgres(client, person)
    _, theirs = colleague

    state = await client.get(f"{KEPT}/{connector_id}", headers=theirs)
    overview = await client.get(KEPT, headers=theirs)

    assert state.status_code == 404
    assert connector_id not in [one["connector_id"] for one in overview.json()["lists"]]


async def test_switching_it_off_deletes_the_names(
    client: AsyncClient, person: dict[str, str]
) -> None:
    connector_id = await _kept_postgres(client, person)

    off = await _keep(client, person, connector_id, keep=False)

    assert off.json()["status"] == "off"
    assert await _count(connector_id) == 0


async def test_refresh_needs_a_kept_list_and_makes_it_due(
    client: AsyncClient, person: dict[str, str]
) -> None:
    connector_id = await _connector(client, person, "postgres", working_postgres_options())

    before = await client.post(f"{KEPT}/{connector_id}/refresh", headers=person)
    await _keep(client, person, connector_id)
    await _pass(connector_id)
    asked = await client.post(f"{KEPT}/{connector_id}/refresh", headers=person)

    assert before.status_code == 409
    assert asked.json()["refresh_asked"] is True
    assert keeper.due(await _row(connector_id), get_datetime_utc())


# --- passes ---------------------------------------------------------------------


class _ScriptOptions(BaseModel):
    url: str


class _Script:
    """A source whose names are whatever the test says, pass by pass."""

    batches: ClassVar[list[NameBatch]] = []
    fails: ClassVar[AdapterError | None] = None

    def __init__(self, options: _ScriptOptions, context: registry.AdapterContext) -> None:
        self.options = options

    async def check_connection(self) -> ConnectionCheckResult:
        return ConnectionCheckResult(ok=True, message="ok", latency_ms=1)

    async def enumerate_names(
        self, limit: int, bounds: SearchBounds
    ) -> AsyncIterator[NameBatch]:
        if _Script.fails is not None:
            raise _Script.fails
        for batch in _Script.batches:
            yield batch


class _Plain:
    """A source that can be reached and cannot say its names."""

    def __init__(self, options: _ScriptOptions, context: registry.AdapterContext) -> None:
        self.options = options

    async def check_connection(self) -> ConnectionCheckResult:
        return ConnectionCheckResult(ok=True, message="ok", latency_ms=1)


def _named(node_id: str, scope: str) -> KeptName:
    return KeptName(
        node=FileNode(id=node_id, name=node_id.rsplit("/", 1)[-1], size_bytes=1, representations=[]),
        parent_id=scope or None,
        location=scope,
        scope=scope,
    )


@pytest.fixture
async def scripted(
    isolated_registry: None, client: AsyncClient, person: dict[str, str]
) -> AsyncGenerator[str]:
    registry.register(
        name="script",
        title="Script",
        category="sql",
        description="Names as the test says.",
        options_schema=_ScriptOptions,
        adapter_class=_Script,
    )(_Script)
    connector_id = await _connector(client, person, "script", {"url": "https://example.com"})
    assert (await _keep(client, person, connector_id)).status_code == 200
    yield connector_id
    _Script.batches = []
    _Script.fails = None


async def _node_ids(connector_id: str) -> set[str]:
    async with async_session_maker() as session:
        rows = await session.exec(
            select(SearchName.node_id).where(
                col(SearchName.connector_id) == uuid.UUID(connector_id)
            )
        )
        return set(rows.all())


async def test_a_finished_pass_deletes_what_it_did_not_see_except_where_it_could_not_read(
    scripted: str,
) -> None:
    _Script.batches = [
        NameBatch(names=[_named("a/one", "a"), _named("a/two", "a"), _named("b/c/three", "b/c")])
    ]
    await _pass(scripted)
    _Script.batches = [NameBatch(names=[_named("a/one", "a")], unread=["b"])]
    await _pass(scripted)

    assert await _node_ids(scripted) == {"a/one", "b/c/three"}
    row = await _row(scripted)
    assert row.outcome == "partial"
    assert row.kept_notice is not None and "could not be read" in row.kept_notice


async def test_a_pass_stopped_short_deletes_nothing(scripted: str) -> None:
    _Script.batches = [NameBatch(names=[_named("a/one", "a"), _named("a/two", "a")])]
    await _pass(scripted)
    _Script.batches = [NameBatch(names=[_named("a/one", "a")], notice="Time ran out")]
    await _pass(scripted)

    assert await _node_ids(scripted) == {"a/one", "a/two"}
    row = await _row(scripted)
    assert row.outcome == "partial"
    assert row.kept_notice == "Time ran out"


async def test_a_failed_pass_keeps_the_old_list_and_says_why(scripted: str) -> None:
    _Script.batches = [NameBatch(names=[_named("a/one", "a")])]
    await _pass(scripted)
    kept_at = (await _row(scripted)).kept_at
    _Script.fails = AdapterError("network", "The server did not answer")
    await _pass(scripted)

    row = await _row(scripted)
    assert await _node_ids(scripted) == {"a/one"}
    assert row.outcome == "failed"
    assert row.notice == "The server did not answer"
    assert row.kept_at == kept_at
    # Tried again after a while, not on every tick.
    assert not keeper.due(row, get_datetime_utc())


async def test_a_type_that_cannot_keep_its_names_is_refused(
    isolated_registry: None, client: AsyncClient, person: dict[str, str]
) -> None:
    registry.register(
        name="ping",
        title="Ping",
        category="sql",
        description="A source that can only be reached.",
        options_schema=_ScriptOptions,
        adapter_class=_Plain,
    )(_Plain)
    connector_id = await _connector(client, person, "ping", {"url": "https://example.com"})

    refused = await _keep(client, person, connector_id)
    state = await client.get(f"{KEPT}/{connector_id}", headers=person)

    assert refused.status_code == 501
    assert state.json()["available"] is False


# --- each source's names --------------------------------------------------------


async def _home(client: AsyncClient, headers: dict[str, str]) -> Path:
    me = await client.get(f"{settings.API_V1_STR}/users/me", headers=headers)
    home = settings.USER_STORAGE_ROOT / me.json()["id"]
    home.mkdir(parents=True, exist_ok=True)
    return home


async def test_files_and_folders_are_kept_with_the_folder_they_sit_in(
    client: AsyncClient, person: dict[str, str]
) -> None:
    home = await _home(client, person)
    (home / "reports" / "2024").mkdir(parents=True)
    (home / "reports" / "2024" / "orders_2024.csv").write_text("id\n1\n", encoding="utf-8")
    connector_id = await _connector(client, person, "file", {"path": "/"})
    await _keep(client, person, connector_id)
    await _pass(connector_id)

    cell = _names_cell(await _search(client, person, "orders 2024"), connector_id)
    (home / "reports" / "2024" / "orders_2024.csv").unlink()
    await _pass(connector_id)

    assert cell["way"] == "kept"
    [hit] = cell["hits"]
    assert hit["target"]["parent_id"] == "reports/2024"
    assert hit["target"]["node"]["kind"] == "file"
    assert await _node_ids(connector_id) == {"reports", "reports/2024"}


async def test_an_action_that_creates_a_file_marks_the_list_stale(
    client: AsyncClient, person: dict[str, str]
) -> None:
    await _home(client, person)
    connector_id = await _connector(client, person, "file", {"path": "/"})
    await _keep(client, person, connector_id)
    await _pass(connector_id)
    before = (await client.get(f"{KEPT}/{connector_id}", headers=person)).json()

    created = await client.post(
        f"{CONNECTORS}/{connector_id}/actions/create_file",
        headers=person,
        json={"node_id": None, "params": {"name": "fresh.txt"}},
    )
    after = (await client.get(f"{KEPT}/{connector_id}", headers=person)).json()

    assert created.status_code == 200, created.text
    assert before["stale"] is False
    assert after["stale"] is True


@pytest.fixture
async def keyspace() -> AsyncGenerator[None]:
    async for _ in empty_keyspace():
        yield


@pytest.mark.usefixtures("keyspace")
async def test_redis_keys_are_kept_with_their_ancestors(
    client: AsyncClient, person: dict[str, str]
) -> None:
    import redis.asyncio as redis

    options = redis_options()
    keys = redis.Redis(host=options.host, port=options.port, db=options.database)
    try:
        await keys.set("orders:2024:total", "1")
        await keys.set("orders:2023:total", "1")
    finally:
        await keys.aclose()
    connector_id = await _connector(client, person, "redis", options.model_dump(mode="json"))
    await _keep(client, person, connector_id)
    await _pass(connector_id)

    cell = _names_cell(await _search(client, person, "2024 total"), connector_id)

    assert cell["way"] == "kept"
    [hit] = cell["hits"]
    assert hit["target"]["node_kind"] == "key"
    assert hit["title"] == "total"
    assert [one["name"] for one in hit["target"]["ancestors"]][-2:] == ["orders:", "2024:"]
