import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.users import crud
from app.users.models import User
from tests.utils.database import working_postgres_options
from tests.utils.relation_fixture import make_schema, run
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import random_email

BASE = f"{settings.API_V1_STR}/connectors"


@pytest.fixture
async def schema() -> AsyncGenerator[str]:
    async for name in make_schema():
        yield name


@pytest.fixture
async def colleague(
    client: AsyncClient, db: AsyncSession
) -> tuple[User, dict[str, str]]:
    email = random_email()
    headers = await authentication_token_from_email(client=client, email=email, db=db)
    user = await crud.get_user_by_email(session=db, email=email)
    assert user is not None
    return user, headers


async def _postgres_connector(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        f"{BASE}/",
        headers=headers,
        json={
            "name": f"references {uuid.uuid4()}",
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
            "name": f"reference files {uuid.uuid4()}",
            "adapter_type": "file",
            "options": {"path": "/"},
        },
    )
    assert response.status_code == 200
    return str(response.json()["id"])


async def _follow(
    client: AsyncClient, headers: dict[str, str], connector_id: str, **body: Any
) -> Any:
    return await client.post(
        f"{BASE}/{connector_id}/references", headers=headers, json=body
    )


async def _seed(schema: str) -> None:
    await run(
        f"INSERT INTO {schema}.regions (id, code) "  # noqa: S608 -- schema is fixture-owned.
        "VALUES (7, 'north')"
    )
    await run(
        f"INSERT INTO {schema}.customers "  # noqa: S608 -- schema is fixture-owned.
        "(region_id, region_code, name) VALUES (7, 'north', 'Ada')"
    )


async def _arriving(
    client: AsyncClient, headers: dict[str, str], connector_id: str, node_id: str
) -> Any:
    return await client.post(
        f"{BASE}/{connector_id}/references/arriving",
        headers=headers,
        json={"node_id": node_id},
    )


