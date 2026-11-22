"""An Coinbase connection through the routes a screen calls (D438, D439).

The adapter is tested on its own in tests/adapters/test_coinbase.py; this is
the same fake Coinbase reached the way the catalog and the grid reach it.
"""

import uuid
from typing import Any

import pytest
from httpx import AsyncClient

from app.core.config import settings
from tests.adapters.coinbase_fixture import FakeCoinbase, install

BASE = f"{settings.API_V1_STR}/connectors"


@pytest.fixture
def fake_coinbase(monkeypatch: pytest.MonkeyPatch) -> FakeCoinbase:
    return install(monkeypatch)


async def test_a_connection_is_checked_browsed_and_read(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    fake_coinbase: FakeCoinbase,
) -> None:
    del fake_coinbase
    headers = normal_user_token_headers
    response = await client.post(
        f"{BASE}/",
        headers=headers,
        json={
            "name": f"coinbase {uuid.uuid4()}",
            "adapter_type": "coinbase",
            "options": {"endpoint": "coinbase"},
        },
    )
    assert response.status_code == 200, response.text
    connector = response.json()["id"]

    async def call(method: str, path: str, **kwargs: Any) -> Any:
        response = await client.request(
            method, f"{BASE}/{connector}/{path}", headers=headers, **kwargs
        )
        assert response.status_code == 200, response.text
        return response.json()

    assert (await call("POST", "check", json={}))["ok"]
    assert [node["id"] for node in await call("GET", "catalog")] == [
        "exchange",
        "markets",
        "spot",
    ]
    symbols = await call("GET", "catalog", params={"node_id": "spot:quote:USD"})
    assert symbols[0]["kind"] == "symbol"
    assert symbols[0]["contract_type"] is None

    page = await call("POST", "fetch", json={"node_id": "spot:tickers", "limit": 2})
    assert page["rows"][0][0] == "ETH-USD"
    assert page["refresh_seconds"] == 10

    missing = await client.post(
        f"{BASE}/{connector}/fetch",
        headers=headers,
        json={"node_id": "spot:symbol:NOPE-USD:trades"},
    )
    assert missing.status_code == 404


async def test_the_options_refuse_an_endpoint_of_their_own(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    response = await client.post(
        f"{BASE}/",
        headers=normal_user_token_headers,
        json={
            "name": f"coinbase {uuid.uuid4()}",
            "adapter_type": "coinbase",
            "options": {"endpoint": "https://evil.example"},
        },
    )

    assert response.status_code == 422
