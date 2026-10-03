"""What is inside connections, found through `POST /search` (S4, S8).

Every test speaks as a person of its own: the shared test user collects
connections from the whole suite, most of them pointing nowhere, and a search
asks every one of them.
"""

import asyncio
import io
import json
import threading
import time
import uuid
from collections.abc import AsyncGenerator, AsyncIterator, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, ClassVar
from urllib.parse import urlsplit

import psycopg
import pytest
from anyio import to_thread
from httpx import AsyncClient
from psycopg import sql
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters import registry
from app.adapters.postgres import search as postgres_search
from app.adapters.postgres.options import PostgresUserPassword
from app.adapters.postgres.pool import PooledConnections, key_for
from app.adapters.postgres.session import PostgresSession
from app.adapters.protocol import AdapterError, ConnectionCheckResult
from app.adapters.resources import Pooling, ResourceStore
from app.adapters.search import (
    LastSearch,
    NodeSearchRequest,
    NodeSearchResult,
    SearchBounds,
    SearchedField,
    SourceCost,
)
from app.adapters.ssh.adapter import SshAdapter
from app.adapters.ssh.options import SshPassword
from app.core.config import settings
from app.main import app
from app.search.engine import SearchEngine
from app.users import crud
from tests.utils import services
from tests.utils.database import working_postgres_options
from tests.utils.keyspace import empty_keyspace, redis_options
from tests.utils.socket import authenticated_socket
from tests.utils.ssh import pinned_key
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import random_email

SEARCH = f"{settings.API_V1_STR}/search"
CONNECTORS = f"{settings.API_V1_STR}/connectors"


def _engine() -> SearchEngine:
    engine: SearchEngine = app.state.search_engine
    return engine


@pytest.fixture
async def person(client: AsyncClient, db: AsyncSession) -> dict[str, str]:
    return await authentication_token_from_email(client=client, email=random_email(), db=db)


async def _connector(
    client: AsyncClient,
    headers: dict[str, str],
    adapter_type: str,
    options: dict[str, Any],
    name: str | None = None,
) -> str:
    response = await client.post(
        f"{CONNECTORS}/",
        headers=headers,
        json={
            "name": name or f"{adapter_type} {uuid.uuid4().hex[:8]}",
            "adapter_type": adapter_type,
            "options": options,
        },
    )
    assert response.status_code == 200, response.text
    return str(response.json()["id"])


async def _postgres(
    client: AsyncClient, headers: dict[str, str], name: str | None = None, **changed: Any
) -> str:
    return await _connector(
        client, headers, "postgres", {**working_postgres_options(), **changed}, name
    )


async def _search(
    client: AsyncClient, headers: dict[str, str], words: str, mode: str = "search", **extra: Any
) -> list[dict[str, Any]]:
    response = await client.post(
        SEARCH, headers=headers, json={"words": words, "mode": mode, **extra}
    )
    assert response.status_code == 200, response.text
    return [json.loads(line) for line in response.text.splitlines() if line]


def _cells(lines: list[dict[str, Any]], connector_id: str) -> dict[str, dict[str, Any]]:
    """The cells of one connection by field: as planned, and as finished."""
    [plan] = [line for line in lines if line["type"] == "plan"]
    planned = {
        cell["key"]: cell for cell in plan["cells"] if cell["connector_id"] == connector_id
    }
    finished = {line["key"]: line for line in lines if line["type"] == "cell"}
    return {
        cell["cell"]["field"]: {**cell, **finished.get(key, {})}
        for key, cell in planned.items()
    }


async def _asked(
    client: AsyncClient,
    headers: dict[str, str],
    words: str,
    connector_id: str,
    mode: str = "search",
) -> dict[str, dict[str, Any]]:
    """One connection's cells, with that connection in context."""
    lines = await _search(client, headers, words, mode, context=[connector_id])
    return _cells(lines, connector_id)


def _names(cell: dict[str, Any]) -> list[str]:
    return [hit["target"]["name"] for hit in cell.get("hits", [])]


@pytest.fixture
def patient() -> Iterator[None]:
    """Deadlines long enough that only a newer answer ends the older."""
    engine = _engine()
    kept = engine.limits
    engine.limits = replace(kept, cheap_seconds=10, costly_seconds=10, total_seconds=20)
    try:
        yield
    finally:
        engine.limits = kept


@pytest.fixture
def quick() -> Iterator[None]:
    engine = _engine()
    kept = engine.limits
    engine.limits = replace(kept, cheap_seconds=0.3, costly_seconds=0.5, total_seconds=1.0)
    try:
        yield
    finally:
        engine.limits = kept


# --- names in a database, live ------------------------------------------------


