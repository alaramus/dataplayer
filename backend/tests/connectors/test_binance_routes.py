"""A Binance connection through the routes a screen calls (D316–D318).

The adapter is tested on its own in tests/adapters/test_binance.py; this is
the same fake Binance reached the way the catalog and the grid reach it.
"""

import uuid
from typing import Any

import pytest
from httpx import AsyncClient

from app.core.config import settings
from tests.adapters.binance_fixture import API_KEY, API_SECRET, FakeBinance, install

BASE = f"{settings.API_V1_STR}/connectors"


@pytest.fixture
def fake_binance(monkeypatch: pytest.MonkeyPatch) -> FakeBinance:
    return install(monkeypatch)


async def test_a_connection_is_checked_browsed_and_read(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    fake_binance: FakeBinance,
) -> None:
    del fake_binance
    headers = normal_user_token_headers
    response = await client.post(
        f"{BASE}/",
        headers=headers,
        json={
            "name": f"binance {uuid.uuid4()}",
            "adapter_type": "binance",
            "options": {"endpoint": "binance"},
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
        "spot",
        "usdm",
        "coinm",
    ]
    symbols = await call("GET", "catalog", params={"node_id": "spot:quote:USDT"})
    assert symbols[0]["kind"] == "symbol"
    assert symbols[0]["base"] == "BTC"

    page = await call("POST", "fetch", json={"node_id": "spot:tickers", "limit": 2})
    assert page["columns"][0]["name"] == "symbol"
    assert page["rows"][0][0] == "ETHUSDT"
    assert page["refresh_seconds"] == 10

    path = await call(
        "GET", "catalog/path", params={"node_id": "spot:symbol:BTCUSDT:trades"}
    )
    assert [node["id"] for node in path][-1] == "spot:symbol:BTCUSDT:trades"

    missing = await client.post(
        f"{BASE}/{connector}/fetch",
        headers=headers,
        json={"node_id": "spot:symbol:NOPEUSDT:trades"},
    )
    assert missing.status_code == 404


async def test_the_options_refuse_an_endpoint_of_their_own(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = await client.post(
        f"{BASE}/",
        headers=normal_user_token_headers,
        json={
            "name": f"binance {uuid.uuid4()}",
            "adapter_type": "binance",
            "options": {"endpoint": "https://binance.example.com"},
        },
    )
    assert response.status_code == 422


async def test_a_key_is_kept_secret_and_opens_the_account(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    fake_binance: FakeBinance,
) -> None:
    """D322: the key and its secret are stored, never shown, and read with."""
    headers = normal_user_token_headers
    response = await client.post(
        f"{BASE}/",
        headers=headers,
        json={
            "name": f"binance key {uuid.uuid4()}",
            "adapter_type": "binance",
            "options": {
                "endpoint": "binance_key",
                "api_key": API_KEY,
                "api_secret": API_SECRET,
            },
        },
    )
    assert response.status_code == 200, response.text
    assert API_KEY not in response.text and API_SECRET not in response.text
    connector = response.json()["id"]

    listed = await client.get(f"{BASE}/{connector}", headers=headers)
    assert API_SECRET not in listed.text and API_KEY not in listed.text

    checked = await client.post(f"{BASE}/{connector}/check", headers=headers, json={})
    assert checked.json()["ok"], checked.text
    market = await client.get(
        f"{BASE}/{connector}/catalog", headers=headers, params={"node_id": "spot"}
    )
    assert "spot:account" in [node["id"] for node in market.json()]
    page = await client.post(
        f"{BASE}/{connector}/fetch",
        headers=headers,
        json={"node_id": "spot:account:balances"},
    )
    assert page.status_code == 200, page.text
    assert fake_binance.signed
