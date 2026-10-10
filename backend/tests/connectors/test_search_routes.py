import asyncio
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

import pytest
from anyio import to_thread
from httpx import AsyncClient
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters import registry
from app.adapters.catalog import CatalogNode
from app.adapters.protocol import ConnectionCheckResult
from app.adapters.search import NodeSearchRequest, NodeSearchResult, SearchBounds
from app.core.config import settings
from app.main import app
from app.users import crud, storage
from tests.utils.database import working_postgres_options

BASE = f"{settings.API_V1_STR}/connectors"


@pytest.fixture
async def home(db: AsyncSession) -> Path:
    user = await crud.get_user_by_email(session=db, email=settings.EMAIL_TEST_USER)
    assert user is not None
    home = storage.create_home(user.id)
    (home / "searched").mkdir(exist_ok=True)
    (home / "searched" / "findme.txt").write_text("top\n", encoding="utf-8")
    (home / "searched" / "deeper").mkdir(exist_ok=True)
    (home / "searched" / "deeper" / "findme-too.txt").write_text("x\n", encoding="utf-8")
    (home / "searched" / "quiet.txt").write_text(
        "the word is inside, not in the name\n", encoding="utf-8"
    )
    return home


async def _file_connector(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        f"{BASE}/",
        headers=headers,
        json={
            "name": f"search files {uuid.uuid4()}",
            "adapter_type": "file",
            "options": {"path": "/"},
        },
    )
    assert response.status_code == 200
    return str(response.json()["id"])