async def test_class_typed_with_a_postgresql_connection_open_finds_pg_class(
    client: AsyncClient, person: dict[str, str]
) -> None:
    """Against the system catalog, which always holds hundreds of relations."""
    connector_id = await _postgres(client, person)

    lines = await _search(client, person, "class", "typing", context=[connector_id])

    names = _cells(lines, connector_id)["names"]
    assert names["outcome"]["status"] in ("complete", "stopped")
    [pg_class] = [hit for hit in names["hits"] if hit["target"]["node_id"] == "pg_catalog.pg_class"]
    assert pg_class["target"]["node_kind"] == "table"
    assert pg_class["target"]["node"]["id"] == "pg_catalog.pg_class"
    assert pg_class["match"] == {
        "field": "name",
        "match_class": "word",
        "line": None,
        "excerpt": [{"text": "pg_", "hit": False}, {"text": "class", "hit": True}],
    }
    assert pg_class["detail"].endswith("pg_catalog")
    assert pg_class["access"] == "own"
    assert pg_class["open"] == "preferred"
    assert names["group"]["title"].startswith("postgres ")


async def test_a_percent_sign_finds_nothing_rather_than_everything(
    client: AsyncClient, person: dict[str, str]
) -> None:
    connector_id = await _postgres(client, person)

    lines = await _search(client, person, "100%", context=[connector_id])

    names = _cells(lines, connector_id)["names"]
    assert names["outcome"]["status"] == "complete"
    assert names["hits"] == []


async def test_a_columns_cell_is_asked_on_enter_and_not_while_typing(
    client: AsyncClient, person: dict[str, str]
) -> None:
    """Every column of every relation is a costly read (D200)."""
    connector_id = await _postgres(client, person)

    typing = await _asked(client, person, "relname", connector_id, "typing")
    entered = await _asked(client, person, "relname", connector_id)

    assert typing["columns"]["outcome"]["reason"] == "too_costly"
    assert typing["names"]["outcome"]["status"] in ("complete", "stopped")
    assert entered["columns"]["cost"] == "costly"
    assert "pg_class" in _names(entered["columns"])


# --- names in a tree of files ----------------------------------------------


async def _home(client: AsyncClient, headers: dict[str, str]) -> Path:
    me = await client.get(f"{settings.API_V1_STR}/users/me", headers=headers)
    home = settings.USER_STORAGE_ROOT / me.json()["id"]
    home.mkdir(parents=True, exist_ok=True)
    return home


async def test_two_words_find_a_file_in_the_field_and_in_the_catalog_alike(
    client: AsyncClient, person: dict[str, str]
) -> None:
    """`2024 orders` finds `orders_2024.csv`: every word, in any order (D202)."""
    home = await _home(client, person)
    (home / "reports").mkdir()
    (home / "reports" / "orders_2024.csv").write_text("id\n1\n", encoding="utf-8")
    (home / "reports" / "orders_2023.csv").write_text("id\n1\n", encoding="utf-8")
    connector_id = await _connector(client, person, "file", {"path": "/"})

    lines = await _search(client, person, "2024 orders", "typing", context=[connector_id])
    catalog = await client.get(
        f"{CONNECTORS}/{connector_id}/catalog/search",
        params={"query": "2024 orders"},
        headers=person,
    )

    names = _cells(lines, connector_id)["names"]
    assert names["cost"] == "cheap"
    assert _names(names) == ["orders_2024.csv"]
    assert names["hits"][0]["target"]["parent_id"] == "reports"
    assert names["hits"][0]["open"] == "preferred"
    assert names["hits"][0]["facts"]["changed_at"] is not None
    assert catalog.status_code == 200, catalog.text
    assert [match["node"]["name"] for match in catalog.json()["matches"]] == ["orders_2024.csv"]


async def test_a_connection_out_of_context_is_asked_on_enter_only(
    client: AsyncClient, person: dict[str, str]
) -> None:
    await _home(client, person)
    connector_id = await _connector(client, person, "file", {"path": "/"})

    typing = _cells(await _search(client, person, "anything", "typing"), connector_id)
    entered = _cells(await _search(client, person, "anything"), connector_id)

    assert typing["names"]["outcome"]["reason"] == "not_in_context"
    assert entered["names"]["outcome"]["status"] == "complete"


# --- what is not asked, and why -----------------------------------------------


async def test_a_switched_off_connection_is_never_asked(
    client: AsyncClient, person: dict[str, str]
) -> None:
    connector_id = await _postgres(client, person)
    await client.patch(f"{CONNECTORS}/{connector_id}", headers=person, json={"enabled": False})

    lines = await _search(client, person, "class", context=[connector_id])

    names = _cells(lines, connector_id)["names"]
    assert names["outcome"]["reason"] == "switched_off"
    assert names["way"] == "none"


class _PingOptions(BaseModel):
    url: str


class _Ping:
    """A source that can be reached and nothing else."""

    def __init__(self, options: _PingOptions, context: registry.AdapterContext) -> None:
        self.options = options

    async def check_connection(self) -> ConnectionCheckResult:
        return ConnectionCheckResult(ok=True, message="pong", latency_ms=1)


