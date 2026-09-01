"""That a console hears about its run without asking.

Through the real socket rather than the topic object: what matters is that
somebody who subscribes and does nothing else is told, and that the run route
would have said the same thing anyway (D64).
"""

import uuid
from typing import Any

from httpx import AsyncClient
from httpx_ws import AsyncWebSocketSession
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.queries.topic import NAME as TOPIC
from tests.utils.database import working_postgres_options
from tests.utils.socket import authenticated_socket
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import random_email

BASE = f"{settings.API_V1_STR}/queries"
CONNECTORS = f"{settings.API_V1_STR}/connectors"


async def _event_on(ws: AsyncWebSocketSession, *, within: float = 10) -> dict[str, Any]:
    """The next frame of this topic, whatever else is on the socket."""
    while True:
        frame: dict[str, Any] = await ws.receive_json(timeout=within)
        assert frame["type"] == "event", frame
        if frame["topic"] == TOPIC:
            payload: dict[str, Any] = frame["payload"]
            return payload


async def test_the_owner_is_told_how_their_run_is_going(
    client: AsyncClient, db: AsyncSession
) -> None:
    email = random_email()
    headers = await authentication_token_from_email(client=client, email=email, db=db)
    connector = await client.post(
        f"{CONNECTORS}/",
        headers=headers,
        json={
            "name": f"pg {uuid.uuid4()}",
            "adapter_type": "postgres",
            "options": working_postgres_options(),
        },
    )
    assert connector.status_code == 200, connector.text
    run_id = str(uuid.uuid4())

    async with authenticated_socket(headers) as ws:
        await ws.send_json({"type": "subscribe", "topic": TOPIC})

        started = await client.post(
            f"{BASE}/runs",
            headers=headers,
            json={
                "run_id": run_id,
                "connector_id": connector.json()["id"],
                "text": "select 1",
            },
        )
        assert started.status_code == 200, started.text

        seen: list[str] = []
        while "succeeded" not in seen:
            event = await _event_on(ws)
            assert event["run_id"] == run_id
            seen.append(event["status"])

        assert "running" in seen
        assert seen[-1] == "succeeded"

    settled = await client.get(f"{BASE}/runs/{run_id}", headers=headers)
    assert settled.json()["status"] == "succeeded"
