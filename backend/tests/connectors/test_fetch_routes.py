import uuid
from typing import Any

import pytest
from httpx import AsyncClient

from app.core.config import settings
from tests.utils.database import working_postgres_options

BASE = f"{settings.API_V1_STR}/connectors"


async def _create_connector(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        f"{BASE}/",
        headers=headers,
        json={
            "name": f"fetch {uuid.uuid4()}",
            "adapter_type": "postgres",
            "options": working_postgres_options(),
        },
    )
    assert response.status_code == 200
    return str(response.json()["id"])


async def _fetch(
    client: AsyncClient, headers: dict[str, str], connector_id: str, **body: Any
) -> Any:
    return await client.post(
        f"{BASE}/{connector_id}/fetch", headers=headers, json=body
    )


async def test_returns_columns_and_rows(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _create_connector(client, normal_user_token_headers)

    response = await _fetch(
        client,
        normal_user_token_headers,
        connector_id,
        node_id="pg_catalog.pg_class",
        limit=5,
    )

    assert response.status_code == 200
    body = response.json()
    assert [column["name"] for column in body["columns"]]
    assert all("data_type" not in column for column in body["columns"])
    assert len(body["rows"]) == 5
    assert body["has_more"] is True
    assert "data_type" not in body
    assert "sortable" not in body
    assert "filterable" not in body


async def test_sorting_and_paging_are_applied(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _create_connector(client, normal_user_token_headers)
    sort = [{"column": "oid", "descending": False}]

    first = await _fetch(
        client,
        normal_user_token_headers,
        connector_id,
        node_id="pg_catalog.pg_class",
        limit=3,
        sort=sort,
    )
    second = await _fetch(
        client,
        normal_user_token_headers,
        connector_id,
        node_id="pg_catalog.pg_class",
        limit=3,
        offset=3,
        sort=sort,
    )

    assert first.json()["rows"] != second.json()["rows"]


async def test_unknown_column_is_rejected_with_422(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _create_connector(client, normal_user_token_headers)

    response = await _fetch(
        client,
        normal_user_token_headers,
        connector_id,
        node_id="public.connector",
        sort=[{"column": "no_such_column"}],
    )

    assert response.status_code == 422


async def test_injection_through_a_column_name_is_rejected(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _create_connector(client, normal_user_token_headers)

    response = await _fetch(
        client,
        normal_user_token_headers,
        connector_id,
        node_id="public.connector",
        filters=[
            {"column": 'id"; DROP TABLE connector; --', "op": "eq", "value": 1}
        ],
    )

    assert response.status_code == 422


async def test_unknown_operator_is_rejected(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _create_connector(client, normal_user_token_headers)

    response = await _fetch(
        client,
        normal_user_token_headers,
        connector_id,
        node_id="public.connector",
        filters=[{"column": "id", "op": "; DROP TABLE connector --", "value": 1}],
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("node_id", "filters"),
    [
        (
            "pg_catalog.pg_class",
            [{"column": "oid", "op": "eq", "value": "not-a-number"}],
        ),
        (
            "public.connector",
            [{"column": "enabled", "op": "eq", "value": "yes"}],
        ),
        (
            "public.connector",
            [{"column": "updated_at", "op": "eq", "value": "not-a-datetime"}],
        ),
        (
            "pg_catalog.pg_class",
            [{"column": "oid", "op": "contains", "value": "1"}],
        ),
    ],
)
async def test_invalid_filter_is_a_safe_422(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    node_id: str,
    filters: list[dict[str, str]],
) -> None:
    connector_id = await _create_connector(client, normal_user_token_headers)

    response = await _fetch(
        client,
        normal_user_token_headers,
        connector_id,
        node_id=node_id,
        filters=filters,
    )

    assert response.status_code == 422
    assert "psycopg" not in response.text
    assert "password" not in response.text


async def test_limit_above_the_maximum_is_rejected(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _create_connector(client, normal_user_token_headers)

    response = await _fetch(
        client,
        normal_user_token_headers,
        connector_id,
        node_id="public.connector",
        limit=5000,
    )

    assert response.status_code == 422


async def test_unknown_relation_returns_502(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _create_connector(client, normal_user_token_headers)

    response = await _fetch(
        client,
        normal_user_token_headers,
        connector_id,
        node_id="public.no_such_table",
    )

    assert response.status_code == 502
    assert response.json()["detail"]["error_kind"] == "config"


async def test_foreign_connector_returns_404(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    superuser_token_headers: dict[str, str],
) -> None:
    connector_id = await _create_connector(client, superuser_token_headers)

    response = await _fetch(
        client,
        normal_user_token_headers,
        connector_id,
        node_id="public.connector",
    )

    assert response.status_code == 404


async def test_unauthenticated_request_is_rejected(client: AsyncClient) -> None:
    response = await client.post(
        f"{BASE}/{uuid.uuid4()}/fetch", json={"node_id": "public.connector"}
    )

    assert response.status_code == 401


@pytest.mark.usefixtures("isolated_registry")
async def test_adapter_without_fetch_support_returns_501(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
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
            "name": f"ping fetch {uuid.uuid4()}",
            "adapter_type": "ping",
            "options": {"url": "https://example.com"},
        },
    )
    assert created.status_code == 200

    response = await _fetch(
        client,
        normal_user_token_headers,
        created.json()["id"],
        node_id="anything",
    )

    assert response.status_code == 501