@pytest.mark.usefixtures("isolated_registry")
async def test_a_source_that_cannot_search_says_so(
    client: AsyncClient, person: dict[str, str]
) -> None:
    """Nothing in the engine is written per type: the capability decides (D197)."""
    registry.register(
        name="ping",
        title="Ping",
        category="sql",
        description="A source that can only be reached.",
        options_schema=_PingOptions,
        adapter_class=_Ping,
    )(_Ping)
    connector_id = await _connector(client, person, "ping", {"url": "https://example.com"})

    names = _cells(await _search(client, person, "anything"), connector_id)["names"]

    assert names["outcome"]["reason"] == "cannot_search"


async def test_connections_are_asked_in_context_then_recent_then_by_name(
    client: AsyncClient, person: dict[str, str]
) -> None:
    """And no more of them than the ceiling: the rest are not asked (D200)."""
    first = await _connector(client, person, "file", {"path": "/"}, "alpha")
    second = await _connector(client, person, "file", {"path": "/"}, "bravo")
    third = await _connector(client, person, "file", {"path": "/"}, "charlie")
    await _home(client, person)
    engine = _engine()
    kept = engine.limits
    engine.limits = replace(kept, max_connections=2)
    try:
        lines = await _search(
            client,
            person,
            "anything",
            context=[third],
            recent=[{"kind": "node", "connector_id": second, "node_id": "x"}],
        )
        # Insisting is for places a person named; without them it changes nothing.
        insisted = await _search(client, person, "anything", context=[third], insist=True)
    finally:
        engine.limits = kept

    cells = {one: _cells(lines, one)["names"] for one in (first, second, third)}
    assert cells[third]["group"]["rank"] < cells[second]["group"]["rank"]
    assert cells[second]["group"]["rank"] < cells[first]["group"]["rank"]
    assert cells[third]["outcome"]["status"] == "complete"
    assert cells[second]["outcome"]["status"] == "complete"
    assert cells[first]["outcome"]["reason"] == "not_asked"
    assert _cells(insisted, second)["names"]["outcome"]["reason"] == "not_asked"


class _SleepyOptions(BaseModel):
    seconds: float


class _Sleepy:
    """A source whose search takes as long as its options say, counting company."""

    running: ClassVar[int] = 0
    most: ClassVar[int] = 0

    def __init__(self, options: _SleepyOptions, context: registry.AdapterContext) -> None:
        self.options = options

    async def check_connection(self) -> ConnectionCheckResult:
        return ConnectionCheckResult(ok=True, message="ok", latency_ms=1)

    async def search_nodes(
        self, request: NodeSearchRequest, bounds: SearchBounds | None = None
    ) -> NodeSearchResult:
        _Sleepy.running += 1
        _Sleepy.most = max(_Sleepy.most, _Sleepy.running)
        try:
            await asyncio.sleep(self.options.seconds)
        finally:
            _Sleepy.running -= 1
        return NodeSearchResult()


def _sleepy() -> None:
    _Sleepy.running = _Sleepy.most = 0
    registry.register(
        name="sleepy",
        title="Sleepy",
        category="files",
        description="A source that takes its time.",
        options_schema=_SleepyOptions,
        adapter_class=_Sleepy,
    )(_Sleepy)


@pytest.mark.usefixtures("isolated_registry")
async def test_a_costly_cell_waiting_for_its_turn_keeps_its_own_seconds(
    client: AsyncClient, person: dict[str, str]
) -> None:
    """No more connections at once than the ceiling, and a costly cell's clock
    starts when it is asked, not when the answer began (D200)."""
    _sleepy()
    asked = [await _connector(client, person, "sleepy", {"seconds": 0.4}) for _ in range(3)]
    engine = _engine()
    kept = engine.limits
    # The third waits 0.4 s for a turn and then needs 0.4 s of its 0.6.
    engine.limits = replace(kept, parallel_connections=2, costly_seconds=0.6, total_seconds=5)
    try:
        lines = await _search(client, person, "anything")
    finally:
        engine.limits = kept

    outcomes = [_cells(lines, one)["names"] for one in asked]
    assert {one["cost"] for one in outcomes} == {"costly"}
    assert [one["outcome"]["status"] for one in outcomes] == ["complete"] * 3
    assert _Sleepy.most == 2


@pytest.mark.usefixtures("isolated_registry", "patient")
async def test_a_person_searches_one_connection_one_search_at_a_time(
    client: AsyncClient, person: dict[str, str]
) -> None:
    """However many lanes ask it, so a person holds one of its pooled
    connections at most (D200)."""
    _sleepy()
    connector_id = await _connector(client, person, "sleepy", {"seconds": 0.3})

    answers = await asyncio.gather(
        _search(client, person, "anything"),
        _search(client, person, "something else", lane="tab"),
    )

    statuses = [_cells(lines, connector_id)["names"]["outcome"]["status"] for lines in answers]
    assert statuses == ["complete", "complete"]
    assert _Sleepy.most == 1


@pytest.fixture
def _health_soon(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "HEALTH_INTERVAL_SECONDS", 0.3)
    monkeypatch.setattr(settings, "HEALTH_GRACE_SECONDS", 0.0)


