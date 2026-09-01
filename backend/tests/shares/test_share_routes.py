import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.users import crud
from app.users.models import User
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import random_email

BASE = f"{settings.API_V1_STR}/shares"
CONNECTORS = f"{settings.API_V1_STR}/connectors"

VIEW: dict[str, Any] = {
    "kind": "rows",
    "filters": [{"column": "name", "op": "contains", "value": "report"}],
    "sort": [{"column": "name", "descending": True}],
    "page_size": 50,
    "column_order": ["name", "size"],
    "pinned_left": ["name"],
    "column_visibility": {"size": False},
    "column_sizing": {"name": 240.0},
}


@pytest.fixture
async def colleague(
    client: AsyncClient, db: AsyncSession
) -> tuple[User, dict[str, str]]:
    """Somebody other than the owner, with a token of their own."""
    email = random_email()
    headers = await authentication_token_from_email(client=client, email=email, db=db)
    user = await crud.get_user_by_email(session=db, email=email)
    assert user is not None
    return user, headers


@pytest.fixture
async def stranger(
    client: AsyncClient, db: AsyncSession
) -> tuple[User, dict[str, str]]:
    email = random_email()
    headers = await authentication_token_from_email(client=client, email=email, db=db)
    user = await crud.get_user_by_email(session=db, email=email)
    assert user is not None
    return user, headers


async def _connector(client: AsyncClient, headers: dict[str, str]) -> str:
    """A file connection: sharing never reaches the source, so this is enough."""
    response = await client.post(
        f"{CONNECTORS}/",
        headers=headers,
        json={
            "name": f"files {uuid.uuid4()}",
            "adapter_type": "file",
            "options": {"path": "/"},
        },
    )
    assert response.status_code == 200
    return str(response.json()["id"])


async def _grant(
    client: AsyncClient,
    headers: dict[str, str],
    connector_id: str,
    user_id: uuid.UUID,
    access: str = "read",
) -> None:
    response = await client.put(
        f"{CONNECTORS}/{connector_id}/grants",
        headers=headers,
        json={"user_id": str(user_id), "access": access},
    )
    assert response.status_code == 200