async def test_a_page_carries_the_keys_it_can_be_left_by(
    client: AsyncClient, normal_user_token_headers: dict[str, str], schema: str
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    response = await client.post(
        f"{BASE}/{connector_id}/fetch",
        headers=normal_user_token_headers,
        json={"node_id": f"{schema}.customers", "limit": 1},
    )

    assert response.status_code == 200
    references = response.json()["references"]
    assert references == [
        {
            "name": "customers_region_fkey",
            "columns": ["region_id", "region_code"],
            "target_title": f"{schema}.regions",
        }
    ]


async def test_following_a_key_answers_with_a_node_and_a_predicate(
    client: AsyncClient, normal_user_token_headers: dict[str, str], schema: str
) -> None:
    await _seed(schema)
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    response = await _follow(
        client,
        normal_user_token_headers,
        connector_id,
        node_id=f"{schema}.customers",
        reference="customers_region_fkey",
        values=[
            {"column": "region_id", "value": "7"},
            {"column": "region_code", "value": "north"},
        ],
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["kind"] == "rows"
    assert body["node"]["id"] == f"{schema}.regions"
    assert body["node"]["kind"] == "table"
    assert body["filters"] == [
        {"column": "id", "op": "eq", "value": "7"},
        {"column": "code", "op": "eq", "value": "north"},
    ]


async def test_the_answer_is_a_request_the_fetch_route_accepts(
    client: AsyncClient, normal_user_token_headers: dict[str, str], schema: str
) -> None:
    """The two ends of the round trip are the same closed vocabulary."""
    await _seed(schema)
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    followed = await _follow(
        client,
        normal_user_token_headers,
        connector_id,
        node_id=f"{schema}.customers",
        reference="customers_region_fkey",
        values=[
            {"column": "region_id", "value": "7"},
            {"column": "region_code", "value": "north"},
        ],
    )
    target = followed.json()

    response = await client.post(
        f"{BASE}/{connector_id}/fetch",
        headers=normal_user_token_headers,
        json={
            "node_id": target["node"]["id"],
            "filters": target["filters"],
            "limit": 10,
        },
    )

    assert response.status_code == 200, response.text
    assert len(response.json()["rows"]) == 1


async def test_an_empty_key_is_answered_rather_than_refused(
    client: AsyncClient, normal_user_token_headers: dict[str, str], schema: str
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    response = await _follow(
        client,
        normal_user_token_headers,
        connector_id,
        node_id=f"{schema}.customers",
        reference="customers_region_fkey",
        values=[
            {"column": "region_id", "value": None},
            {"column": "region_code", "value": None},
        ],
    )

    assert response.status_code == 200
    assert response.json()["kind"] == "none"
    assert response.json()["reason"]


async def test_a_reference_the_relation_does_not_have_is_a_bad_request(
    client: AsyncClient, normal_user_token_headers: dict[str, str], schema: str
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    response = await _follow(
        client,
        normal_user_token_headers,
        connector_id,
        node_id=f"{schema}.customers",
        reference="invented",
        values=[{"column": "region_id", "value": "7"}],
    )

    assert response.status_code == 422


async def test_a_source_without_references_says_so(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await _follow(
        client,
        normal_user_token_headers,
        connector_id,
        node_id="anything",
        reference="whatever",
        values=[{"column": "id", "value": "1"}],
    )

    assert response.status_code == 501


async def test_without_a_grant_a_key_cannot_be_followed(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
    schema: str,
) -> None:
    """The id space is not an oracle for connections other people hold."""
    _, headers = colleague
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    response = await _follow(
        client,
        headers,
        connector_id,
        node_id=f"{schema}.customers",
        reference="customers_region_fkey",
        values=[{"column": "region_id", "value": "7"}],
    )

    assert response.status_code == 404


async def test_reading_is_enough_to_follow_a_key(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
    schema: str,
) -> None:
    """Following a key only looks at rows the caller may already read."""
    await _seed(schema)
    user, headers = colleague
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    granted = await client.put(
        f"{BASE}/{connector_id}/grants",
        headers=normal_user_token_headers,
        json={"user_id": str(user.id), "access": "read"},
    )
    assert granted.status_code == 200, granted.text

    response = await _follow(
        client,
        headers,
        connector_id,
        node_id=f"{schema}.customers",
        reference="customers_region_fkey",
        values=[
            {"column": "region_id", "value": "7"},
            {"column": "region_code", "value": "north"},
        ],
    )

    assert response.status_code == 200
    assert response.json()["kind"] == "rows"


async def test_a_relation_says_what_points_at_it(
    client: AsyncClient, normal_user_token_headers: dict[str, str], schema: str
) -> None:
    """The mirror of the page's own keys, asked for rather than read per page."""
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    response = await _arriving(
        client, normal_user_token_headers, connector_id, f"{schema}.regions"
    )

    assert response.status_code == 200, response.text
    assert response.json() == [
        {
            # A handle the source issues rather than the constraint's own name:
            # several arriving keys can share one (D110).
            "name": f"customers_region_fkey@{schema}.customers",
            # This relation's columns, because they are the cells the way back
            # is offered from and the values the caller already holds.
            "columns": ["id", "code"],
            "source_title": f"{schema}.customers",
        }
    ]


async def test_a_relation_nothing_points_at_says_so(
    client: AsyncClient, normal_user_token_headers: dict[str, str], schema: str
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    response = await _arriving(
        client, normal_user_token_headers, connector_id, f"{schema}.customers"
    )

    assert response.status_code == 200, response.text
    assert response.json() == []


async def test_a_relation_that_is_not_there_is_not_an_empty_answer(
    client: AsyncClient, normal_user_token_headers: dict[str, str], schema: str
) -> None:
    """"Nothing points here" and "there is no such relation" are not the same."""
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    response = await _arriving(
        client, normal_user_token_headers, connector_id, f"{schema}.invented"
    )

    assert response.status_code == 404


async def test_following_an_arriving_key_lands_on_the_rows_that_point_here(
    client: AsyncClient, normal_user_token_headers: dict[str, str], schema: str
) -> None:
    await _seed(schema)
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    response = await _follow(
        client,
        normal_user_token_headers,
        connector_id,
        node_id=f"{schema}.regions",
        reference=f"customers_region_fkey@{schema}.customers",
        direction="incoming",
        values=[
            {"column": "id", "value": "7"},
            {"column": "code", "value": "north"},
        ],
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["kind"] == "rows"
    assert body["node"]["id"] == f"{schema}.customers"
    assert body["connector"]["id"] == connector_id
    # The filters are over the referencing relation's own columns.
    assert body["filters"] == [
        {"column": "region_id", "op": "eq", "value": "7"},
        {"column": "region_code", "op": "eq", "value": "north"},
    ]


async def test_the_way_back_is_a_request_the_fetch_route_accepts(
    client: AsyncClient, normal_user_token_headers: dict[str, str], schema: str
) -> None:
    await _seed(schema)
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    followed = await _follow(
        client,
        normal_user_token_headers,
        connector_id,
        node_id=f"{schema}.regions",
        reference=f"customers_region_fkey@{schema}.customers",
        direction="incoming",
        values=[
            {"column": "id", "value": "7"},
            {"column": "code", "value": "north"},
        ],
    )
    target = followed.json()

    response = await client.post(
        f"{BASE}/{connector_id}/fetch",
        headers=normal_user_token_headers,
        json={
            "node_id": target["node"]["id"],
            "filters": target["filters"],
            "limit": 10,
        },
    )

    assert response.status_code == 200, response.text
    assert len(response.json()["rows"]) == 1


async def test_a_row_with_no_key_value_points_back_at_nothing(
    client: AsyncClient, normal_user_token_headers: dict[str, str], schema: str
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    response = await _follow(
        client,
        normal_user_token_headers,
        connector_id,
        node_id=f"{schema}.regions",
        reference=f"customers_region_fkey@{schema}.customers",
        direction="incoming",
        values=[
            {"column": "id", "value": None},
            {"column": "code", "value": None},
        ],
    )

    assert response.status_code == 200
    assert response.json()["kind"] == "none"


async def test_an_arriving_name_the_relation_does_not_have_is_a_bad_request(
    client: AsyncClient, normal_user_token_headers: dict[str, str], schema: str
) -> None:
    """The direction decides which reading the name is checked against."""
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    response = await _follow(
        client,
        normal_user_token_headers,
        connector_id,
        # This name is a key *of* customers, so it is not one arriving at it.
        node_id=f"{schema}.customers",
        reference="customers_region_fkey",
        direction="incoming",
        values=[{"column": "region_id", "value": "7"}],
    )

    assert response.status_code == 422
    assert "points at this relation" in response.text


async def test_a_source_that_cannot_search_for_arriving_keys_says_so(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)

    listed = await _arriving(
        client, normal_user_token_headers, connector_id, "sample.csv"
    )
    followed = await _follow(
        client,
        normal_user_token_headers,
        connector_id,
        node_id="sample.csv",
        reference="anything",
        direction="incoming",
        values=[{"column": "id", "value": "1"}],
    )

    assert listed.status_code == 501
    assert followed.status_code == 501
