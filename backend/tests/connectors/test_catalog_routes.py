import uuid

import pytest
from httpx import AsyncClient

from app.core.config import settings
from tests.utils.database import working_postgres_options

BASE = f"{settings.API_V1_STR}/connectors"


async def _create_connector(
    client: AsyncClient, headers: dict[str, str], name: str
) -> str:
    response = await client.post(
        f"{BASE}/",
        headers=headers,
        json={
            "name": name,
            "adapter_type": "postgres",
            "options": working_postgres_options(),
        },
    )
    assert response.status_code == 200
    return str(response.json()["id"])


async def test_root_returns_schemas(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _create_connector(
        client, normal_user_token_headers, f"catalog root {uuid.uuid4()}"
    )

    response = await client.get(
        f"{BASE}/{connector_id}/catalog", headers=normal_user_token_headers
    )

    assert response.status_code == 200
    nodes = response.json()
    assert all(node["kind"] == "schema" for node in nodes)
    assert "public" in [node["name"] for node in nodes]


async def test_schema_returns_tables(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _create_connector(
        client, normal_user_token_headers, f"catalog schema {uuid.uuid4()}"
    )

    response = await client.get(
        f"{BASE}/{connector_id}/catalog",
        headers=normal_user_token_headers,
        params={"node_id": "public"},
    )

    assert response.status_code == 200
    tables = [node for node in response.json() if node["kind"] == "table"]
    assert "connector" in [node["name"] for node in tables]


async def test_table_returns_columns(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _create_connector(
        client, normal_user_token_headers, f"catalog table {uuid.uuid4()}"
    )

    response = await client.get(
        f"{BASE}/{connector_id}/catalog",
        headers=normal_user_token_headers,
        params={"node_id": "public.connector"},
    )

    assert response.status_code == 200
    columns = {node["name"]: node for node in response.json()}
    assert columns["adapter_type"]["kind"] == "column"
    assert columns["adapter_type"]["data_type"]
    assert columns["adapter_type"]["has_children"] is False


async def test_unknown_node_returns_502_not_an_empty_list(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _create_connector(
        client, normal_user_token_headers, f"catalog missing {uuid.uuid4()}"
    )

    response = await client.get(
        f"{BASE}/{connector_id}/catalog",
        headers=normal_user_token_headers,
        params={"node_id": "no_such_schema"},
    )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["error_kind"] == "config"
    assert detail["message"]


async def test_foreign_connector_returns_404(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    superuser_token_headers: dict[str, str],
) -> None:
    connector_id = await _create_connector(
        client, superuser_token_headers, f"catalog foreign {uuid.uuid4()}"
    )

    response = await client.get(
        f"{BASE}/{connector_id}/catalog", headers=normal_user_token_headers
    )

    assert response.status_code == 404


async def test_unknown_connector_returns_404(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = await client.get(
        f"{BASE}/{uuid.uuid4()}/catalog", headers=normal_user_token_headers
    )

    assert response.status_code == 404


async def test_unauthenticated_request_is_rejected(client: AsyncClient) -> None:
    response = await client.get(f"{BASE}/{uuid.uuid4()}/catalog")

    assert response.status_code == 401


@pytest.mark.usefixtures("isolated_registry")
async def test_adapter_without_catalog_support_returns_501(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """Browsing is optional: a source with no catalog must not be forced to fake one."""
    from pydantic import BaseModel

    from app.adapters import registry
    from app.adapters.protocol import ConnectionCheckResult

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
        f"{BASE}/{created.json()['id']}/catalog", headers=normal_user_token_headers
    )

    assert response.status_code == 501
    assert "does not support browsing" in response.json()["detail"]["message"]
async def test_path_names_every_node_from_the_root_down(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _create_connector(
        client, normal_user_token_headers, f"catalog path {uuid.uuid4()}"
    )

    response = await client.get(
        f"{BASE}/{connector_id}/catalog/path",
        headers=normal_user_token_headers,
        params={"node_id": "public.connector"},
    )

    assert response.status_code == 200
    nodes = response.json()
    assert [node["name"] for node in nodes] == ["public", "connector"]
    assert [node["kind"] for node in nodes] == ["schema", "table"]


async def test_path_to_a_node_that_is_gone_returns_404(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """A tab outlives the table it shows, and must be told so in words."""
    connector_id = await _create_connector(
        client, normal_user_token_headers, f"catalog path gone {uuid.uuid4()}"
    )

    response = await client.get(
        f"{BASE}/{connector_id}/catalog/path",
        headers=normal_user_token_headers,
        params={"node_id": "public.no_such_table"},
    )

    assert response.status_code == 404
    assert response.json()["detail"]["message"]


async def test_path_without_a_node_is_rejected(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """The root has no path: it is the connector."""
    connector_id = await _create_connector(
        client, normal_user_token_headers, f"catalog path root {uuid.uuid4()}"
    )

    response = await client.get(
        f"{BASE}/{connector_id}/catalog/path", headers=normal_user_token_headers
    )

    assert response.status_code == 422


@pytest.mark.usefixtures("isolated_registry")
async def test_a_source_that_cannot_walk_back_answers_501(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """A source may browse forward and have no way back up: 501, not a lie."""
    from pydantic import BaseModel

    from app.adapters import registry
    from app.adapters.catalog import CatalogNode, DirectoryNode
    from app.adapters.protocol import ConnectionCheckResult

    class OneWayOptions(BaseModel):
        url: str

    class OneWayAdapter:
        def __init__(
            self, options: OneWayOptions, _context: registry.AdapterContext
        ) -> None:
            self.options = options

        async def check_connection(self) -> ConnectionCheckResult:
            return ConnectionCheckResult(ok=True, message="ok", latency_ms=1)

        async def list_children(self, node_id: str | None) -> list[CatalogNode]:
            return [DirectoryNode(id="a", name="a", has_children=False)]

    registry.register(
        name="oneway",
        title="One way",
        category="sql",
        description="A source that can be walked into but not out of.",
        options_schema=OneWayOptions,
        adapter_class=OneWayAdapter,
    )(OneWayAdapter)

    created = await client.post(
        f"{BASE}/",
        headers=normal_user_token_headers,
        json={
            "name": f"oneway {uuid.uuid4()}",
            "adapter_type": "oneway",
            "options": {"url": "https://example.com"},
        },
    )
    assert created.status_code == 200

    response = await client.get(
        f"{BASE}/{created.json()['id']}/catalog/path",
        headers=normal_user_token_headers,
        params={"node_id": "a"},
    )

    assert response.status_code == 501
    assert "where a node lives" in response.json()["detail"]["message"]
