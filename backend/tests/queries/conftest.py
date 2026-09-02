"""What the query tests share.

One source that runs no SQL. Both real adapters now do — PostgreSQL by D62 and
the file source by D77 — so a test about "a source without this capability
answers 501" needs a source built for the purpose, and would otherwise quietly
stop testing anything the day the last capability-less adapter grew one.
"""

import uuid

import pytest
from httpx import AsyncClient
from pydantic import BaseModel

from app.adapters import registry
from app.adapters.protocol import ConnectionCheckResult

CONNECTORS = "/api/v1/connectors"


class _PingOptions(BaseModel):
    url: str


class _PingAdapter:
    """A source that can be reached and asked nothing else."""

    def __init__(self, options: _PingOptions, _context: registry.AdapterContext) -> None:
        self.options = options

    async def check_connection(self) -> ConnectionCheckResult:
        return ConnectionCheckResult(ok=True, message="pong", latency_ms=1)


@pytest.fixture
def silent_source(
    # A fixture asked for by name, so that the registry is put back afterwards;
    # ruff reads it as an unused argument, which is what a dependency looks
    # like to it.
    isolated_registry: None,  # noqa: ARG001
) -> type[_PingAdapter]:
    """Register a source with no capability at all, for this test only."""
    registry.register(
        name="ping",
        title="Ping",
        category="sql",
        description="A source that can only be reached.",
        options_schema=_PingOptions,
        adapter_class=_PingAdapter,
    )(_PingAdapter)
    return _PingAdapter


async def silent_connector(client: AsyncClient, headers: dict[str, str]) -> str:
    """A connector of that source, as its id."""
    response = await client.post(
        f"{CONNECTORS}/",
        headers=headers,
        json={
            "name": f"ping {uuid.uuid4()}",
            "adapter_type": "ping",
            "options": {"url": "https://example.com"},
        },
    )
    assert response.status_code == 200, response.text
    return str(response.json()["id"])
