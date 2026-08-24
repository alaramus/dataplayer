"""Availability of a user's connections, pushed while someone is watching.

The tests drive the real socket rather than the topic object: what matters is
that a screen which subscribes and does nothing else ends up knowing the state
of every connection it is allowed to see.

Timings are shortened through settings. The monitor reads them every cycle, so
patching them takes effect on a monitor that is already running.
"""

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import AsyncClient
from httpx_ws import AsyncWebSocketSession
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from tests.utils.database import working_postgres_options
from tests.utils.socket import authenticated_socket
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import random_email

BASE = f"{settings.API_V1_STR}/connectors"
TOPIC = "connector.health"


@pytest.fixture(autouse=True)
def _prompt_and_forgetful(monkeypatch: pytest.MonkeyPatch) -> None:
    """Probe often, and let the monitor die the moment the socket closes.

    Without the second half a monitor outlives its test and the next one reads
    its cache instead of doing the work — which would make the snapshot test
    pass for the wrong reason.
    """
    monkeypatch.setattr(settings, "HEALTH_INTERVAL_SECONDS", 0.3)
    monkeypatch.setattr(settings, "HEALTH_GRACE_SECONDS", 0.0)


@pytest.fixture
async def fresh_user_headers(
    client: AsyncClient, db: AsyncSession
) -> dict[str, str]:
    """A user who owns nothing yet.

    The shared test user accumulates connectors from every other file, most of
    them pointing nowhere, so a monitor watching them takes rounds long enough
    to drown any assertion about what was and was not probed.
    """
    return await authentication_token_from_email(
        client=client, email=random_email(), db=db
    )


async def _create_connector(
    client: AsyncClient,
    headers: dict[str, str],
    name: str,
    options: dict[str, Any] | None = None,
) -> str:
    response = await client.post(
        f"{BASE}/",
        headers=headers,
        json={
            "name": name,
            "adapter_type": "postgres",
            "options": options or working_postgres_options(),
        },
    )
    assert response.status_code == 200
    return str(response.json()["id"])


async def _watch(ws: AsyncWebSocketSession) -> None:
    await ws.send_json({"type": "subscribe", "topic": TOPIC})


async def _health_of(
    ws: AsyncWebSocketSession, connector_id: str, *, within: float = 10
) -> dict[str, Any]:
    """The next report about one connector.

    The user owns whatever earlier tests left behind, so reports about other
    connections arrive too and are skipped.
    """
    while True:
        frame: dict[str, Any] = await ws.receive_json(timeout=within)
        assert frame["type"] == "event", frame
        assert frame["topic"] == TOPIC
        if frame["payload"]["connector_id"] == connector_id:
            return frame["payload"]


async def _health_after(
    ws: AsyncWebSocketSession, connector_id: str, moment: datetime
) -> dict[str, Any]:
    """The first report about one connector made after a given instant.

    Reports queued before it are still in the buffer, so the newest one has to
    be looked for rather than simply read.
    """
    for _ in range(30):
        health = await _health_of(ws, connector_id, within=5)
        if datetime.fromisoformat(health["checked_at"]) >= moment:
            return health
    raise AssertionError("no report was made after that moment")


async def _reported_beside(
    ws: AsyncWebSocketSession, connector_id: str, *, rounds: int = 2
) -> set[str]:
    """Everything spoken about while one connector is reported a few times.

    Counting rounds rather than frames, and ending on a connector that is
    certainly probed: a fixed number of frames says nothing about whether a
    whole round has gone by. A round announces every due connector before the
    next one starts, so anything being probed at all appears in the first.
    """
    seen: set[str] = set()
    reports = 0
    while reports < rounds:
        frame: dict[str, Any] = await ws.receive_json(timeout=30)
        seen.add(frame["payload"]["connector_id"])
        if frame["payload"]["connector_id"] == connector_id:
            reports += 1
    return seen