@pytest.mark.usefixtures("home")
async def test_a_search_answers_with_nodes_and_where_they_are(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await client.get(
        f"{BASE}/{connector_id}/catalog/search",
        params={"node_id": "searched", "query": "findme"},
        headers=normal_user_token_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["complete"] is True
    names = [match["node"]["name"] for match in body["matches"]]
    assert names == ["findme.txt", "findme-too.txt"]
    deeper = body["matches"][1]
    assert deeper["parent_id"] == "searched/deeper"
    assert deeper["location"] == "searched/deeper"
    # The same node the listing gives, so a found row opens like any other.
    assert deeper["node"]["kind"] == "file"
    assert deeper["node"]["representations"][0]["kind"] == "text"


@pytest.mark.usefixtures("home")
async def test_a_ceiling_is_answered_as_an_incomplete_search(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await client.get(
        f"{BASE}/{connector_id}/catalog/search",
        params={"node_id": "searched", "query": "findme", "limit": 1},
        headers=normal_user_token_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["matches"]) == 1
    assert body["complete"] is False
    assert body["notice"]


@pytest.mark.usefixtures("home")
@pytest.mark.parametrize(
    ("params", "status"),
    [
        ({"query": ""}, 422),
        ({"query": "x" * 500}, 422),
        ({"query": "findme", "limit": 0}, 422),
        ({"query": "findme", "limit": 5000}, 422),
        ({"query": "findme", "node_id": "../../etc"}, 422),
        ({"query": "findme", "node_id": "searched/findme.txt"}, 422),
        ({"query": "findme", "node_id": "nowhere"}, 404),
    ],
)
async def test_what_a_search_refuses(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    params: dict[str, object],
    status: int,
) -> None:
    """Every bound is the route's or the source's, and none is the caller's."""
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await client.get(
        f"{BASE}/{connector_id}/catalog/search",
        params=params,
        headers=normal_user_token_headers,
    )

    assert response.status_code == status


@pytest.mark.usefixtures("home")
async def test_a_search_inside_files_finds_what_a_name_search_cannot(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)

    inside = await client.get(
        f"{BASE}/{connector_id}/catalog/search-contents",
        params={"node_id": "searched", "query": "inside"},
        headers=normal_user_token_headers,
    )
    by_name = await client.get(
        f"{BASE}/{connector_id}/catalog/search",
        params={"node_id": "searched", "query": "inside"},
        headers=normal_user_token_headers,
    )

    assert inside.status_code == 200
    body = inside.json()
    assert [match["node"]["name"] for match in body["matches"]] == ["quiet.txt"]
    # The line it was found on, which is what the row then shows instead of a
    # file size.
    assert body["matches"][0]["excerpt"] == "the word is inside, not in the name"
    assert by_name.json()["matches"] == []


@pytest.mark.usefixtures("home")
@pytest.mark.parametrize(
    ("params", "status"),
    [
        ({"query": ""}, 422),
        ({"query": "inside", "node_id": "../../etc"}, 422),
        ({"query": "inside", "node_id": "nowhere"}, 404),
    ],
)
async def test_reading_inside_refuses_what_the_name_search_refuses(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    params: dict[str, object],
    status: int,
) -> None:
    """One set of bounds, whichever of the two searches is asked for."""
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await client.get(
        f"{BASE}/{connector_id}/catalog/search-contents",
        params=params,
        headers=normal_user_token_headers,
    )

    assert response.status_code == status


async def _created(
    client: AsyncClient, headers: dict[str, str], adapter_type: str, options: dict[str, object]
) -> str:
    created = await client.post(
        f"{BASE}/",
        headers=headers,
        json={
            "name": f"search {adapter_type} {uuid.uuid4()}",
            "adapter_type": adapter_type,
            "options": options,
        },
    )
    assert created.status_code == 200, created.text
    return str(created.json()["id"])


async def test_a_database_is_searched_by_name_and_not_inside(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """PostgreSQL finds its relations by name (S4) and has no files to read."""
    connector_id = await _created(
        client, normal_user_token_headers, "postgres", working_postgres_options()
    )

    by_name = await client.get(
        f"{BASE}/{connector_id}/catalog/search",
        params={"query": "class", "node_id": "pg_catalog"},
        headers=normal_user_token_headers,
    )
    inside = await client.get(
        f"{BASE}/{connector_id}/catalog/search-contents",
        params={"query": "class"},
        headers=normal_user_token_headers,
    )

    assert by_name.status_code == 200, by_name.text
    assert "pg_class" in [match["node"]["name"] for match in by_name.json()["matches"]]
    assert inside.status_code == 501


async def test_a_tree_is_searched_by_name_and_never_inside(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """A key space searches its tree by name; it has no files to read (D91).

    Refused before anything is asked of the server, so none needs to answer.
    """
    connector_id = await _created(
        client,
        normal_user_token_headers,
        "redis",
        {"auth_method": "no_auth", "host": "localhost", "port": 6379, "database": 15},
    )

    response = await client.get(
        f"{BASE}/{connector_id}/catalog/search-contents",
        params={"query": "users"},
        headers=normal_user_token_headers,
    )

    assert response.status_code == 501


async def test_the_type_catalog_says_which_sources_can_be_searched(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """A code rather than a title: a screen switches on it (D76)."""
    response = await client.get(
        f"{settings.API_V1_STR}/adapter-types/", headers=normal_user_token_headers
    )

    assert response.status_code == 200
    codes = {
        adapter["name"]: {
            capability["code"] for capability in adapter["capabilities"]
        }
        for adapter in response.json()
    }
    assert "search" in codes["file"]
    assert "search" in codes["postgres"]
    # A tree with no node path still searches its own catalog: its matches
    # carry their ancestors (D91).
    assert codes["redis"] - {None} == {"metrics", "relation_model", "search"}
    # Two promises, so two codes: a source may match names without being able
    # to read what is in them.
    assert "content_search" in codes["file"]
    assert "content_search" not in codes["postgres"]


class _WalkOptions(BaseModel):
    label: str


@dataclass
class _Walk:
    started: threading.Event = field(default_factory=threading.Event)
    ended: threading.Event = field(default_factory=threading.Event)
    how: str = ""


class _Walking:
    """A tree whose walk takes until it is told to stop, or until its deadline."""

    walk: ClassVar[_Walk] = _Walk()

    def __init__(self, options: _WalkOptions, context: registry.AdapterContext) -> None:
        self.options = options

    async def check_connection(self) -> ConnectionCheckResult:
        return ConnectionCheckResult(ok=True, message="ok", latency_ms=1)

    async def list_children(self, node_id: str | None) -> list[CatalogNode]:
        return []

    async def path_to(self, node_id: str) -> list[CatalogNode]:
        return []

    async def search_nodes(
        self, request: NodeSearchRequest, bounds: SearchBounds | None = None
    ) -> NodeSearchResult:
        assert bounds is not None
        walk = self.walk

        def walking() -> None:
            walk.started.set()
            while not bounds.over():
                time.sleep(0.01)
            walk.how = "stopped" if bounds.stopped() else "deadline"
            walk.ended.set()

        await to_thread.run_sync(walking)
        return NodeSearchResult(complete=False, notice="Stopped")


@pytest.mark.usefixtures("isolated_registry")
async def test_a_walk_stops_when_its_caller_has_gone(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """A client going away does not cancel the route, so the walk is told (D200)."""
    _Walking.walk = _Walk()
    registry.register(
        name="walking",
        title="Walking",
        category="files",
        description="A tree that takes as long as it is let to.",
        options_schema=_WalkOptions,
        adapter_class=_Walking,
    )(_Walking)
    connector_id = await _created(
        client, normal_user_token_headers, "walking", {"label": "slow"}
    )
    path = f"{BASE}/{connector_id}/catalog/search"
    gone = asyncio.Event()
    asked = False

    async def receive() -> dict[str, Any]:
        nonlocal asked
        if not asked:
            asked = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await gone.wait()
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        pass

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "server": ("test", 80),
        "client": ("127.0.0.1", 50000),
        "root_path": "",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"query=anything",
        "headers": [
            (b"host", b"test"),
            *(
                (name.lower().encode(), value.encode())
                for name, value in normal_user_token_headers.items()
            ),
        ],
    }
    answering = asyncio.create_task(app(scope, receive, send))
    assert await to_thread.run_sync(_Walking.walk.started.wait, 5)
    left = time.monotonic()

    gone.set()

    assert await to_thread.run_sync(_Walking.walk.ended.wait, 5)
    assert _Walking.walk.how == "stopped"
    assert time.monotonic() - left < 5
    await asyncio.wait_for(answering, 5)
