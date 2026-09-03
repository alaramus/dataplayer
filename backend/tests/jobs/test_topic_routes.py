"""What somebody watching a job is told, over the socket they already have.

The row stays the authority (D81), so this is about the courtesy arriving: a
person who asked for a service and did nothing else sees it move.
"""

from collections.abc import AsyncGenerator
from typing import Any

import pytest
from httpx import AsyncClient
from httpx_ws import AsyncWebSocketSession
from sqlmodel import delete

from app.core.config import settings
from app.core.db import async_session_maker
from app.jobs.models import Job
from app.jobs.topic import NAME as TOPIC
from app.main import app
from app.services.models import ManagedService
from tests.utils.service_engine import FakeEngine, engine_of
from tests.utils.socket import authenticated_socket

BASE = f"{settings.API_V1_STR}/services"


@pytest.fixture(autouse=True)
async def without_services() -> AsyncGenerator[None]:
    async with async_session_maker() as session:
        await session.exec(delete(Job))
        await session.exec(delete(ManagedService))
        await session.commit()
    yield


async def _event_on(ws: AsyncWebSocketSession) -> dict[str, Any]:
    while True:
        frame = await ws.receive_json(timeout=5)
        assert frame["type"] == "event", frame
        if frame["topic"] == TOPIC:
            payload: dict[str, Any] = frame["payload"]
            return payload


@pytest.mark.usefixtures("client")
async def test_the_owner_watches_their_service_job_without_asking_again(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """The whole sequence: it starts, it names each step, and it ends with a
    sentence — without the client asking anything after the first request."""
    with engine_of(app, FakeEngine()):
        async with authenticated_socket(normal_user_token_headers) as ws:
            await ws.send_json({"type": "subscribe", "topic": TOPIC})

            accepted = await client.post(
                f"{BASE}/",
                headers=normal_user_token_headers,
                json={"template_key": "postgres"},
            )
            assert accepted.status_code == 200, accepted.text

            seen: list[dict[str, Any]] = []
            while not seen or seen[-1]["state"] not in {"succeeded", "failed"}:
                seen.append(await _event_on(ws))

    assert {event["job_id"] for event in seen} == {accepted.json()["job"]["id"]}
    assert seen[0]["state"] == "running"
    assert seen[-1]["state"] == "succeeded"
    # The steps are named, so what a person watches is a place in a list the
    # server declared rather than a number nobody can check.
    # No "clearing an earlier attempt": there was none, and a step that did
    # not happen is not announced.
    assert [event["step"] for event in seen] == [
        None,
        "pulling the image",
        "creating the container",
        "starting the container",
        "waiting for it to answer",
        "saving the connection",
        "saving the connection",
    ]
    assert seen[-1]["message"] == "PostgreSQL is ready"
