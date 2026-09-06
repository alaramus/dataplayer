import uuid
from collections.abc import AsyncGenerator
from typing import Any

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


async def _postgres_connector(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        f"{BASE}/",
        headers=headers,
        json={
            "name": f"design {uuid.uuid4()}",
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
            "name": f"design files {uuid.uuid4()}",
            "adapter_type": "file",
            "options": {"path": "/"},
        },
    )
    assert response.status_code == 200
    return str(response.json()["id"])


def _definition(name: str = "invoices") -> dict[str, Any]:
    return {
        "name": name,
        "columns": [
            {
                "id": "c1",
                "name": "id",
                "type": {"code": "integer"},
                "not_null": True,
                "generation": {"kind": "identity"},
            },
            {
                "id": "c2",
                "name": "amount",
                "type": {"code": "numeric", "precision": 12, "scale": 2},
                "not_null": True,
            },
        ],
        "primary_key": {"column_ids": ["c1"]},
        "checks": [
            {
                "id": "k1",
                "expression": {
                    "kind": "compare",
                    "operator": "gte",
                    "left": {"kind": "column", "column_id": "c2"},
                    "right": {"kind": "literal", "value_kind": "number", "text": "0"},
                },
            }
        ],
    }


async def test_the_destination_publishes_what_it_will_accept(
    client: AsyncClient, normal_user_token_headers: dict[str, str], schema: str
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    response = await client.post(
        f"{BASE}/{connector_id}/table-design/options",
        headers=normal_user_token_headers,
        json={"node_id": schema},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["supported"] is True
    assert body["schema_label"] == schema
    assert any(option["code"] == "jsonb" for option in body["types"])
    assert any(method["code"] == "btree" for method in body["index_methods"])
    assert body["limits"]["max_columns"] == 100


async def test_a_schema_the_server_owns_says_why_it_takes_nothing(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    response = await client.post(
        f"{BASE}/{connector_id}/table-design/options",
        headers=normal_user_token_headers,
        json={"node_id": "pg_catalog"},
    )

    assert response.status_code == 200
    assert response.json()["supported"] is False
    assert response.json()["types"] == []


async def test_the_plan_is_returned_and_nothing_is_created(
    client: AsyncClient, normal_user_token_headers: dict[str, str], schema: str
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    response = await client.post(
        f"{BASE}/{connector_id}/table-design/plan",
        headers=normal_user_token_headers,
        json={"node_id": schema, "definition": _definition(), "revision": 7},
    )

    assert response.status_code == 200, response.text
    plan = response.json()
    assert plan["revision"] == 7
    assert plan["problems"] == []
    assert plan["fingerprint"] != ""
    assert plan["statements"][0]["sql"].startswith("CREATE TABLE")

    catalog = await client.get(
        f"{BASE}/{connector_id}/catalog",
        headers=normal_user_token_headers,
        params={"node_id": schema, "refresh": True},
    )
    assert all(node["name"] != "invoices" for node in catalog.json())


async def test_a_definition_with_problems_is_an_answer_not_a_failure(
    client: AsyncClient, normal_user_token_headers: dict[str, str], schema: str
) -> None:
    definition = _definition()
    definition["columns"][0]["not_null"] = False
    definition["columns"][0]["generation"] = {"kind": "none"}

    connector_id = await _postgres_connector(client, normal_user_token_headers)
    answer = await client.post(
        f"{BASE}/{connector_id}/table-design/plan",
        headers=normal_user_token_headers,
        json={"node_id": schema, "definition": definition},
    )

    assert answer.status_code == 200, answer.text
    plan = answer.json()
    assert plan["fingerprint"] == ""
    assert plan["problems"][0]["object_id"] == "c1"
    assert plan["problems"][0]["kind"] == "invalid"


async def test_the_reviewed_plan_is_created_through_the_action(
    client: AsyncClient, normal_user_token_headers: dict[str, str], schema: str
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    plan = await client.post(
        f"{BASE}/{connector_id}/table-design/plan",
        headers=normal_user_token_headers,
        json={"node_id": schema, "definition": _definition()},
    )
    fingerprint = plan.json()["fingerprint"]

    created = await client.post(
        f"{BASE}/{connector_id}/actions/create_table",
        headers=normal_user_token_headers,
        json={
            "node_id": schema,
            "params": {"definition": _definition(), "fingerprint": fingerprint},
        },
    )

    assert created.status_code == 200, created.text
    body = created.json()
    assert body["message"] == "invoices created"
    assert body["reload_node_ids"] == [schema]
    assert body["created_node_id"] == f"{schema}.invoices"

    again = await client.post(
        f"{BASE}/{connector_id}/actions/create_table",
        headers=normal_user_token_headers,
        json={
            "node_id": schema,
            "params": {"definition": _definition(), "fingerprint": fingerprint},
        },
    )
    # A taken name is a conflict, never an implicit replacement.
    assert again.status_code == 409, again.text


async def test_a_plan_from_another_definition_is_refused(
    client: AsyncClient, normal_user_token_headers: dict[str, str], schema: str
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    plan = await client.post(
        f"{BASE}/{connector_id}/table-design/plan",
        headers=normal_user_token_headers,
        json={"node_id": schema, "definition": _definition()},
    )
    changed = _definition()
    changed["columns"][1]["name"] = "total"

    response = await client.post(
        f"{BASE}/{connector_id}/actions/create_table",
        headers=normal_user_token_headers,
        json={
            "node_id": schema,
            "params": {
                "definition": changed,
                "fingerprint": plan.json()["fingerprint"],
            },
        },
    )

    assert response.status_code == 409, response.text
    catalog = await client.get(
        f"{BASE}/{connector_id}/catalog",
        headers=normal_user_token_headers,
        params={"node_id": schema, "refresh": True},
    )
    assert all(node["name"] != "invoices" for node in catalog.json())


async def test_the_action_is_offered_on_a_schema_and_carries_its_own_screen(
    client: AsyncClient, normal_user_token_headers: dict[str, str], schema: str
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    response = await client.post(
        f"{BASE}/{connector_id}/actions",
        headers=normal_user_token_headers,
        json={"node_ids": [schema]},
    )

    actions = {action["name"]: action for action in response.json()}
    assert actions["create_table"]["applicable"] is True
    assert actions["create_table"]["acts_on"] == "children"
    # The editor is registered against the workflow, not against the name.
    assert (
        actions["create_table"]["params_schema"]["x-ui-workflow"] == "table-designer"
    )


async def test_a_schema_the_server_owns_does_not_offer_the_action(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    response = await client.post(
        f"{BASE}/{connector_id}/actions/create_table",
        headers=normal_user_token_headers,
        json={
            "node_id": "pg_catalog",
            "params": {"definition": _definition(), "fingerprint": "x"},
        },
    )

    assert response.status_code == 422, response.text


async def test_a_source_that_cannot_design_a_table_says_so(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)

    options = await client.post(
        f"{BASE}/{connector_id}/table-design/options",
        headers=normal_user_token_headers,
        json={"node_id": "anything"},
    )
    plan = await client.post(
        f"{BASE}/{connector_id}/table-design/plan",
        headers=normal_user_token_headers,
        json={"node_id": "anything", "definition": _definition()},
    )

    assert options.status_code == 501
    assert plan.status_code == 501


async def test_a_field_nobody_declared_is_refused(
    client: AsyncClient, normal_user_token_headers: dict[str, str], schema: str
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    definition = _definition()
    definition["columns"][0]["storage"] = "external"

    response = await client.post(
        f"{BASE}/{connector_id}/table-design/plan",
        headers=normal_user_token_headers,
        json={"node_id": schema, "definition": definition},
    )

    assert response.status_code == 422, response.text
