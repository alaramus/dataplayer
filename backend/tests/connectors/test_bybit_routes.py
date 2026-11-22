"""A Bybit connection through the routes a screen calls (D426, D427).

The adapter is tested on its own in tests/adapters/test_bybit.py; this is
the same fake Bybit reached the way the catalog and the grid reach it.
"""

import uuid
from typing import Any

import pytest
from httpx import AsyncClient

from app.core.config import settings
from tests.adapters.bybit_fixture import FakeBybit, install

BASE = f"{settings.API_V1_STR}/connectors"


@pytest.fixture
def fake_bybit(monkeypatch: pytest.MonkeyPatch) -> FakeBybit:
    return install(monkeypatch)


async def test_a_connection_is_checked_browsed_and_read(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    fake_bybit: FakeBybit,
) -> None:
    del fake_bybit
    headers = normal_user_token_headers
    response = await client.post(
        f"{BASE}/",
        headers=headers,
        json={
            "name": f"bybit {uuid.uuid4()}",
            "adapter_type": "bybit",
            "options": {"endpoint": "bybit"},
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
        "linear",
        "inverse",
    ]
    symbols = await call("GET", "catalog", params={"node_id": "linear:quote:USDT"})
    assert symbols[0]["kind"] == "symbol"
    assert symbols[0]["contract_type"] == "LinearPerpetual"

    page = await call("POST", "fetch", json={"node_id": "spot:tickers", "limit": 2})
    assert page["rows"][0][0] == "ETHUSDT"
    assert page["refresh_seconds"] == 10

    missing = await client.post(
        f"{BASE}/{connector}/fetch",
        headers=headers,
        json={"node_id": "spot:symbol:NOPEUSDT:trades"},
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
            "name": f"bybit {uuid.uuid4()}",
            "adapter_type": "bybit",
            "options": {"endpoint": "https://evil.example"},
        },
    )

    assert response.status_code == 422