async def _share(
    client: AsyncClient,
    headers: dict[str, str],
    connector_id: str,
    *,
    node_id: str = "reports",
    node_label: str = "reports",
    view: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = await client.post(
        f"{BASE}/",
        headers=headers,
        json={
            "connector_id": connector_id,
            "node_id": node_id,
            "node_label": node_label,
            "view": VIEW if view is None else view,
        },
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def test_a_link_leads_back_to_the_view_it_was_made_from(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _connector(client, normal_user_token_headers)
    link = await _share(client, normal_user_token_headers, connector_id)

    response = await client.get(
        f"{BASE}/{link['token']}", headers=normal_user_token_headers
    )

    assert response.status_code == 200
    resolved = response.json()
    assert resolved["state"] == "open"
    assert resolved["connector_id"] == connector_id
    assert resolved["node_id"] == "reports"
    assert resolved["view"] == VIEW


async def test_the_same_view_shared_twice_is_one_link(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """D59: the button is idempotent, so one view does not grow addresses."""
    connector_id = await _connector(client, normal_user_token_headers)
    first = await _share(client, normal_user_token_headers, connector_id)
    again = await _share(client, normal_user_token_headers, connector_id)

    assert again["token"] == first["token"]
    assert again["id"] == first["id"]


async def test_another_query_over_the_same_node_is_another_link(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _connector(client, normal_user_token_headers)
    first = await _share(client, normal_user_token_headers, connector_id)
    other = await _share(
        client,
        normal_user_token_headers,
        connector_id,
        view={**VIEW, "page_size": 25},
    )

    assert other["token"] != first["token"]


async def test_a_stranger_cannot_make_a_link_to_a_connection_they_cannot_see(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    stranger: tuple[User, dict[str, str]],
) -> None:
    connector_id = await _connector(client, normal_user_token_headers)
    _, headers = stranger

    response = await client.post(
        f"{BASE}/",
        headers=headers,
        json={
            "connector_id": connector_id,
            "node_id": "reports",
            "node_label": "reports",
            "view": VIEW,
        },
    )

    assert response.status_code == 404


async def test_a_reader_with_read_may_make_a_link(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
) -> None:
    """D58: making an address hands nothing over, so `read` is enough."""
    connector_id = await _connector(client, normal_user_token_headers)
    user, headers = colleague
    await _grant(client, normal_user_token_headers, connector_id, user.id)

    link = await _share(client, headers, connector_id)

    assert link["token"]


async def test_a_reader_without_a_grant_is_told_what_it_is_and_who_shared_it(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    stranger: tuple[User, dict[str, str]],
) -> None:
    """D60: a state, not an error, and it names enough to ask about."""
    connector_id = await _connector(client, normal_user_token_headers)
    link = await _share(client, normal_user_token_headers, connector_id)
    _, headers = stranger

    response = await client.get(f"{BASE}/{link['token']}", headers=headers)

    assert response.status_code == 200
    resolved = response.json()
    assert resolved["state"] == "no_access"
    assert resolved["node_label"] == "reports"
    assert resolved["connector_label"]
    assert resolved["shared_by"]
    # Nothing that would let them read anything, and nothing to fetch with.
    assert "view" not in resolved
    assert "connector_id" not in resolved
    assert "node_id" not in resolved


async def test_a_grant_turns_the_same_link_into_the_view(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
) -> None:
    connector_id = await _connector(client, normal_user_token_headers)
    link = await _share(client, normal_user_token_headers, connector_id)
    user, headers = colleague

    barred = await client.get(f"{BASE}/{link['token']}", headers=headers)
    assert barred.json()["state"] == "no_access"

    await _grant(client, normal_user_token_headers, connector_id, user.id)

    opened = await client.get(f"{BASE}/{link['token']}", headers=headers)
    assert opened.json()["state"] == "open"


async def test_an_unknown_token_and_a_deleted_link_answer_the_same(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """A token cannot be probed for whether it ever existed."""
    connector_id = await _connector(client, normal_user_token_headers)
    link = await _share(client, normal_user_token_headers, connector_id)
    unknown = await client.get(
        f"{BASE}/nosuchtokenatall", headers=normal_user_token_headers
    )

    deleted = await client.delete(
        f"{BASE}/{link['id']}", headers=normal_user_token_headers
    )
    assert deleted.status_code == 200
    gone = await client.get(f"{BASE}/{link['token']}", headers=normal_user_token_headers)

    assert unknown.status_code == 404
    assert gone.status_code == 404
    assert gone.json()["detail"] == unknown.json()["detail"]


async def test_the_log_counts_the_reader_and_not_the_author(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
) -> None:
    """D59: the question is "did it reach them"."""
    connector_id = await _connector(client, normal_user_token_headers)
    link = await _share(client, normal_user_token_headers, connector_id)
    user, headers = colleague
    await _grant(client, normal_user_token_headers, connector_id, user.id)

    await client.get(f"{BASE}/{link['token']}", headers=headers)
    await client.get(f"{BASE}/{link['token']}", headers=headers)
    await client.get(f"{BASE}/{link['token']}", headers=normal_user_token_headers)

    listed = await client.get(
        f"{BASE}/",
        headers=normal_user_token_headers,
        params={"connector_id": connector_id},
    )
    assert listed.status_code == 200
    openers = listed.json()["data"][0]["openers"]
    assert [(opener["email"], opener["opens"]) for opener in openers] == [
        (user.email, 2)
    ]


async def test_the_owner_sees_every_link_and_a_reader_only_their_own(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
) -> None:
    connector_id = await _connector(client, normal_user_token_headers)
    user, headers = colleague
    await _grant(client, normal_user_token_headers, connector_id, user.id)
    mine = await _share(client, normal_user_token_headers, connector_id)
    theirs = await _share(client, headers, connector_id, node_id="other")

    owners_view = await client.get(
        f"{BASE}/",
        headers=normal_user_token_headers,
        params={"connector_id": connector_id},
    )
    readers_view = await client.get(
        f"{BASE}/", headers=headers, params={"connector_id": connector_id}
    )

    assert {link["id"] for link in owners_view.json()["data"]} == {
        mine["id"],
        theirs["id"],
    }
    assert [link["id"] for link in readers_view.json()["data"]] == [theirs["id"]]
    assert all(link["can_delete"] for link in owners_view.json()["data"])


async def test_a_revoked_grant_takes_the_log_but_not_the_link(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
) -> None:
    """D59: the address goes on working for the people it was sent to."""
    connector_id = await _connector(client, normal_user_token_headers)
    user, headers = colleague
    await _grant(client, normal_user_token_headers, connector_id, user.id)
    theirs = await _share(client, headers, connector_id)

    revoked = await client.delete(
        f"{CONNECTORS}/{connector_id}/grants/{user.id}",
        headers=normal_user_token_headers,
    )
    assert revoked.status_code == 200

    listed = await client.get(
        f"{BASE}/", headers=headers, params={"connector_id": connector_id}
    )
    still_open = await client.get(
        f"{BASE}/{theirs['token']}", headers=normal_user_token_headers
    )

    assert listed.status_code == 404
    assert still_open.json()["state"] == "open"


async def test_who_may_take_a_link_back(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
    stranger: tuple[User, dict[str, str]],
) -> None:
    connector_id = await _connector(client, normal_user_token_headers)
    reader, reader_headers = colleague
    other, other_headers = stranger
    await _grant(client, normal_user_token_headers, connector_id, reader.id)
    await _grant(client, normal_user_token_headers, connector_id, other.id)
    theirs = await _share(client, reader_headers, connector_id)

    # Somebody who can read the connection but does not own it, and did not
    # make this link: they hold a level, so they are told what is missing.
    refused = await client.delete(f"{BASE}/{theirs['id']}", headers=other_headers)
    assert refused.status_code == 403

    by_author = await client.delete(f"{BASE}/{theirs['id']}", headers=reader_headers)
    assert by_author.status_code == 200

    mine = await _share(client, reader_headers, connector_id, node_id="second")
    by_owner = await client.delete(
        f"{BASE}/{mine['id']}", headers=normal_user_token_headers
    )
    assert by_owner.status_code == 200


async def test_deleting_the_connection_takes_its_links(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _connector(client, normal_user_token_headers)
    link = await _share(client, normal_user_token_headers, connector_id)

    dropped = await client.delete(
        f"{CONNECTORS}/{connector_id}", headers=normal_user_token_headers
    )
    assert dropped.status_code == 200

    gone = await client.get(f"{BASE}/{link['token']}", headers=normal_user_token_headers)
    assert gone.status_code == 404


async def test_a_body_that_is_not_a_view_is_refused(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _connector(client, normal_user_token_headers)

    response = await client.post(
        f"{BASE}/",
        headers=normal_user_token_headers,
        json={
            "connector_id": connector_id,
            "node_id": "reports",
            "node_label": "reports",
            "view": {
                "kind": "rows",
                "filters": [{"column": "id", "op": "or 1=1", "value": "x"}],
            },
        },
    )

    assert response.status_code == 422
