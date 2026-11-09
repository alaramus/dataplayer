"""A node watched live through its own socket (D323).

The Binance source answers from the fake REST API and fake streams the
adapter tests use; this is the socket a screen opens, end to end.
"""

import uuid
from typing import Any

import pytest
from httpx import AsyncClient

from app.adapters.binance import live as binance_live
from app.core.config import settings
from tests.adapters.binance_fixture import FakeBinance, install
from tests.adapters.test_binance_live import FakeStreams
from tests.utils.socket import hung_up_on, open_socket, token_of

CONNECTORS = f"{settings.API_V1_STR}/connectors"
WATCH = "/watch"


@pytest.fixture
def fake_binance(monkeypatch: pytest.MonkeyPatch) -> FakeBinance:
    return install(monkeypatch)


@pytest.fixture
def streams(monkeypatch: pytest.MonkeyPatch) -> FakeStreams:
    fake = FakeStreams()
    monkeypatch.setattr(binance_live, "connect", fake.connect)
    return fake


async def _binance(client: AsyncClient, headers: dict[str, str]) -> str:
    created = await client.post(
        f"{CONNECTORS}/",
        headers=headers,
        json={
            "name": f"binance {uuid.uuid4().hex[:8]}",
            "adapter_type": "binance",
            "options": {"endpoint": "binance"},
        },
    )
    assert created.status_code == 200, created.text
    return str(created.json()["id"])


def _opening(headers: dict[str, str], connector: str, node: str) -> dict[str, Any]:
    return {
        "type": "open",
        "token": token_of(headers),
        "connector_id": connector,
        "node_id": node,
        "interval": "1h",
    }


async def _refused(frame: dict[str, Any]) -> dict[str, Any]:
    async with hung_up_on(WATCH) as ws:
        await ws.send_json(frame)
        answer: dict[str, Any] = await ws.receive_json(timeout=15)
        await ws.receive_json(timeout=5)
    return answer


async def test_a_symbols_market_is_said_as_it_stands_then_as_it_changes(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    fake_binance: FakeBinance,
    streams: FakeStreams,
) -> None:
    del fake_binance
    connector = await _binance(client, normal_user_token_headers)
    node = "spot:symbol:BTCUSDT:market"

    async with open_socket(WATCH) as ws:
        await ws.send_json(_opening(normal_user_token_headers, connector, node))
        ready = await ws.receive_json(timeout=15)
        parts = [(await ws.receive_json(timeout=15))["part"] for _ in range(4)]
        (url,) = await streams.opened(1)
        streams.tell(
            url,
            {
                "stream": "btcusdt@depth20",
                "data": {"bids": [["99", "2"]], "asks": [["101", "3"]]},
            },
        )
        live = await ws.receive_json(timeout=15)

    assert ready["type"] == "ready"
    assert ready["interval"] == "1h"
    assert "1s" in ready["intervals"]
    assert parts == ["ticker", "candles", "order_book", "trades"]
    assert live["type"] == "rows"
    assert live["part"] == "order_book"
    assert live["mode"] == "replace"


async def test_a_node_that_is_not_watched_is_refused_in_words(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    fake_binance: FakeBinance,
) -> None:
    del fake_binance
    connector = await _binance(client, normal_user_token_headers)

    trades = await _refused(
        _opening(normal_user_token_headers, connector, "spot:symbol:BTCUSDT:trades")
    )
    missing = await _refused(
        _opening(normal_user_token_headers, connector, "spot:symbol:NOPE:market")
    )

    assert trades["code"] == "unsupported"
    assert missing["code"] == "not_found"


@pytest.mark.usefixtures("client")
async def test_a_token_that_is_nobodys_is_refused() -> None:
    frame = await _refused(
        {
            "type": "open",
            "token": "nobody",
            "connector_id": str(uuid.uuid4()),
            "node_id": "spot:symbol:BTCUSDT:market",
        }
    )

    assert frame["code"] == "unauthenticated"


async def test_a_source_that_is_not_watched_live_is_refused(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    created = await client.post(
        f"{CONNECTORS}/",
        headers=normal_user_token_headers,
        json={
            "name": f"redis {uuid.uuid4().hex[:8]}",
            "adapter_type": "redis",
            "options": {"auth_method": "no_auth", "host": "redis.invalid"},
        },
    )
    assert created.status_code == 200, created.text

    frame = await _refused(
        _opening(normal_user_token_headers, created.json()["id"], "/")
    )

    assert frame["code"] == "unsupported"