async def _health_of(ws: Any, *connector_ids: str) -> dict[str, dict[str, Any]]:
    """The first report about each of these connections, by id."""
    seen: dict[str, dict[str, Any]] = {}
    while len(seen) < len(connector_ids):
        frame: dict[str, Any] = await ws.receive_json(timeout=10)
        if frame["payload"]["connector_id"] in connector_ids:
            seen.setdefault(frame["payload"]["connector_id"], frame["payload"])
    return seen


@pytest.mark.usefixtures("_health_soon", "quick")
async def test_a_connection_its_monitor_could_not_reach_is_skipped_unless_insisted_on(
    client: AsyncClient, person: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The person's health monitor (D19) could not reach it; "Search anyway" asks."""
    monkeypatch.setattr(settings, "HEALTH_PROBE_TIMEOUT_SECONDS", 0.5)
    async with _silent_server() as silent:
        connector_id = await _postgres(client, person, host="127.0.0.1", port=silent.port)

        async with authenticated_socket(person) as ws:
            await ws.send_json({"type": "subscribe", "topic": "connector.health"})
            health = await _health_of(ws, connector_id)
            skipped = _cells(await _search(client, person, "class"), connector_id)
            insisted = _cells(
                await _search(
                    client,
                    person,
                    "class",
                    only=[{"kind": "connection", "connector_id": connector_id}],
                    insist=True,
                ),
                connector_id,
            )

    assert health[connector_id]["result"]["error_kind"] == "timeout"
    assert skipped["names"]["outcome"]["reason"] == "unreachable"
    assert skipped["names"]["outcome"]["since"] is not None
    assert skipped["columns"]["outcome"]["reason"] == "unreachable"
    assert insisted["names"]["outcome"]["status"] == "late"


class _LockedOptions(BaseModel):
    key: str


class _Locked:
    """A source that signs in with a key whose passphrase nobody has given (D147)."""

    def __init__(self, options: _LockedOptions, context: registry.AdapterContext) -> None:
        self.options = options

    def _sentence(self) -> str:
        return f"The SSH key {self.options.key} is locked; enter its passphrase to use it"

    async def check_connection(self) -> ConnectionCheckResult:
        return ConnectionCheckResult(ok=False, message=self._sentence(), error_kind="locked")

    async def search_nodes(
        self, request: NodeSearchRequest, bounds: SearchBounds | None = None
    ) -> NodeSearchResult:
        raise AdapterError("locked", self._sentence())


def _locked() -> None:
    registry.register(
        name="locked",
        title="Locked",
        category="files",
        description="A source whose key is locked.",
        options_schema=_LockedOptions,
        adapter_class=_Locked,
    )(_Locked)


@pytest.mark.usefixtures("isolated_registry", "_health_soon")
async def test_a_refused_password_or_a_locked_key_is_asked_though_its_monitor_saw_it_fail(
    client: AsyncClient, person: dict[str, str]
) -> None:
    """Their servers answered, so they are not unreachable: the search asks and
    says what failed, and the owner is offered the way on (D201)."""
    _locked()
    refused = await _postgres(client, person, password="wrong-on-purpose")
    locked = await _connector(client, person, "locked", {"key": "deploy-key"})

    async with authenticated_socket(person) as ws:
        await ws.send_json({"type": "subscribe", "topic": "connector.health"})
        health = await _health_of(ws, refused, locked)
        lines = await _search(client, person, "class")

    assert health[refused]["result"]["error_kind"] == "auth"
    assert health[locked]["result"]["error_kind"] == "locked"
    outcomes = {one: _cells(lines, one)["names"]["outcome"] for one in (refused, locked)}
    assert outcomes[refused]["status"] == "failed"
    assert outcomes[refused]["error_kind"] == "auth"
    assert outcomes[refused]["owned"] is True
    assert outcomes[locked]["status"] == "failed"
    assert outcomes[locked]["error_kind"] == "locked"
    assert outcomes[locked]["owned"] is True
    assert "deploy-key" in outcomes[locked]["message"]
    assert "wrong-on-purpose" not in json.dumps(lines)


@pytest.mark.usefixtures("isolated_registry")
async def test_a_grantee_searches_under_the_owner_s_credentials(
    client: AsyncClient, db: AsyncSession, superuser_token_headers: dict[str, str]
) -> None:
    """In the owner's storage, naming the owner, and never the owner's key (D199)."""
    _locked()
    owner_email, grantee_email = random_email(), random_email()
    owner = await authentication_token_from_email(client=client, email=owner_email, db=db)
    grantee = await authentication_token_from_email(client=client, email=grantee_email, db=db)
    stranger = await authentication_token_from_email(client=client, email=random_email(), db=db)
    marker = uuid.uuid4().hex[:8]
    (await _home(client, owner) / f"ledger_{marker}.csv").write_text("id\n1\n", encoding="utf-8")
    files = await _connector(client, owner, "file", {"path": "/"})
    key = f"deploy-{marker}"
    locked = await _connector(client, owner, "locked", {"key": key})
    granted = await crud.get_user_by_email(session=db, email=grantee_email)
    assert granted is not None
    for connector_id in (files, locked):
        response = await client.put(
            f"{CONNECTORS}/{connector_id}/grants",
            headers=owner,
            json={"user_id": str(granted.id), "access": "read"},
        )
        assert response.status_code == 200, response.text
    words = f"ledger {marker}"

    theirs = await _search(client, grantee, words, context=[files, locked])
    mine = await _search(client, owner, words, context=[files, locked])

    [hit] = _cells(theirs, files)["names"]["hits"]
    assert hit["target"]["name"] == f"ledger_{marker}.csv"
    assert hit["facts"]["owner"] == owner_email
    assert hit["access"] == "read"
    failed = _cells(theirs, locked)["names"]["outcome"]
    assert (failed["error_kind"], failed["owned"]) == ("locked", False)
    assert failed["message"] == "Locked by its owner"
    assert key not in json.dumps(theirs)
    [own] = _cells(mine, files)["names"]["hits"]
    assert (own["facts"]["owner"], own["access"]) == (None, "own")
    assert _cells(mine, locked)["names"]["outcome"]["owned"] is True
    assert key in _cells(mine, locked)["names"]["outcome"]["message"]
    for nobody in (stranger, superuser_token_headers):
        lines = await _search(client, nobody, words, "typing", context=[files, locked])
        assert _cells(lines, files) == {}
        assert _cells(lines, locked) == {}


# --- a server that does not answer ---------------------------------------------


@dataclass
class _Silent:
    port: int = 0
    connections: int = 0
    held: list[asyncio.StreamWriter] = field(default_factory=list)


@asynccontextmanager
async def _silent_server() -> AsyncIterator[_Silent]:
    """A port that accepts and says nothing, counting who came."""
    silent = _Silent()

    async def hold(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        silent.connections += 1
        silent.held.append(writer)
        await reader.read()

    server = await asyncio.start_server(hold, "127.0.0.1", 0)
    silent.port = server.sockets[0].getsockname()[1]
    try:
        yield silent
    finally:
        server.close()
        for writer in silent.held:
            writer.close()
        await server.wait_closed()


@pytest.mark.usefixtures("quick")
async def test_a_server_that_does_not_answer_is_late_and_then_left_alone(
    client: AsyncClient, person: dict[str, str]
) -> None:
    """The other groups are drawn, and neither its next cell nor Enter pressed
    again asks it (D200)."""
    async with _silent_server() as silent:
        marker = uuid.uuid4().hex[:8]
        connector_id = await _postgres(
            client, person, f"silent {marker}", host="127.0.0.1", port=silent.port
        )

        first = await _search(client, person, f"silent {marker}")
        asked = silent.connections
        again = [await _search(client, person, f"silent {marker}") for _ in range(3)]

    late = _cells(first, connector_id)["names"]
    assert late["outcome"]["status"] == "late"
    assert late["outcome"]["deadline_seconds"] == 0.3
    columns = _cells(first, connector_id)["columns"]
    assert columns["outcome"]["status"] == "skipped"
    assert columns["outcome"]["reason"] == "unreachable"
    rows = [line for line in first if line["type"] == "cell" and line["key"] == "connections/names"]
    assert [hit["target"]["connector_id"] for hit in rows[0]["hits"]] == [connector_id]
    assert first[-1]["type"] == "end"
    assert asked == 1
    for lines in again:
        skipped = _cells(lines, connector_id)["names"]
        assert skipped["outcome"]["reason"] == "unreachable"
        assert skipped["outcome"]["since"] is not None
    assert silent.connections == asked


# --- a newer keystroke ends the older work -------------------------------------


def _conninfo() -> str:
    options = working_postgres_options()
    return psycopg.conninfo.make_conninfo(
        host=options["host"],
        port=options["port"],
        dbname=options["database"],
        user=options["user"],
        password=options["password"],
    )


@pytest.fixture
def slow_names(monkeypatch: pytest.MonkeyPatch) -> str:
    """A name search the server runs until it is cancelled, marked to be found
    among the server's running queries.

    The mark comes first: the server keeps only the start of a long query.
    """
    marker = f"search_slow_{uuid.uuid4().hex[:8]}"
    names = postgres_search._names_statement

    def slow(count: int) -> sql.Composed:
        return sql.SQL("SELECT found.* FROM (SELECT {}) AS m, pg_sleep(30), ({}) AS found").format(
            sql.Literal(marker), names(count)
        )

    monkeypatch.setattr(postgres_search, "_names_statement", slow)
    return marker


async def _running(marker: str) -> int:
    async with await psycopg.AsyncConnection.connect(_conninfo(), autocommit=True) as watch:
        cursor = await watch.execute(
            "SELECT count(*) FROM pg_stat_activity "
            "WHERE state = 'active' AND strpos(query, %s) > 0 AND pid <> pg_backend_pid()",
            (marker,),
        )
        row = await cursor.fetchone()
        assert row is not None
        return int(row[0])


@pytest.mark.usefixtures("patient")
async def test_a_newer_keystroke_cancels_the_older_postgresql_query(
    client: AsyncClient, person: dict[str, str], slow_names: str
) -> None:
    connector_id = await _postgres(client, person)
    older = asyncio.create_task(
        client.post(
            SEARCH,
            headers=person,
            json={"words": "class", "mode": "search", "context": [connector_id]},
        )
    )
    for _ in range(100):
        if await _running(slow_names):
            break
        await asyncio.sleep(0.05)
    else:
        pytest.fail("The search never reached the server")

    newer = await _search(client, person, "something else", "typing")
    ended = await asyncio.wait_for(older, 10)

    assert newer[-1]["type"] == "end"
    assert json.loads(ended.text.splitlines()[-1])["superseded"] is True
    for _ in range(100):
        if not await _running(slow_names):
            return
        await asyncio.sleep(0.05)
    pytest.fail("The server still runs a query whose answer nobody waits for")


# --- the same cell asked twice -------------------------------------------------


@pytest.mark.usefixtures("isolated_registry")
async def test_the_same_words_entered_again_are_answered_on_time(
    client: AsyncClient, person: dict[str, str]
) -> None:
    """The newer answer does not join the older one's task while it is being
    stopped, which would end the newer with it."""
    _sleepy()
    connector_id = await _connector(client, person, "sleepy", {"seconds": 0.5})
    engine = _engine()
    kept = engine.limits
    engine.limits = replace(kept, cheap_seconds=3, costly_seconds=3, total_seconds=4)
    try:
        older = asyncio.create_task(_search(client, person, "anything"))
        for _ in range(200):
            if _Sleepy.running:
                break
            await asyncio.sleep(0.01)
        started = time.monotonic()
        newer = await _search(client, person, "anything")
        took = time.monotonic() - started
    finally:
        engine.limits = kept

    assert (await asyncio.wait_for(older, 10))[-1]["superseded"] is True
    assert _cells(newer, connector_id)["names"]["outcome"]["status"] == "complete"
    assert took < 3


class _Timed:
    """A cheap source that says when it was told to be done by, and takes a while."""

    given: ClassVar[list[float]] = []

    def __init__(self, options: _SleepyOptions, context: registry.AdapterContext) -> None:
        self.options = options

    async def check_connection(self) -> ConnectionCheckResult:
        return ConnectionCheckResult(ok=True, message="ok", latency_ms=1)

    @classmethod
    def search_cost(cls, field: SearchedField, last: LastSearch | None) -> SourceCost:
        return "cheap"

    async def search_nodes(
        self, request: NodeSearchRequest, bounds: SearchBounds | None = None
    ) -> NodeSearchResult:
        assert bounds is not None
        _Timed.given.append(bounds.deadline)
        await asyncio.sleep(self.options.seconds)
        return NodeSearchResult()


@pytest.mark.usefixtures("isolated_registry")
async def test_enter_is_not_given_the_seconds_of_a_keystroke_still_running(
    client: AsyncClient, person: dict[str, str]
) -> None:
    """A cell asked on Enter does not join a typing answer's task for the same
    words: that task's deadline and mode are the keystroke's (D200)."""
    _Timed.given = []
    registry.register(
        name="timed",
        title="Timed",
        category="files",
        description="A source that says how long it was given.",
        options_schema=_SleepyOptions,
        adapter_class=_Timed,
    )(_Timed)
    connector_id = await _connector(client, person, "timed", {"seconds": 0.6})
    scope = [{"kind": "connection", "connector_id": connector_id}]
    engine = _engine()
    kept = engine.limits
    engine.limits = replace(
        kept, typing_seconds=2, cheap_seconds=3, costly_seconds=3, total_seconds=4
    )
    try:
        typing = asyncio.create_task(_search(client, person, "anything", "typing", only=scope))
        for _ in range(200):
            if _Timed.given:
                break
            await asyncio.sleep(0.01)
        entered = await _search(client, person, "anything", only=scope, lane="tab")
        typed = await asyncio.wait_for(typing, 10)
    finally:
        engine.limits = kept

    assert _cells(typed, connector_id)["names"]["outcome"]["status"] == "complete"
    assert _cells(entered, connector_id)["names"]["outcome"]["status"] == "complete"
    assert len(_Timed.given) == 2
    assert _Timed.given[1] > _Timed.given[0]


class _SlowOptions(BaseModel):
    label: str


@dataclass
class _Walked:
    started: threading.Event = field(default_factory=threading.Event)
    ended: threading.Event = field(default_factory=threading.Event)
    how: str = ""


class _SlowTree:
    """A tree whose walk takes until it is told to stop, or until its deadline."""

    walked: ClassVar[_Walked] = _Walked()

    def __init__(self, options: _SlowOptions, context: registry.AdapterContext) -> None:
        self.options = options

    async def check_connection(self) -> ConnectionCheckResult:
        return ConnectionCheckResult(ok=True, message="ok", latency_ms=1)

    async def search_nodes(
        self, request: NodeSearchRequest, bounds: SearchBounds | None = None
    ) -> NodeSearchResult:
        assert bounds is not None
        walked = self.walked

        def walk() -> None:
            walked.started.set()
            while not bounds.stopped() and time.monotonic() < bounds.deadline:
                time.sleep(0.01)
            walked.how = "stopped" if bounds.stopped() else "deadline"
            walked.ended.set()

        await to_thread.run_sync(walk, limiter=bounds.limiter)
        return NodeSearchResult(complete=False, notice="Stopped")


@pytest.mark.usefixtures("isolated_registry", "patient")
async def test_a_newer_keystroke_stops_the_older_walk(
    client: AsyncClient, person: dict[str, str]
) -> None:
    _SlowTree.walked = _Walked()
    registry.register(
        name="slowtree",
        title="Slow tree",
        category="files",
        description="A tree that takes as long as it is let to.",
        options_schema=_SlowOptions,
        adapter_class=_SlowTree,
    )(_SlowTree)
    await _connector(client, person, "slowtree", {"label": "slow"})
    older = asyncio.create_task(_search(client, person, "anything"))
    assert await to_thread.run_sync(_SlowTree.walked.started.wait, 5)
    started = time.monotonic()

    await _search(client, person, "something else", "typing")

    assert await to_thread.run_sync(_SlowTree.walked.ended.wait, 5)
    assert _SlowTree.walked.how == "stopped"
    assert time.monotonic() - started < 5
    assert (await asyncio.wait_for(older, 10))[-1]["superseded"] is True


# --- other people's pools -----------------------------------------------------


async def test_a_search_over_25_connections_closes_no_pool_another_person_uses(
    client: AsyncClient, person: dict[str, str], db: AsyncSession
) -> None:
    """Nothing is made in the shared store, so nothing is pushed out of it (D200)."""
    other = await authentication_token_from_email(client=client, email=random_email(), db=db)
    theirs = await _postgres(client, other)
    opened = await client.get(f"{CONNECTORS}/{theirs}/catalog", headers=other)
    assert opened.status_code == 200, opened.text
    store: ResourceStore = app.state.resources
    conninfo = PostgresSession(PostgresUserPassword(**working_postgres_options())).conninfo()
    pool = await store.existing(key_for(uuid.UUID(theirs), conninfo), PooledConnections)
    assert pool is not None
    mine = [await _postgres(client, person) for _ in range(25)]

    lines = await _search(client, person, "class")

    asked = [one for one in mine if _cells(lines, one)["names"]["way"] == "live"]
    assert len(asked) == _engine().limits.max_connections
    assert await store.existing(key_for(uuid.UUID(theirs), conninfo), PooledConnections) is pool
    for one in mine:
        assert await store.existing(key_for(uuid.UUID(one), conninfo), PooledConnections) is None
    again = await client.get(f"{CONNECTORS}/{theirs}/catalog", headers=other)
    assert again.status_code == 200


# --- a tree over SSH -----------------------------------------------------------


class _Payload:
    def __init__(self, name: str, data: bytes) -> None:
        self.filename = name
        self._data = io.BytesIO(data)

    async def read(self, size: int) -> bytes:
        return self._data.read(size)


@pytest.fixture
async def ssh_folder() -> AsyncGenerator[dict[str, Any]]:
    """The options of a connection to a folder of this test's own on the
    development SSH server, holding one report."""
    parts = urlsplit(services.SSH.require())
    server: dict[str, Any] = {
        "auth_method": "password",
        "host": parts.hostname,
        "port": parts.port or 22,
        "username": parts.username,
        "password": parts.password,
    }
    server["host_key"] = await pinned_key(str(server["host"]), int(server["port"]))
    name = f"test-{uuid.uuid4().hex[:12]}"
    options = SshPassword.model_validate({**server, "path": name})
    store = ResourceStore(max_entries=4, max_idle_seconds=60)
    context = registry.AdapterContext(
        home_dir=Path("."), pooling=Pooling(store=store, connector_id=uuid.uuid4())
    )
    home = SshAdapter(options.model_copy(update={"path": ""}), context)
    await home.action("create_folder").perform(None, {"name": name})
    try:
        await SshAdapter(options, context).action("upload").perform_with_file(
            None, {"conflict": "refuse"}, _Payload("orders_2024.csv", b"id\n1\n")
        )
        yield {**server, "path": name}
    finally:
        await home.action("delete").perform(name, {})
        await store.aclose()


async def test_a_file_over_ssh_is_found_on_enter_through_a_link_of_its_own(
    client: AsyncClient, person: dict[str, str], ssh_folder: dict[str, Any]
) -> None:
    """A walk over SSH is a round trip per folder, so costly; the link it signs
    in with is closed with the search and never kept in the shared store (D200)."""
    connector_id = await _connector(client, person, "ssh", ssh_folder)
    store: ResourceStore = app.state.resources
    kept = await store.size()

    typing = await _asked(client, person, "2024 orders", connector_id, "typing")
    entered = await _asked(client, person, "2024 orders", connector_id)

    assert typing["names"]["outcome"]["reason"] == "too_costly"
    assert entered["names"]["cost"] == "costly"
    assert entered["names"]["outcome"]["status"] == "complete"
    assert _names(entered["names"]) == ["orders_2024.csv"]
    assert await store.size() == kept


# --- a key space ------------------------------------------------------------


@pytest.fixture
async def keyspace() -> AsyncGenerator[None]:
    async for _ in empty_keyspace():
        yield


async def _keys(*names: str) -> None:
    import redis.asyncio as redis

    options = redis_options()
    keys = redis.Redis(host=options.host, port=options.port, db=options.database)
    try:
        for name in names:
            await keys.set(name, "1")
    finally:
        await keys.aclose()


@pytest.mark.usefixtures("keyspace")
async def test_a_large_key_space_is_searched_on_enter_and_not_while_typing(
    client: AsyncClient, person: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Costly until a search has said how many keys there are, and above the
    threshold after (D200)."""
    options = redis_options()
    await _keys(*(f"orders:{index}:total" for index in range(10)))
    connector_id = await _connector(client, person, "redis", options.model_dump(mode="json"))
    monkeypatch.setattr(settings, "SEARCH_CHEAP_KEYS", 5)

    before = await _asked(client, person, "total", connector_id, "typing")
    entered = await _asked(client, person, "total", connector_id)
    after = await _asked(client, person, "total", connector_id, "typing")
    monkeypatch.setattr(settings, "SEARCH_CHEAP_KEYS", 1000)
    small = await _asked(client, person, "total", connector_id, "typing")

    assert before["names"]["outcome"]["reason"] == "too_costly"
    assert entered["names"]["outcome"]["status"] == "complete"
    assert len(entered["names"]["hits"]) == 10
    hit = entered["names"]["hits"][0]
    assert hit["target"]["node_kind"] == "key"
    # No node path: the folders it is shown in come with it (D205).
    assert [one["name"] for one in hit["target"]["ancestors"][:2]] == [
        f"db{options.database}",
        "orders:",
    ]
    assert after["names"]["outcome"]["reason"] == "too_costly"
    assert small["names"]["cost"] == "cheap"
    assert small["names"]["outcome"]["status"] in ("complete", "stopped")


# --- columns and comments (S8) ---------------------------------------------------


@pytest.fixture
async def described_schema() -> AsyncGenerator[str]:
    schema = f"search_described_{uuid.uuid4().hex[:8]}"
    statements = [
        "CREATE SCHEMA {schema}",
        "CREATE TABLE {schema}.buyers (id int, customer_email text)",
        "CREATE TABLE {schema}.sellers (id int, email text)",
        "CREATE TABLE {schema}.ledger (id int, amount numeric)",
        "COMMENT ON TABLE {schema}.ledger IS 'Every invoice the warehouse settled'",
    ]
    async with await psycopg.AsyncConnection.connect(_conninfo(), autocommit=True) as conn:
        for statement in statements:
            await conn.execute(sql.SQL(statement).format(schema=sql.Identifier(schema)))
    try:
        yield schema
    finally:
        async with await psycopg.AsyncConnection.connect(_conninfo(), autocommit=True) as conn:
            await conn.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema))
            )


async def test_email_finds_the_tables_with_such_a_column_and_says_which(
    client: AsyncClient, person: dict[str, str], described_schema: str
) -> None:
    connector_id = await _postgres(client, person)
    scope = [{"kind": "connection", "connector_id": connector_id, "node_id": described_schema}]

    lines = await _search(client, person, "email", only=scope)

    columns = _cells(lines, connector_id)["columns"]
    found = {
        hit["target"]["name"]: "".join(part["text"] for part in hit["match"]["excerpt"])
        for hit in columns["hits"]
    }
    assert found == {"sellers": "email", "buyers": "customer_email"}
    assert {hit["match"]["field"] for hit in columns["hits"]} == {"columns"}
    assert {hit["target"]["node_kind"] for hit in columns["hits"]} == {"table"}


async def test_a_table_comment_is_found_by_a_word_in_it(
    client: AsyncClient, person: dict[str, str], described_schema: str
) -> None:
    connector_id = await _postgres(client, person)
    scope = [{"kind": "connection", "connector_id": connector_id, "node_id": described_schema}]

    lines = await _search(client, person, "warehouse invoice", only=scope)

    [hit] = _cells(lines, connector_id)["columns"]["hits"]
    assert hit["target"]["node_id"] == f"{described_schema}.ledger"
    assert [part["text"] for part in hit["match"]["excerpt"] if part["hit"]] == [
        "invoice",
        "warehouse",
    ]
