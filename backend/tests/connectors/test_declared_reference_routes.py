"""References somebody drew between two columns no source calls related (D106).

The pair under test is deliberately the one the old application was used for:
a PostgreSQL relation and a CSV in personal storage, joined on a code that
neither source has ever heard of.
"""

import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.users import crud, storage
from app.users.models import User
from tests.utils.database import working_postgres_options
from tests.utils.relation_fixture import make_schema, run
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import random_email

BASE = f"{settings.API_V1_STR}/connectors"
DECLARED = f"{settings.API_V1_STR}/declared-references"


@pytest.fixture
async def schema() -> AsyncGenerator[str]:
    async for name in make_schema():
        yield name


@pytest.fixture
async def home(db: AsyncSession) -> Path:
    """The personal directory of the user these tests sign in as."""
    user = await crud.get_user_by_email(session=db, email=settings.EMAIL_TEST_USER)
    assert user is not None
    home = storage.create_home(user.id)
    (home / "regions.csv").write_text(
        "code,label\nnorth,Northern\nsouth,Southern\n", encoding="utf-8"
    )
    return home


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
            "name": f"declared {uuid.uuid4()}",
            "adapter_type": "postgres",
            "options": working_postgres_options(),
        },
    )
    assert response.status_code == 200, response.text
    return str(response.json()["id"])


async def _file_connector(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        f"{BASE}/",
        headers=headers,
        json={
            "name": f"declared files {uuid.uuid4()}",
            "adapter_type": "file",
            "options": {"path": "/"},
        },
    )
    assert response.status_code == 200, response.text
    return str(response.json()["id"])


def _end(connector_id: str, node_id: str, column: str) -> dict[str, str]:
    return {"connector_id": connector_id, "node_id": node_id, "column": column}


async def _declare(
    client: AsyncClient,
    headers: dict[str, str],
    first: dict[str, str],
    second: dict[str, str],
) -> Any:
    return await client.post(
        f"{DECLARED}/", headers=headers, json={"ends": [first, second]}
    )


async def _fetch(
    client: AsyncClient, headers: dict[str, str], connector_id: str, **body: Any
) -> Any:
    return await client.post(
        f"{BASE}/{connector_id}/fetch", headers=headers, json=body
    )


async def _follow(
    client: AsyncClient, headers: dict[str, str], connector_id: str, **body: Any
) -> Any:
    return await client.post(
        f"{BASE}/{connector_id}/references", headers=headers, json=body
    )


def _between(listed: Any, first: str, second: str) -> list[str]:
    """The listed references drawn between exactly these two sources.

    Every test here signs in as the same person and the suite wipes only at
    the end, so the whole list also carries what earlier tests drew.
    """
    ends = {first, second}
    return [
        item["id"]
        for item in listed
        if {end["connector_id"] for end in item["ends"]} == ends
    ]


async def _seed(schema: str) -> None:
    await run(
        f"INSERT INTO {schema}.regions (id, code) "  # noqa: S608 -- fixture-owned.
        "VALUES (7, 'north'), (8, 'south')"
    )


@pytest.fixture
async def pair(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
    home: Path,  # noqa: ARG001 - personal storage, required for its side effect
) -> tuple[str, str, str]:
    """A PostgreSQL connection, a file connection, and a reference between them."""
    await _seed(schema)
    postgres_id = await _postgres_connector(client, normal_user_token_headers)
    file_id = await _file_connector(client, normal_user_token_headers)
    response = await _declare(
        client,
        normal_user_token_headers,
        _end(postgres_id, f"{schema}.regions", "code"),
        _end(file_id, "regions.csv", "code"),
    )
    assert response.status_code == 200, response.text
    return postgres_id, file_id, str(response.json()["id"])


