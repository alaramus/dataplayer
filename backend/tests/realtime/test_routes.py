"""The socket itself: who may speak on it, and what it accepts.

Nothing here knows what a topic does. That is the point of the module — the
transport carries frames for topics it has never heard of, the way the panel
engine carries panels it does not know.
"""

import pytest

from app.core.config import settings
from tests.utils.socket import (
    authenticated_socket,
    hung_up_on,
    open_socket,
    token_of,
)


@pytest.mark.usefixtures("client")
async def test_socket_without_auth_is_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A socket that never says who it is does not stay open."""
    monkeypatch.setattr(settings, "WS_AUTH_TIMEOUT_SECONDS", 0.2)

    async with hung_up_on() as ws:
        await ws.receive_json(timeout=5)


@pytest.mark.usefixtures("client")
async def test_socket_with_a_bad_token_is_closed() -> None:
    async with hung_up_on() as ws:
        await ws.send_json({"type": "auth", "token": "not-a-token"})
        await ws.receive_json(timeout=5)


async def test_authenticated_socket_is_told_it_is_ready(
    normal_user_token_headers: dict[str, str],
) -> None:
    async with open_socket() as ws:
        await ws.send_json(
            {"type": "auth", "token": token_of(normal_user_token_headers)}
        )

        frame = await ws.receive_json(timeout=5)

    assert frame["type"] == "ready"
    assert frame["protocol"] >= 1


async def test_unknown_message_type_is_refused_without_closing(
    normal_user_token_headers: dict[str, str],
) -> None:
    async with authenticated_socket(normal_user_token_headers) as ws:
        await ws.send_json({"type": "make-me-a-sandwich"})
        refusal = await ws.receive_json(timeout=5)

        # Still usable afterwards: a malformed frame is the client's mistake,
        # not a reason to drop everything else it is watching.
        await ws.send_json({"type": "subscribe", "topic": "no-such-topic"})
        second = await ws.receive_json(timeout=5)

    assert refusal["type"] == "error"
    assert refusal["code"] == "malformed"
    assert second["type"] == "error"


async def test_a_frame_with_an_extra_key_is_refused(
    normal_user_token_headers: dict[str, str],
) -> None:
    async with authenticated_socket(normal_user_token_headers) as ws:
        await ws.send_json({"type": "subscribe", "topic": "nope", "sudo": True})

        refusal = await ws.receive_json(timeout=5)

    assert refusal["type"] == "error"
    assert refusal["code"] == "malformed"


async def test_subscribing_to_an_unregistered_topic_is_refused(
    normal_user_token_headers: dict[str, str],
) -> None:
    async with authenticated_socket(normal_user_token_headers) as ws:
        await ws.send_json({"type": "subscribe", "topic": "no-such-topic"})

        refusal = await ws.receive_json(timeout=5)

    assert refusal["type"] == "error"
    assert refusal["code"] == "unknown_topic"


@pytest.mark.usefixtures("client")
async def test_a_frame_before_auth_is_refused() -> None:
    """Nothing is served until the socket has said who it is."""
    async with hung_up_on() as ws:
        await ws.send_json({"type": "subscribe", "topic": "no-such-topic"})
        await ws.receive_json(timeout=5)


async def test_a_second_auth_frame_is_refused(
    normal_user_token_headers: dict[str, str],
) -> None:
    """One socket, one identity.

    Re-authenticating would change who is watching without the topics being
    told, and they hold subscriptions keyed by user.
    """
    async with authenticated_socket(normal_user_token_headers) as ws:
        await ws.send_json(
            {"type": "auth", "token": token_of(normal_user_token_headers)}
        )

        refusal = await ws.receive_json(timeout=5)

    assert refusal["type"] == "error"
    assert refusal["code"] == "already_authenticated"
