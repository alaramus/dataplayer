import asyncio
import uuid

import pytest
from httpx import AsyncClient
from pydantic import BaseModel

from app.adapters import registry
from app.adapters.protocol import AdapterError, ConnectionCheckResult, NodeNotFound
from app.adapters.relation import RelationModel, RelationModelsRequest
from app.connectors.routes import _relation_models_for_request
from app.core.config import settings
from tests.utils.database import working_postgres_options

BASE = f"{settings.API_V1_STR}/connectors"


async def test_batch_read_falls_back_to_four_single_reads() -> None:
    class SingleRelationAdapter:
        def __init__(self) -> None:
            self.active = 0
            self.peak = 0

        async def relation_model(self, node_id: str) -> RelationModel:
            self.active += 1
            self.peak = max(self.peak, self.active)
            try:
                await asyncio.sleep(0)
                if node_id == "missing":
                    raise NodeNotFound(node_id)
                return RelationModel(node_id=node_id, name=node_id, kind="table")
            finally:
                self.active -= 1

    adapter = SingleRelationAdapter()
    request = RelationModelsRequest(
        node_ids=[*(f"public.table_{index}" for index in range(8)), "missing"]
    )

    result = await _relation_models_for_request(adapter, request)

    assert adapter.peak == 4
    assert len(result.models) == 8
    assert [failure.node_id for failure in result.failures] == ["missing"]



async def test_a_batch_past_its_snapshot_clock_is_read_one_by_one() -> None:
    class SlowBatchAdapter:
        async def relation_models_for_nodes(
            self, request: RelationModelsRequest
        ) -> list[RelationModel]:
            raise AdapterError("timeout", "The server did not answer in time")

        async def relation_model(self, node_id: str) -> RelationModel:
            return RelationModel(node_id=node_id, name=node_id, kind="table")

    request = RelationModelsRequest(node_ids=["public.a", "public.b"])

    result = await _relation_models_for_request(SlowBatchAdapter(), request)

    assert [model.node_id for model in result.models] == ["public.a", "public.b"]
    assert result.failures == []


async def test_a_batch_that_cannot_reach_the_source_is_not_retried() -> None:
    class UnreachableAdapter:
        singles = 0

        async def relation_models_for_nodes(
            self, request: RelationModelsRequest
        ) -> list[RelationModel]:
            raise AdapterError("network", "Could not reach the server")

        async def relation_model(self, node_id: str) -> RelationModel:
            self.singles += 1
            raise AssertionError("not expected")

    adapter = UnreachableAdapter()

    with pytest.raises(AdapterError):
        await _relation_models_for_request(
            adapter, RelationModelsRequest(node_ids=["public.a"])
        )
    assert adapter.singles == 0

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


async def test_batch_relation_models_are_cached_by_the_selected_set(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    response = await client.post(
        f"{BASE}/{connector_id}/relation-models",
        json={
            "node_ids": [
                "pg_catalog.pg_class",
                "pg_catalog.pg_namespace",
            ]
        },
        headers=normal_user_token_headers,
    )

    assert response.status_code == 200
    assert response.headers["X-Data-Cache"] == "miss"
    body = response.json()
    assert {model["node_id"] for model in body["models"]} == {
        "pg_catalog.pg_class",
        "pg_catalog.pg_namespace",
    }
    assert body["failures"] == []

    cached = await client.post(
        f"{BASE}/{connector_id}/relation-models",
        json={
            "node_ids": [
                "pg_catalog.pg_namespace",
                "pg_catalog.pg_class",
            ]
        },
        headers=normal_user_token_headers,
    )
    assert cached.status_code == 200
    assert cached.headers["X-Data-Cache"] == "hit"
    assert {model["node_id"] for model in cached.json()["models"]} == {
        "pg_catalog.pg_class",
        "pg_catalog.pg_namespace",
    }

    partial = await client.post(
        f"{BASE}/{connector_id}/relation-models",
        json={
            "node_ids": [
                "pg_catalog.pg_class",
                "pg_catalog.no_such_relation",
            ]
        },
        headers=normal_user_token_headers,
    )
    assert partial.status_code == 200
    assert partial.headers["X-Data-Cache"] == "bypass"
    assert [failure["node_id"] for failure in partial.json()["failures"]] == [
        "pg_catalog.no_such_relation"
    ]


async def test_relation_model_refresh_bypasses_the_server_cache(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    path = f"{BASE}/{connector_id}/relation-model"
    params = {"node_id": "pg_catalog.pg_class"}

    first = await client.get(path, params=params, headers=normal_user_token_headers)
    refreshed = await client.get(
        path, params={**params, "refresh": "true"}, headers=normal_user_token_headers
    )
    hit = await client.get(path, params=params, headers=normal_user_token_headers)

    assert first.headers["X-Data-Cache"] == "miss"
    assert refreshed.headers["X-Data-Cache"] == "refreshed"
    assert hit.headers["X-Data-Cache"] == "hit"


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