@pytest.mark.usefixtures("home")
async def test_a_reference_is_drawn_between_two_sources(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
) -> None:
    postgres_id = await _postgres_connector(client, normal_user_token_headers)
    file_id = await _file_connector(client, normal_user_token_headers)

    response = await _declare(
        client,
        normal_user_token_headers,
        _end(postgres_id, f"{schema}.regions", "code"),
        _end(file_id, "regions.csv", "code"),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert [end["node_label"] for end in body["ends"]] == ["regions", "regions.csv"]
    assert [end["adapter_type"] for end in body["ends"]] == ["postgres", "file"]


async def test_both_ends_carry_the_arrow(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
    pair: tuple[str, str, str],
) -> None:
    """Neither end is the key: the way out is offered from both (D106)."""
    postgres_id, file_id, reference_id = pair

    relation = await _fetch(
        client,
        normal_user_token_headers,
        postgres_id,
        node_id=f"{schema}.regions",
        limit=5,
    )
    csv = await _fetch(
        client, normal_user_token_headers, file_id, node_id="regions.csv", limit=5
    )

    assert relation.json()["references"] == [
        {
            "name": f"declared:{reference_id}:a",
            "columns": ["code"],
            "target_title": relation.json()["references"][0]["target_title"],
        }
    ]
    assert "regions.csv" in relation.json()["references"][0]["target_title"]
    assert csv.json()["references"][0]["name"] == f"declared:{reference_id}:b"
    assert csv.json()["references"][0]["columns"] == ["code"]


async def test_following_it_lands_in_the_other_connection(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
    pair: tuple[str, str, str],
) -> None:
    postgres_id, file_id, reference_id = pair

    response = await _follow(
        client,
        normal_user_token_headers,
        postgres_id,
        node_id=f"{schema}.regions",
        reference=f"declared:{reference_id}:a",
        values=[{"column": "code", "value": "north"}],
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["kind"] == "rows"
    assert body["node"]["id"] == "regions.csv"
    assert body["connector"]["id"] == file_id
    assert body["connector"]["adapter_type"] == "file"
    assert body["filters"] == [{"column": "code", "op": "eq", "value": "north"}]


async def test_the_answer_is_a_request_the_target_accepts(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
    pair: tuple[str, str, str],
) -> None:
    """The round trip: a predicate built here is one the file source honours."""
    postgres_id, file_id, reference_id = pair
    followed = await _follow(
        client,
        normal_user_token_headers,
        postgres_id,
        node_id=f"{schema}.regions",
        reference=f"declared:{reference_id}:a",
        values=[{"column": "code", "value": "north"}],
    )
    target = followed.json()

    response = await _fetch(
        client,
        normal_user_token_headers,
        target["connector"]["id"],
        node_id=target["node"]["id"],
        filters=target["filters"],
        limit=10,
    )

    assert response.status_code == 200, response.text
    assert response.json()["rows"] == [["north", "Northern"]]


async def test_following_it_from_the_file_lands_in_the_relation(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
    pair: tuple[str, str, str],
) -> None:
    postgres_id, file_id, reference_id = pair

    response = await _follow(
        client,
        normal_user_token_headers,
        file_id,
        node_id="regions.csv",
        reference=f"declared:{reference_id}:b",
        values=[{"column": "code", "value": "south"}],
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["node"]["id"] == f"{schema}.regions"
    assert body["connector"]["id"] == postgres_id
    assert body["filters"] == [{"column": "code", "op": "eq", "value": "south"}]


async def test_a_row_with_no_value_names_nothing(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
    pair: tuple[str, str, str],
) -> None:
    postgres_id, _, reference_id = pair

    response = await _follow(
        client,
        normal_user_token_headers,
        postgres_id,
        node_id=f"{schema}.regions",
        reference=f"declared:{reference_id}:a",
        values=[{"column": "code", "value": None}],
    )

    assert response.status_code == 200
    assert response.json()["kind"] == "none"
    assert response.json()["reason"]


async def test_a_reference_belonging_to_another_node_is_refused(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
    pair: tuple[str, str, str],
) -> None:
    """The end named by the name has to be the relation being stood on."""
    postgres_id, _, reference_id = pair

    response = await _follow(
        client,
        normal_user_token_headers,
        postgres_id,
        node_id=f"{schema}.customers",
        reference=f"declared:{reference_id}:a",
        values=[{"column": "code", "value": "north"}],
    )

    assert response.status_code == 422


async def test_an_invented_reference_name_is_refused(
    client: AsyncClient, normal_user_token_headers: dict[str, str], schema: str
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    response = await _follow(
        client,
        normal_user_token_headers,
        connector_id,
        node_id=f"{schema}.regions",
        reference=f"declared:{uuid.uuid4()}:a",
        values=[{"column": "code", "value": "north"}],
    )

    assert response.status_code == 422


@pytest.mark.usefixtures("home")
async def test_a_column_the_source_does_not_have_is_refused(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
) -> None:
    postgres_id = await _postgres_connector(client, normal_user_token_headers)
    file_id = await _file_connector(client, normal_user_token_headers)

    response = await _declare(
        client,
        normal_user_token_headers,
        _end(postgres_id, f"{schema}.regions", "code"),
        _end(file_id, "regions.csv", "invented"),
    )

    assert response.status_code == 422, response.text
    assert "invented" in response.text


@pytest.mark.usefixtures("home")
async def test_a_column_that_cannot_be_looked_up_is_refused(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
) -> None:
    """`bytea` admits no equality, so it cannot be an end of a reference."""
    postgres_id = await _postgres_connector(client, normal_user_token_headers)
    file_id = await _file_connector(client, normal_user_token_headers)

    response = await _declare(
        client,
        normal_user_token_headers,
        _end(postgres_id, f"{schema}.customers", "picture"),
        _end(file_id, "regions.csv", "code"),
    )

    assert response.status_code == 422, response.text


async def test_a_column_cannot_reference_itself(
    client: AsyncClient, normal_user_token_headers: dict[str, str], schema: str
) -> None:
    postgres_id = await _postgres_connector(client, normal_user_token_headers)

    response = await _declare(
        client,
        normal_user_token_headers,
        _end(postgres_id, f"{schema}.regions", "code"),
        _end(postgres_id, f"{schema}.regions", "code"),
    )

    assert response.status_code == 422


@pytest.mark.usefixtures("home")
async def test_a_connection_the_caller_cannot_read_is_not_an_end(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
    schema: str,
) -> None:
    _, colleague_headers = colleague
    theirs = await _postgres_connector(client, colleague_headers)
    file_id = await _file_connector(client, normal_user_token_headers)

    response = await _declare(
        client,
        normal_user_token_headers,
        _end(theirs, f"{schema}.regions", "code"),
        _end(file_id, "regions.csv", "code"),
    )

    assert response.status_code == 404


async def test_the_same_pair_drawn_twice_is_one_reference(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
    pair: tuple[str, str, str],
) -> None:
    postgres_id, file_id, reference_id = pair

    again = await _declare(
        client,
        normal_user_token_headers,
        _end(file_id, "regions.csv", "code"),
        _end(postgres_id, f"{schema}.regions", "code"),
    )

    assert again.status_code == 200, again.text
    assert again.json()["id"] == reference_id
    listed = await client.get(f"{DECLARED}/", headers=normal_user_token_headers)
    assert _between(listed.json(), postgres_id, file_id) == [reference_id]


@pytest.mark.usefixtures("normal_user_token_headers", "schema")
async def test_a_reference_belongs_to_the_person_who_drew_it(
    client: AsyncClient,
    colleague: tuple[User, dict[str, str]],
    pair: tuple[str, str, str],
) -> None:
    _, _, reference_id = pair
    _, colleague_headers = colleague

    listed = await client.get(f"{DECLARED}/", headers=colleague_headers)
    removed = await client.delete(f"{DECLARED}/{reference_id}", headers=colleague_headers)

    assert listed.json() == []
    assert removed.status_code == 404


async def test_removing_it_takes_the_arrow_off_the_page(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
    pair: tuple[str, str, str],
) -> None:
    postgres_id, _, reference_id = pair

    removed = await client.delete(
        f"{DECLARED}/{reference_id}", headers=normal_user_token_headers
    )

    assert removed.status_code == 200
    page = await _fetch(
        client,
        normal_user_token_headers,
        postgres_id,
        node_id=f"{schema}.regions",
        limit=1,
    )
    assert page.json()["references"] == []


async def test_a_switched_off_far_end_takes_the_arrow_off_the_page(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
    pair: tuple[str, str, str],
) -> None:
    """D106: a reference is visible only while both of its ends are."""
    postgres_id, file_id, _ = pair

    disabled = await client.patch(
        f"{BASE}/{file_id}", headers=normal_user_token_headers, json={"enabled": False}
    )

    assert disabled.status_code == 200, disabled.text
    page = await _fetch(
        client,
        normal_user_token_headers,
        postgres_id,
        node_id=f"{schema}.regions",
        limit=1,
    )
    assert page.json()["references"] == []
    listed = await client.get(f"{DECLARED}/", headers=normal_user_token_headers)
    assert _between(listed.json(), postgres_id, file_id) == []


async def test_the_list_is_filtered_to_one_node(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
    pair: tuple[str, str, str],
) -> None:
    postgres_id, _, reference_id = pair

    here = await client.get(
        f"{DECLARED}/",
        headers=normal_user_token_headers,
        params={"connector_id": postgres_id, "node_id": f"{schema}.regions"},
    )
    elsewhere = await client.get(
        f"{DECLARED}/",
        headers=normal_user_token_headers,
        params={"connector_id": postgres_id, "node_id": f"{schema}.customers"},
    )

    assert [item["id"] for item in here.json()] == [reference_id]
    assert elsewhere.json() == []


async def test_a_real_key_still_names_its_own_connection(
    client: AsyncClient, normal_user_token_headers: dict[str, str], schema: str
) -> None:
    """D108: the route completes every answer, not only a declared one."""
    await _seed(schema)
    await run(
        f"INSERT INTO {schema}.customers "  # noqa: S608 -- fixture-owned.
        "(region_id, region_code, name) VALUES (7, 'north', 'Ada')"
    )
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
    assert response.json()["connector"]["id"] == connector_id
