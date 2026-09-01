"""Planning a statement, and not running it.

Against a real PostgreSQL, because a plan is the server's own answer and the
point of this capability is that it is the server's (D65).
"""

import uuid
from typing import Any

from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from tests.utils.database import working_postgres_options
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import random_email

BASE = f"{settings.API_V1_STR}/queries"
CONNECTORS = f"{settings.API_V1_STR}/connectors"


async def _headers(client: AsyncClient, db: AsyncSession) -> dict[str, str]:
    return await authentication_token_from_email(
        client=client, email=random_email(), db=db
    )


async def _postgres(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        f"{CONNECTORS}/",
        headers=headers,
        json={
            "name": f"pg {uuid.uuid4()}",
            "adapter_type": "postgres",
            "options": working_postgres_options(),
        },
    )
    assert response.status_code == 200, response.text
    return str(response.json()["id"])


async def _file(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        f"{CONNECTORS}/",
        headers=headers,
        json={
            "name": f"files {uuid.uuid4()}",
            "adapter_type": "file",
            "options": {"path": "/"},
        },
    )
    assert response.status_code == 200, response.text
    return str(response.json()["id"])


async def _explain(
    client: AsyncClient, headers: dict[str, str], connector_id: str, **body: Any
) -> Any:
    return await client.post(
        f"{BASE}/connectors/{connector_id}/explain", headers=headers, json=body
    )


async def test_a_plan_comes_back_as_a_tree_and_as_the_text_the_server_prints(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)

    response = await _explain(
        client, headers, connector_id, text="select * from demo_lab.projects"
    )

    assert response.status_code == 200, response.text
    plan = response.json()
    assert plan["plan"]["kind"] == "Seq Scan"
    assert plan["plan"]["relation"] == "projects"
    assert plan["plan"]["id"] == "0"
    assert plan["plan"]["total_cost"] > 0
    assert plan["rows"] is not None
    assert "Seq Scan" in plan["raw"]


async def test_a_plan_with_several_operations_keeps_their_shape(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)

    response = await _explain(
        client,
        headers,
        connector_id,
        text="select * from demo_lab.projects order by name limit 5",
    )

    plan = response.json()["plan"]
    assert plan["kind"] == "Limit"
    # A child's id says where it is, so a row of the table and a node of the
    # tree are the same operation.
    assert plan["children"][0]["id"] == "0.0"
    assert plan["children"][0]["kind"] == "Sort"


async def test_the_details_of_an_operation_travel_as_text(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)

    response = await _explain(
        client,
        headers,
        connector_id,
        text="select * from demo_lab.projects where name = 'x'",
    )

    plan = response.json()["plan"]
    assert "Filter" in plan["details"]
    assert isinstance(plan["details"]["Filter"], str)


async def test_a_parameterised_statement_is_planned_with_its_bindings(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)

    response = await _explain(
        client,
        headers,
        connector_id,
        text="select * from demo_lab.projects where name = :wanted",
        parameters=[{"name": "wanted", "value": "x"}],
    )

    assert response.status_code == 200, response.text
    assert response.json()["plan"]["kind"] == "Seq Scan"


async def test_explaining_does_not_run_the_statement(
    client: AsyncClient, db: AsyncSession
) -> None:
    """The guarantee of this capability, stated as a test (D65)."""
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)

    # pg_sleep would take ten seconds if it ran; a plan is immediate.
    response = await _explain(
        client, headers, connector_id, text="select pg_sleep(10)", timeout_seconds=5
    )

    assert response.status_code == 200, response.text
    assert response.json()["plan"]["kind"] == "Result"


async def test_a_statement_that_is_not_a_read_is_not_planned_here(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)

    dml = await _explain(client, headers, connector_id, text="delete from pg_class")
    already = await _explain(client, headers, connector_id, text="explain select 1")
    several = await _explain(client, headers, connector_id, text="select 1; select 2")

    assert dml.status_code == 422
    assert "dml" in dml.json()["detail"]
    assert already.status_code == 422
    assert several.status_code == 422


async def test_a_statement_the_source_refuses_answers_with_its_own_words(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)

    response = await _explain(
        client, headers, connector_id, text="select * from nothing_here"
    )

    assert response.status_code == 422
    assert "nothing_here" in response.json()["detail"]


async def test_a_source_that_does_not_plan_says_so(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _file(client, headers)

    response = await _explain(client, headers, connector_id, text="select 1")

    assert response.status_code == 501


async def test_the_profile_now_says_this_source_plans(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)

    response = await client.get(
        f"{BASE}/connectors/{connector_id}/profile", headers=headers
    )

    assert response.json()["supports_explain"] is True


async def test_planning_is_not_offered_to_somebody_without_the_connection(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    stranger = await _headers(client, db)
    connector_id = await _postgres(client, headers)

    response = await _explain(client, stranger, connector_id, text="select 1")

    assert response.status_code == 404
