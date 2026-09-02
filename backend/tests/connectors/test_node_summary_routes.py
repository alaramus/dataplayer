import uuid
import zipfile
from pathlib import Path

import pytest
from httpx import AsyncClient
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters import registry
from app.adapters.protocol import ConnectionCheckResult
from app.core.config import settings
from app.users import crud, storage
from tests.utils.database import working_postgres_options

BASE = f"{settings.API_V1_STR}/connectors"


@pytest.fixture
async def home(db: AsyncSession) -> Path:
    """The personal directory of the user the route tests sign in as."""
    user = await crud.get_user_by_email(session=db, email=settings.EMAIL_TEST_USER)
    assert user is not None
    home = storage.create_home(user.id)
    (home / "described").mkdir(exist_ok=True)
    (home / "described" / "notes.txt").write_bytes(b"first\nsecond\n")
    with zipfile.ZipFile(home / "described" / "bundle.zip", "w") as bundle:
        bundle.writestr("readme.md", "# Inside\n")
    return home


async def _file_connector(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        f"{BASE}/",
        headers=headers,
        json={
            "name": f"summary files {uuid.uuid4()}",
            "adapter_type": "file",
            "options": {"path": "/"},
        },
    )
    assert response.status_code == 200
    return str(response.json()["id"])


@pytest.mark.usefixtures("home")
async def test_a_file_describes_itself(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await client.get(
        f"{BASE}/{connector_id}/node-summary",
        params={"node_id": "described/notes.txt"},
        headers=normal_user_token_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "notes.txt"
    assert body["kind"] == "file"
    assert body["size_bytes"] == 13
    assert body["modified_at"] is not None
    assert [item["kind"] for item in body["representations"]] == ["text"]
    assert body["contents"]["kind"] == "text"
    assert body["contents"]["lines"] == 2


@pytest.mark.usefixtures("home")
async def test_a_folder_and_a_member_are_described_through_the_same_route(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """One question about a node, whatever kind of node it is (D75)."""
    connector_id = await _file_connector(client, normal_user_token_headers)

    folder = await client.get(
        f"{BASE}/{connector_id}/node-summary",
        params={"node_id": "described"},
        headers=normal_user_token_headers,
    )
    entry = await client.get(
        f"{BASE}/{connector_id}/node-summary",
        params={"node_id": "described/bundle.zip/readme.md"},
        headers=normal_user_token_headers,
    )

    assert folder.status_code == 200
    assert folder.json()["kind"] == "directory"
    assert folder.json()["contents"]["kind"] == "directory"
    assert entry.status_code == 200
    assert entry.json()["kind"] == "entry"
    assert entry.json()["contents"]["kind"] == "entry"


@pytest.mark.usefixtures("home")
async def test_the_catalog_says_which_nodes_can_be_described(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """The client does not work it out from the kind — the source says it."""
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await client.get(
        f"{BASE}/{connector_id}/catalog",
        params={"node_id": "described"},
        headers=normal_user_token_headers,
    )

    assert response.status_code == 200
    nodes = response.json()
    assert nodes
    assert all(node["summarizable"] for node in nodes)


@pytest.mark.usefixtures("home")
async def test_a_node_that_is_not_there_is_not_found(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await client.get(
        f"{BASE}/{connector_id}/node-summary",
        params={"node_id": "described/nowhere.txt"},
        headers=normal_user_token_headers,
    )

    assert response.status_code == 404


@pytest.mark.usefixtures("home")
async def test_a_path_out_of_the_root_is_refused_by_the_route(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await client.get(
        f"{BASE}/{connector_id}/node-summary",
        params={"node_id": "../../etc/passwd"},
        headers=normal_user_token_headers,
    )

    assert response.status_code == 422


async def test_a_source_that_describes_no_nodes_says_so(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """PostgreSQL describes relations and does not describe nodes (D75)."""
    created = await client.post(
        f"{BASE}/",
        headers=normal_user_token_headers,
        json={
            "name": f"summary postgres {uuid.uuid4()}",
            "adapter_type": "postgres",
            "options": working_postgres_options(),
        },
    )
    assert created.status_code == 200

    response = await client.get(
        f"{BASE}/{created.json()['id']}/node-summary",
        params={"node_id": "public.users"},
        headers=normal_user_token_headers,
    )

    assert response.status_code == 501


@pytest.mark.usefixtures("isolated_registry")
async def test_a_source_with_no_capability_at_all_says_so(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    class PingOptions(BaseModel):
        url: str

    class PingAdapter:
        def __init__(
            self, options: PingOptions, _context: registry.AdapterContext
        ) -> None:
            self.options = options

        async def check_connection(self) -> ConnectionCheckResult:
            return ConnectionCheckResult(ok=True, message="pong", latency_ms=1)

    registry.register(
        name="ping",
        title="Ping",
        category="sql",
        description="A source that can only be reached.",
        options_schema=PingOptions,
        adapter_class=PingAdapter,
    )(PingAdapter)

    created = await client.post(
        f"{BASE}/",
        headers=normal_user_token_headers,
        json={
            "name": f"ping {uuid.uuid4()}",
            "adapter_type": "ping",
            "options": {"url": "https://example.com"},
        },
    )
    assert created.status_code == 200

    response = await client.get(
        f"{BASE}/{created.json()['id']}/node-summary",
        params={"node_id": "anything"},
        headers=normal_user_token_headers,
    )

    assert response.status_code == 501