async def test_a_watcher_is_told_a_working_connection_is_up(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _create_connector(
        client, normal_user_token_headers, f"health up {uuid.uuid4()}"
    )

    async with authenticated_socket(normal_user_token_headers) as ws:
        await _watch(ws)
        health = await _health_of(ws, connector_id)

    assert health["result"]["ok"] is True
    assert health["result"]["latency_ms"] >= 0
    assert health["checked_at"]


async def test_a_watcher_is_told_an_unreachable_connection_is_down(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    options = working_postgres_options() | {"password": "wrong-on-purpose"}
    connector_id = await _create_connector(
        client, normal_user_token_headers, f"health down {uuid.uuid4()}", options
    )

    async with authenticated_socket(normal_user_token_headers) as ws:
        await _watch(ws)
        health = await _health_of(ws, connector_id)

    assert health["result"]["ok"] is False
    assert health["result"]["error_kind"] == "auth"
    assert "wrong-on-purpose" not in str(health)


async def test_a_disabled_connection_is_never_probed(
    client: AsyncClient, fresh_user_headers: dict[str, str]
) -> None:
    """The point of switching a connection off is that the server stops
    touching it."""
    watched = await _create_connector(
        client, fresh_user_headers, f"health enabled {uuid.uuid4()}"
    )
    ignored = await _create_connector(
        client, fresh_user_headers, f"health disabled {uuid.uuid4()}"
    )
    await client.patch(
        f"{BASE}/{ignored}", headers=fresh_user_headers, json={"enabled": False}
    )

    async with authenticated_socket(fresh_user_headers) as ws:
        await _watch(ws)
        seen = await _reported_beside(ws, watched)

    # The enabled one has to be in there, or the test proves nothing: a socket
    # that reported nobody would satisfy the second assertion on its own.
    assert watched in seen
    assert ignored not in seen


async def test_a_second_socket_is_told_what_is_already_known(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """A second tab colours in at once and costs nobody a connection."""
    connector_id = await _create_connector(
        client, normal_user_token_headers, f"health snapshot {uuid.uuid4()}"
    )

    async with authenticated_socket(normal_user_token_headers) as first:
        await _watch(first)
        await _health_of(first, connector_id)

        # Far longer than the second socket is given below, so an answer that
        # fast cannot have come from a fresh probe.
        settings.HEALTH_INTERVAL_SECONDS = 30.0
        async with authenticated_socket(normal_user_token_headers) as second:
            await _watch(second)
            health = await _health_of(second, connector_id, within=3)

    assert health["connector_id"] == connector_id
    assert health["result"]["ok"] is True


async def test_a_watcher_hears_nothing_about_someone_elses_connection(
    client: AsyncClient,
    fresh_user_headers: dict[str, str],
    normal_user_token_headers: dict[str, str],
) -> None:
    theirs = await _create_connector(
        client, normal_user_token_headers, f"health foreign {uuid.uuid4()}"
    )
    mine = await _create_connector(
        client, fresh_user_headers, f"health mine {uuid.uuid4()}"
    )

    async with authenticated_socket(fresh_user_headers) as ws:
        await _watch(ws)
        seen = await _reported_beside(ws, mine)

    assert mine in seen
    assert theirs not in seen


async def test_pressing_check_reaches_every_watcher(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """The button and the dot cannot say different things.

    With the monitor put to sleep for far longer than the wait below, a report
    that arrives at all can only have come from the manual check.
    """
    connector_id = await _create_connector(
        client, normal_user_token_headers, f"health manual {uuid.uuid4()}"
    )

    async with authenticated_socket(normal_user_token_headers) as ws:
        await _watch(ws)
        await _health_of(ws, connector_id)

        settings.HEALTH_INTERVAL_SECONDS = 30.0
        # Let a round that was already in flight finish before the clock below
        # is read, so what arrives afterwards is not one of its reports.
        await asyncio.sleep(1)
        pressed_at = datetime.now(UTC)

        response = await client.post(
            f"{BASE}/{connector_id}/check", headers=normal_user_token_headers
        )
        health = await _health_after(ws, connector_id, pressed_at)

    assert response.status_code == 200
    assert health["result"]["ok"] is True


async def test_a_connection_switched_back_on_is_reported_again(
    client: AsyncClient, fresh_user_headers: dict[str, str]
) -> None:
    """Switching off and on again is not a one-way door.

    What the monitor knew is dropped when a connection goes off, so if it were
    not picked up again the dot would stay blank for as long as the screen is
    open.
    """
    connector_id = await _create_connector(
        client, fresh_user_headers, f"health revived {uuid.uuid4()}"
    )

    async with authenticated_socket(fresh_user_headers) as ws:
        await _watch(ws)
        await _health_of(ws, connector_id)

        await client.patch(
            f"{BASE}/{connector_id}",
            headers=fresh_user_headers,
            json={"enabled": False},
        )
        await asyncio.sleep(1)
        switched_on_at = datetime.now(UTC)
        await client.patch(
            f"{BASE}/{connector_id}",
            headers=fresh_user_headers,
            json={"enabled": True},
        )

        health = await _health_after(ws, connector_id, switched_on_at)

    assert health["result"]["ok"] is True
