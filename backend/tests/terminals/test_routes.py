"""A terminal's socket: who may open one, and what travels on it (D148, D149).

Every refusal is reached without a server: each stands before anything is
sent to one. The two that type into a shell need `docker compose up -d sshd`.
"""

import json
import uuid
from typing import Any
from urllib.parse import urlsplit

import pytest
from httpx import AsyncClient
from httpx_ws import AsyncWebSocketSession
from sqlmodel.ext.asyncio.session import AsyncSession
from wsproto.events import BytesMessage, TextMessage

from app.adapters.ssh import keys
from app.core.config import settings
from app.terminals.slots import SLOTS
from app.users import crud
from app.users.models import User
from tests.utils import services
from tests.utils.socket import hung_up_on, open_socket, token_of
from tests.utils.ssh import pinned_key
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import random_email

CONNECTORS = f"{settings.API_V1_STR}/connectors"
TERMINALS = "/terminals"


@pytest.fixture
async def colleague(client: AsyncClient, db: AsyncSession) -> tuple[User, dict[str, str]]:
    """Somebody other than the owner, with a token of their own."""
    email = random_email()
    headers = await authentication_token_from_email(client=client, email=email, db=db)
    user = await crud.get_user_by_email(session=db, email=email)
    assert user is not None
    return user, headers


async def _connector(
    client: AsyncClient, headers: dict[str, str], adapter_type: str, options: dict[str, Any]
) -> str:
    created = await client.post(
        f"{CONNECTORS}/",
        headers=headers,
        json={
            "name": f"{adapter_type} {uuid.uuid4().hex[:8]}",
            "adapter_type": adapter_type,
            "options": options,
        },
    )
    assert created.status_code == 200, created.text
    return str(created.json()["id"])


async def _unreachable_server(client: AsyncClient, headers: dict[str, str]) -> str:
    """An SSH connection to a host that does not exist, with a key pinned."""
    return await _connector(
        client,
        headers,
        "ssh",
        {
            "auth_method": "password",
            "host": "server.invalid",
            "username": "deploy",
            "password": "secret",
            "host_key": keys.generate("ed25519", None).facts.public_key,
        },
    )


def _opening(headers: dict[str, str], connector_id: str) -> dict[str, Any]:
    return {
        "type": "open",
        "token": token_of(headers),
        "connector_id": connector_id,
        "cols": 80,
        "rows": 24,
    }


async def _refused(first_frame: dict[str, Any] | None) -> dict[str, Any]:
    """What the server says before hanging up on this first frame."""
    async with hung_up_on(TERMINALS) as ws:
        if first_frame is not None:
            await ws.send_json(first_frame)
        frame: dict[str, Any] = await ws.receive_json(timeout=15)
        await ws.receive_json(timeout=5)
    return frame


async def _next_text(ws: AsyncWebSocketSession) -> dict[str, Any]:
    """The next text frame, past whatever output arrives before it."""
    while True:
        event = await ws.receive(timeout=10)
        if isinstance(event, TextMessage):
            frame: dict[str, Any] = json.loads(event.data)
            return frame


async def _output_until(ws: AsyncWebSocketSession, needle: bytes) -> bytes:
    seen = b""
    while needle not in seen:
        event = await ws.receive(timeout=10)
        if isinstance(event, TextMessage):
            raise AssertionError(f"a text frame in the middle of output: {event.data}")
        if isinstance(event, BytesMessage):
            seen += bytes(event.data)
    return seen


@pytest.mark.usefixtures("client")
async def test_a_socket_that_says_nothing_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "WS_AUTH_TIMEOUT_SECONDS", 0.2)

    frame = await _refused(None)

    assert frame == {
        "type": "refused",
        "code": "unauthenticated",
        "message": "Say who you are first",
        "error_kind": None,
    }


