import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from httpx_ws import AsyncWebSocketSession
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.users import crud
from app.users.models import User
from tests.utils.socket import authenticated_socket
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import random_email

BASE = f"{settings.API_V1_STR}/shares"
CONNECTORS = f"{settings.API_V1_STR}/connectors"
TOPIC = "shares.requests"

VIEW: dict[str, Any] = {"kind": "rows", "page_size": 100}


@pytest.fixture
async def colleague(
    client: AsyncClient, db: AsyncSession
) -> tuple[User, dict[str, str]]:
    email = random_email()
    headers = await authentication_token_from_email(client=client, email=email, db=db)
    user = await crud.get_user_by_email(session=db, email=email)
    assert user is not None
    return user, headers


async def _connector(client: AsyncClient, headers: dict[str, str]) -> str:
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


async def _share(client: AsyncClient, headers: dict[str, str], connector_id: str) -> str:
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
    assert response.status_code == 200, response.text
    token: str = response.json()["token"]
    return token


async def _ask(client: AsyncClient, headers: dict[str, str], token: str) -> Any:
    return await client.post(f"{BASE}/{token}/request", headers=headers)


async def test_asking_reaches_the_owner_and_shows_on_the_link(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
) -> None:
    connector_id = await _connector(client, normal_user_token_headers)
    token = await _share(client, normal_user_token_headers, connector_id)
    user, headers = colleague

    asked = await _ask(client, headers, token)
    assert asked.status_code == 200
    assert asked.json()["state"] == "pending"

    waiting = await client.get(
        f"{BASE}/requests",
        headers=normal_user_token_headers,
        params={"connector_id": connector_id},
    )
    assert [row["requester_email"] for row in waiting.json()["data"]] == [user.email]
    # What they came looking for is kept beside the ask as context.
    assert waiting.json()["data"][0]["node_label"] == "reports"

    # The screen that offered the button now says it has been pressed.
    resolved = await client.get(f"{BASE}/{token}", headers=headers)
    assert resolved.json()["state"] == "no_access"
    assert resolved.json()["requested"] is True


async def test_asking_twice_is_one_ask(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
) -> None:
    """D61: pressing again is not a way to prod anybody."""
    connector_id = await _connector(client, normal_user_token_headers)
    token = await _share(client, normal_user_token_headers, connector_id)
    _, headers = colleague

    first = await _ask(client, headers, token)
    again = await _ask(client, headers, token)

    assert again.json()["id"] == first.json()["id"]
    waiting = await client.get(
        f"{BASE}/requests",
        headers=normal_user_token_headers,
        params={"connector_id": connector_id},
    )
    assert len(waiting.json()["data"]) == 1


async def test_somebody_who_already_has_access_has_nothing_to_ask_for(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
) -> None:
    connector_id = await _connector(client, normal_user_token_headers)
    token = await _share(client, normal_user_token_headers, connector_id)
    user, headers = colleague
    await client.put(
        f"{CONNECTORS}/{connector_id}/grants",
        headers=normal_user_token_headers,
        json={"user_id": str(user.id), "access": "read"},
    )

    refused = await _ask(client, headers, token)

    assert refused.status_code == 409


async def test_approving_is_an_ordinary_grant(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
) -> None:
    """D61: saying yes adds no second kind of access."""
    connector_id = await _connector(client, normal_user_token_headers)
    token = await _share(client, normal_user_token_headers, connector_id)
    user, headers = colleague
    asked = await _ask(client, headers, token)
    request_id = asked.json()["id"]

    approved = await client.post(
        f"{BASE}/requests/{request_id}/approve",
        headers=normal_user_token_headers,
        json={"access": "read"},
    )
    assert approved.status_code == 200
    assert approved.json()["state"] == "approved"

    # The grant is the one D33 already defines, and the link now opens.
    grants = await client.get(
        f"{CONNECTORS}/{connector_id}/grants", headers=normal_user_token_headers
    )
    assert [(row["email"], row["access"]) for row in grants.json()["data"]] == [
        (user.email, "read")
    ]
    opened = await client.get(f"{BASE}/{token}", headers=headers)
    assert opened.json()["state"] == "open"

    # And the ask is done with: a second window cannot answer it again.
    waiting = await client.get(
        f"{BASE}/requests",
        headers=normal_user_token_headers,
        params={"connector_id": connector_id},
    )
    assert waiting.json()["data"] == []
    twice = await client.post(
        f"{BASE}/requests/{request_id}/approve",
        headers=normal_user_token_headers,
        json={"access": "read"},
    )
    assert twice.status_code == 404


async def test_declining_leaves_no_grant_and_does_not_bar_asking_again(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
) -> None:
    connector_id = await _connector(client, normal_user_token_headers)
    token = await _share(client, normal_user_token_headers, connector_id)
    _, headers = colleague
    asked = await _ask(client, headers, token)

    declined = await client.post(
        f"{BASE}/requests/{asked.json()['id']}/decline",
        headers=normal_user_token_headers,
    )
    assert declined.status_code == 200
    assert declined.json()["state"] == "declined"

    grants = await client.get(
        f"{CONNECTORS}/{connector_id}/grants", headers=normal_user_token_headers
    )
    assert grants.json()["data"] == []

    # Circumstances change; a closed ask does not bar the next one.
    again = await _ask(client, headers, token)
    assert again.status_code == 200
    assert again.json()["id"] != asked.json()["id"]


