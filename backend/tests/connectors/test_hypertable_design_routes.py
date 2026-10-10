import uuid
from collections.abc import AsyncGenerator

import pytest
from httpx import AsyncClient

from app.core.config import settings
from tests.utils.database import working_postgres_options
from tests.utils.relation_fixture import make_schema

BASE = f"{settings.API_V1_STR}/connectors"


@pytest.fixture
async def schema() -> AsyncGenerator[str]:
    async for name in make_schema():
        yield name


async def _connector(client: AsyncClient, headers: dict[str, str], adapter_type: str, options: object) -> str:
    response = await client.post(
        f"{BASE}/",
        headers=headers,
        json={"name": f"hypertables {uuid.uuid4()}", "adapter_type": adapter_type, "options": options},
    )
    assert response.status_code == 200
    return str(response.json()["id"])


async def test_a_table_without_timescale_says_why_it_has_no_design(
    client: AsyncClient, normal_user_token_headers: dict[str, str], schema: str
) -> None:
    connector_id = await _connector(client, normal_user_token_headers, "postgres", working_postgres_options())

    response = await client.post(
        f"{BASE}/{connector_id}/hypertable-design/state",
        headers=normal_user_token_headers,
        json={"node_id": f"{schema}.regions"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["design"] is None
    assert body["reason"] == "TimescaleDB is not installed on this database"


async def test_a_source_without_hypertables_answers_501(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _connector(client, normal_user_token_headers, "file", {"path": "/"})

    response = await client.post(
        f"{BASE}/{connector_id}/hypertable-design/state",
        headers=normal_user_token_headers,
        json={"node_id": "anything"},
    )

    assert response.status_code == 501


async def test_an_action_naming_no_hints_answers_501(
    client: AsyncClient, normal_user_token_headers: dict[str, str], schema: str
) -> None:
    connector_id = await _connector(client, normal_user_token_headers, "postgres", working_postgres_options())

    listed = await client.post(
        f"{BASE}/{connector_id}/actions", headers=normal_user_token_headers, json={"node_ids": [schema]},
    )
    assert listed.status_code == 200
    assert {item["name"]: item["offers_hints"] for item in listed.json()}["rename_schema"] is False

    response = await client.post(
        f"{BASE}/{connector_id}/actions/rename_schema/hints",
        headers=normal_user_token_headers,
        json={"node_id": schema, "params": {}},
    )
    assert response.status_code == 501
    assert "offers no hints" in response.json()["detail"]["message"]