async def test_a_token_that_is_nobodys_is_refused(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _unreachable_server(client, normal_user_token_headers)

    frame = await _refused(
        _opening(normal_user_token_headers, connector_id) | {"token": "not-a-token"}
    )

    assert frame["code"] == "unauthenticated"


@pytest.mark.usefixtures("client")
async def test_a_first_frame_that_opens_nothing_is_refused() -> None:
    frame = await _refused({"type": "resize", "cols": 80, "rows": 24})

    assert frame["code"] == "malformed"


async def test_a_connection_shared_with_somebody_opens_no_terminal_for_them(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
) -> None:
    """Even the widest grant: typing into the server is its owner's (D149)."""
    user, headers = colleague
    connector_id = await _unreachable_server(client, normal_user_token_headers)
    granted = await client.put(
        f"{CONNECTORS}/{connector_id}/grants",
        headers=normal_user_token_headers,
        json={"user_id": str(user.id), "access": "structure"},
    )
    assert granted.status_code == 200, granted.text

    frame = await _refused(_opening(headers, connector_id))

    assert frame["code"] == "forbidden"


async def test_somebody_elses_connection_is_not_found(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
) -> None:
    _, headers = colleague
    connector_id = await _unreachable_server(client, normal_user_token_headers)

    frame = await _refused(_opening(headers, connector_id))

    assert frame["code"] == "not_found"


async def test_a_source_with_no_shell_opens_no_terminal(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _connector(client, normal_user_token_headers, "file", {"path": "/"})

    frame = await _refused(_opening(normal_user_token_headers, connector_id))

    assert frame["code"] == "unsupported"


async def test_a_switched_off_connection_opens_no_terminal(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _unreachable_server(client, normal_user_token_headers)
    switched = await client.patch(
        f"{CONNECTORS}/{connector_id}",
        headers=normal_user_token_headers,
        json={"enabled": False},
    )
    assert switched.status_code == 200, switched.text

    frame = await _refused(_opening(normal_user_token_headers, connector_id))

    assert frame["code"] == "disabled"


async def test_no_more_terminals_than_one_person_may_hold(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(SLOTS, "limit", 0)
    connector_id = await _unreachable_server(client, normal_user_token_headers)

    frame = await _refused(_opening(normal_user_token_headers, connector_id))

    assert frame["code"] == "too_many"


async def test_a_server_that_cannot_be_reached_is_said_in_the_sources_words(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # One slot, asked for twice: a slot kept by the first refusal would make
    # the second one `too_many`.
    monkeypatch.setattr(SLOTS, "limit", 1)
    connector_id = await _unreachable_server(client, normal_user_token_headers)

    first = await _refused(_opening(normal_user_token_headers, connector_id))
    second = await _refused(_opening(normal_user_token_headers, connector_id))

    assert first["code"] == "source"
    assert first["error_kind"] == "network"
    assert "server.invalid" not in first["message"]
    assert second["code"] == "source"


# --- a real shell ---------------------------------------------------------


@pytest.fixture
async def server_connector(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> str:
    parts = urlsplit(services.SSH.require())
    server = {
        "host": parts.hostname,
        "port": parts.port or 22,
        "username": parts.username,
        "password": parts.password,
    }
    pinned = await pinned_key(str(server["host"]), int(str(server["port"])))
    return await _connector(
        client,
        normal_user_token_headers,
        "ssh",
        {"auth_method": "password", **server, "host_key": pinned},
    )


async def test_the_owner_types_into_a_shell_and_is_told_when_it_ends(
    normal_user_token_headers: dict[str, str], server_connector: str
) -> None:
    async with hung_up_on(TERMINALS) as ws:
        await ws.send_json(_opening(normal_user_token_headers, server_connector))
        assert (await _next_text(ws))["type"] == "ready"

        # The arithmetic is the shell's, so the answer is not the echo.
        await ws.send_bytes(b'echo "dp-$((6*7))"\n')
        seen = await _output_until(ws, b"dp-42")
        await ws.send_bytes(b"exit 5\n")
        ended = await _next_text(ws)
        await ws.receive(timeout=5)

    assert b"dp-42" in seen
    assert ended == {"type": "ended", "exit_status": 5}


async def test_a_resize_and_a_frame_not_understood_leave_the_shell_running(
    normal_user_token_headers: dict[str, str], server_connector: str
) -> None:
    async with open_socket(TERMINALS) as ws:
        await ws.send_json(_opening(normal_user_token_headers, server_connector))
        assert (await _next_text(ws))["type"] == "ready"

        await ws.send_text("not a frame")
        error = await _next_text(ws)
        await ws.send_json({"type": "resize", "cols": 132, "rows": 43})
        await ws.send_bytes(b'stty size; echo "dp-$((6*7))"\n')
        seen = await _output_until(ws, b"dp-42")

    assert error["type"] == "error"
    assert b"43 132" in seen