async def test_only_the_person_who_asked_may_take_it_back(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
) -> None:
    connector_id = await _connector(client, normal_user_token_headers)
    token = await _share(client, normal_user_token_headers, connector_id)
    _, headers = colleague
    asked = await _ask(client, headers, token)
    request_id = asked.json()["id"]

    # Not even the owner: withdrawing is not the same statement as declining.
    by_owner = await client.delete(
        f"{BASE}/requests/{request_id}", headers=normal_user_token_headers
    )
    assert by_owner.status_code == 404

    by_asker = await client.delete(f"{BASE}/requests/{request_id}", headers=headers)
    assert by_asker.status_code == 200

    waiting = await client.get(
        f"{BASE}/requests",
        headers=normal_user_token_headers,
        params={"connector_id": connector_id},
    )
    assert waiting.json()["data"] == []


async def test_answering_belongs_to_the_owner_alone(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
) -> None:
    connector_id = await _connector(client, normal_user_token_headers)
    token = await _share(client, normal_user_token_headers, connector_id)
    user, headers = colleague
    asked = await _ask(client, headers, token)
    request_id = asked.json()["id"]

    # The person who asked cannot approve themselves, and cannot even see that
    # there is a list: they have no standing on the connection at all.
    theirs = await client.post(
        f"{BASE}/requests/{request_id}/approve", headers=headers, json={"access": "read"}
    )
    listed = await client.get(
        f"{BASE}/requests", headers=headers, params={"connector_id": connector_id}
    )
    assert theirs.status_code == 404
    assert listed.status_code == 404

    # Somebody who reads the connection is told what is missing rather than
    # that it does not exist: they can already see it.
    await client.put(
        f"{CONNECTORS}/{connector_id}/grants",
        headers=normal_user_token_headers,
        json={"user_id": str(user.id), "access": "read"},
    )
    with_read = await client.get(
        f"{BASE}/requests", headers=headers, params={"connector_id": connector_id}
    )
    assert with_read.status_code == 403


async def test_everything_waiting_on_me_crosses_connections(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
) -> None:
    """What the activity sheet asks for: no connection named (D113)."""
    first = await _connector(client, normal_user_token_headers)
    second = await _connector(client, normal_user_token_headers)
    user, headers = colleague
    await _ask(client, headers, await _share(client, normal_user_token_headers, first))
    await _ask(client, headers, await _share(client, normal_user_token_headers, second))

    waiting = await client.get(f"{BASE}/requests", headers=normal_user_token_headers)

    assert waiting.status_code == 200
    # Contains rather than equals: the point of the route is that it crosses
    # connections, so whatever else this user owns is in the answer too.
    rows = [row for row in waiting.json()["data"] if row["connector_id"] in {first, second}]
    assert {row["connector_id"] for row in rows} == {first, second}
    assert {row["requester_email"] for row in rows} == {user.email}
    # Each row names its own connection: a list that crosses them cannot say
    # "this connection".
    assert all(row["connector_label"] for row in rows)


async def test_deleting_a_connection_takes_what_was_waiting_on_it(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
) -> None:
    """Nothing is left for the owner to answer about a connection that is gone.

    The activity sheet leads from a waiting request to the connection it is
    about (D113), so a request outliving its subject would be a line nobody
    could act on.
    """
    connector_id = await _connector(client, normal_user_token_headers)
    _, headers = colleague
    await _ask(client, headers, await _share(client, normal_user_token_headers, connector_id))

    gone = await client.delete(
        f"{CONNECTORS}/{connector_id}", headers=normal_user_token_headers
    )
    assert gone.status_code == 200, gone.text

    waiting = await client.get(f"{BASE}/requests", headers=normal_user_token_headers)
    assert waiting.status_code == 200
    assert [row for row in waiting.json()["data"] if row["connector_id"] == connector_id] == []


async def test_everything_waiting_on_me_is_only_mine(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
) -> None:
    """Somebody else's asks are not in my list, and mine are not in theirs."""
    mine = await _connector(client, normal_user_token_headers)
    _, headers = colleague
    await _ask(client, headers, await _share(client, normal_user_token_headers, mine))

    theirs = await client.get(f"{BASE}/requests", headers=headers)

    assert theirs.status_code == 200
    assert theirs.json()["data"] == []


async def _event_on(ws: AsyncWebSocketSession, *, within: float = 10) -> dict[str, Any]:
    """The next frame of this topic, whatever else is on the socket."""
    while True:
        frame: dict[str, Any] = await ws.receive_json(timeout=within)
        assert frame["type"] == "event", frame
        if frame["topic"] == TOPIC:
            payload: dict[str, Any] = frame["payload"]
            return payload


async def test_both_sides_are_told_what_happened(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
) -> None:
    """The tap on the shoulder, over the socket the application already has.

    Driven through the real socket rather than the topic object: what matters
    is that somebody who subscribes and does nothing else hears about the ask.
    """
    connector_id = await _connector(client, normal_user_token_headers)
    token = await _share(client, normal_user_token_headers, connector_id)
    user, headers = colleague

    async with authenticated_socket(normal_user_token_headers) as owner_ws:
        await owner_ws.send_json({"type": "subscribe", "topic": TOPIC})
        async with authenticated_socket(headers) as asker_ws:
            await asker_ws.send_json({"type": "subscribe", "topic": TOPIC})

            asked = await _ask(client, headers, token)
            arrived = await _event_on(owner_ws)
            assert arrived["kind"] == "asked"
            assert arrived["connector_id"] == connector_id
            assert arrived["person"] == user.email

            await client.post(
                f"{BASE}/requests/{asked.json()['id']}/approve",
                headers=normal_user_token_headers,
                json={"access": "read"},
            )
            answered = await _event_on(asker_ws)
            assert answered["kind"] == "answered"
            assert answered["outcome"] == "approved"
            assert answered["access"] == "read"
