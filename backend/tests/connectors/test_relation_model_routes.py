import uuid

import pytest
from httpx import AsyncClient
from pydantic import BaseModel

from app.adapters import registry
from app.adapters.protocol import ConnectionCheckResult
from app.core.config import settings
from tests.utils.database import working_postgres_options

BASE = f"{settings.API_V1_STR}/connectors"


async def _postgres_connector(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        f"{BASE}/",
        headers=headers,
        json={
            "name": f"relation {uuid.uuid4()}",
            "adapter_type": "postgres",
            "options": working_postgres_options(),
        },
    )
    assert response.status_code == 200
    return str(response.json()["id"])


async def _file_connector(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        f"{BASE}/",
        headers=headers,
        json={
            "name": f"relation files {uuid.uuid4()}",
            "adapter_type": "file",
            "options": {"path": "/"},
        },
    )
    assert response.status_code == 200
    return str(response.json()["id"])


async def test_describes_a_relation(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    response = await client.get(
        f"{BASE}/{connector_id}/relation-model",
        params={"node_id": "pg_catalog.pg_class"},
        headers=normal_user_token_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "pg_class"
    assert body["kind"] == "table"
    names = [column["name"] for column in body["columns"]]
    assert "relname" in names
    relname = next(c for c in body["columns"] if c["name"] == "relname")
    assert relname["type"]["sql"] == "name"
    assert relname["type"]["category"] == "string"


async def test_a_relation_that_is_gone_is_not_a_failure(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    response = await client.get(
        f"{BASE}/{connector_id}/relation-model",
        params={"node_id": "public.no_such_table"},
        headers=normal_user_token_headers,
    )
    assert response.status_code == 404


async def _ping_connector(client: AsyncClient, headers: dict[str, str]) -> str:
    """A source with no capability beyond being reachable.

    The capability-level answers need one: both real adapters describe
    relations now, and the file source changes rows and columns of a
    delimited file since D53, so neither can stand for a source that cannot.
    """

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
        headers=headers,
        json={
            "name": f"ping {uuid.uuid4()}",
            "adapter_type": "ping",
            "options": {"url": "https://example.com"},
        },
    )
    assert created.status_code == 200
    return str(created.json()["id"])


@pytest.mark.usefixtures("isolated_registry")
async def test_a_source_without_relations_says_so(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """Describing is optional, and a source that cannot must not fake one."""
    connector_id = await _ping_connector(client, normal_user_token_headers)

    response = await client.get(
        f"{BASE}/{connector_id}/relation-model",
        params={"node_id": "anything"},
        headers=normal_user_token_headers,
    )

    assert response.status_code == 501


async def test_a_file_node_that_is_not_there_is_not_found(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """A file source describes datasets, so a missing node is a node answer."""
    connector_id = await _file_connector(client, normal_user_token_headers)
    response = await client.get(
        f"{BASE}/{connector_id}/relation-model",
        params={"node_id": "anything"},
        headers=normal_user_token_headers,
    )
    assert response.status_code == 404


@pytest.mark.usefixtures("isolated_registry")
async def test_a_source_without_column_changes_says_so(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _ping_connector(client, normal_user_token_headers)

    added = await client.post(
        f"{BASE}/{connector_id}/columns",
        headers=normal_user_token_headers,
        json={"node_id": "anything", "name": "note", "type_code": "text"},
    )
    dropped = await client.request(
        "DELETE",
        f"{BASE}/{connector_id}/columns",
        headers=normal_user_token_headers,
        json={"node_id": "anything", "name": "note"},
    )

    assert added.status_code == 501
    assert dropped.status_code == 501


@pytest.mark.usefixtures("isolated_registry")
async def test_a_source_without_row_changes_says_so(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _ping_connector(client, normal_user_token_headers)

    inserted = await client.post(
        f"{BASE}/{connector_id}/rows",
        headers=normal_user_token_headers,
        json={"node_id": "anything", "values": []},
    )
    deleted = await client.request(
        "DELETE",
        f"{BASE}/{connector_id}/rows",
        headers=normal_user_token_headers,
        json={"node_id": "anything", "row_handles": ["opaque"]},
    )

    assert inserted.status_code == 501
    assert deleted.status_code == 501


async def test_requires_authentication(client: AsyncClient) -> None:
    response = await client.get(
        f"{BASE}/{uuid.uuid4()}/relation-model",
        params={"node_id": "public.x"},
    )
    assert response.status_code == 401
