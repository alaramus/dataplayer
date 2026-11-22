"""A Coinbase product read on by a link and watched live, against a fake
Coinbase and a fake feed (D440, D441)."""

import asyncio
import json
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import pytest

from app.adapters.coinbase.adapter import CoinbaseAdapter
from app.adapters.coinbase.live import stream_spec
from app.adapters.coinbase.options import CoinbaseMain
from app.adapters.coinbase.session import CoinbaseSession
from app.adapters.live import LiveRows
from app.adapters.market import stream as market_stream
from app.adapters.reading_on import Bookmark
from tests.adapters.coinbase_fixture import TRADES, FakeCoinbase, install

NODE = "spot:symbol:BTC-USD:market"
TRADES_NODE = "spot:symbol:BTC-USD:trades"
CANDLES_NODE = "spot:symbol:BTC-USD:candles:1h"
FEED = "wss://ws-feed.exchange.coinbase.com"
READER = "dataplayer-link-1"


class Kept:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], Bookmark] = {}

    async def read(self, node_id: str, reader: str) -> Bookmark | None:
        return self.rows.get((node_id, reader))

    async def write(self, node_id: str, reader: str, at: Bookmark) -> None:
        self.rows[(node_id, reader)] = at


class FakeFeed:
    def __init__(self) -> None:
        self.said: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.told: list[str] = []
        self.opened = asyncio.Event()

    @asynccontextmanager
    async def connect(self, url: str, **_: Any) -> AsyncIterator[_Socket]:
        assert url == FEED
        self.opened.set()
        yield _Socket(self.said, self.told)


class _Socket:
    def __init__(self, said: asyncio.Queue[dict[str, Any]], told: list[str]) -> None:
        self._said = said
        self._told = told

    async def send(self, message: str) -> None:
        self._told.append(message)

    def __aiter__(self) -> _Socket:
        return self

    async def __anext__(self) -> str:
        return json.dumps(await self._said.get())


@pytest.fixture
def fake_coinbase(monkeypatch: pytest.MonkeyPatch) -> FakeCoinbase:
    return install(monkeypatch)


@pytest.fixture
def feed(monkeypatch: pytest.MonkeyPatch) -> FakeFeed:
    fake = FakeFeed()
    monkeypatch.setattr(market_stream, "connect", fake.connect)
    return fake


def _adapter(kept: Kept | None = None) -> CoinbaseAdapter:
    return CoinbaseAdapter(CoinbaseSession(CoinbaseMain(), None), kept)


async def _take(stream: AsyncGenerator[LiveRows], count: int) -> list[LiveRows]:
    taken: list[LiveRows] = []
    async with asyncio.timeout(5):
        async for rows in stream:
            taken.append(rows)
            if len(taken) == count:
                break
    return taken


# --- read on (D440) ------------------------------------------------------------------


async def test_trades_are_read_on_by_id_and_nothing_is_lost(
    fake_coinbase: FakeCoinbase,
) -> None:
    kept = Kept()
    adapter = _adapter(kept)
    # However far behind, every trade is still there.
    await kept.write(TRADES_NODE, READER, Bookmark(positions={"": 10}))

    span = await adapter.unread(TRADES_NODE, READER, "latest")
    block = await adapter.read_on(TRADES_NODE, ["id"], span.start, span.line, 3)
    fresh = await adapter.unread(TRADES_NODE, "another", "earliest")

    assert span.count == TRADES + 1 - 10
    assert span.lost == 0
    assert block.rows == [["10"], ["11"], ["12"]]
    assert block.after.positions[""] == 13
    assert fresh.count == 1000
    del fake_coinbase


async def test_candles_are_read_on_up_to_the_open_one(
    fake_coinbase: FakeCoinbase,
) -> None:
    kept = Kept()
    adapter = _adapter(kept)
    now = fake_coinbase.now_ms // 1000
    still_open = now - now % 3600
    await kept.write(
        CANDLES_NODE, READER, Bookmark(positions={"": (still_open - 5 * 3600) * 1000})
    )

    span = await adapter.unread(CANDLES_NODE, READER, "latest")
    first = await adapter.read_on(
        CANDLES_NODE, ["open_time", "closed"], span.start, span.line, 3
    )
    second = await adapter.read_on(
        CANDLES_NODE, ["open_time"], first.after, span.line, 3
    )

    assert span.count == 5
    assert len(first.rows) == 3
    assert all(row[1] == "true" for row in first.rows)
    assert len(second.rows) == 2
    assert second.done
    assert adapter.row_key(TRADES_NODE) == ["id"]


# --- live (D441) -----------------------------------------------------------------------


def test_one_socket_a_product_on_four_public_channels() -> None:
    spec = stream_spec("coinbase", "BTC-USD")

    assert spec.url == FEED
    assert json.loads(spec.greeting[0]) == {
        "type": "subscribe",
        "product_ids": ["BTC-USD"],
        "channels": ["matches", "level2_batch", "ticker", "heartbeat"],
    }


async def test_the_snapshot_then_the_feed_the_candle_kept_from_trades(
    fake_coinbase: FakeCoinbase, feed: FakeFeed
) -> None:
    watch = _adapter().live(NODE, "1h")
    try:
        first = await _take(watch, 4)
        async with asyncio.timeout(5):
            await feed.opened.wait()
        at = datetime.fromtimestamp(fake_coinbase.now_ms / 1000 + 1, tz=UTC)
        when = at.isoformat().replace("+00:00", "Z")
        feed.said.put_nowait({"type": "subscriptions", "channels": []})
        feed.said.put_nowait(
            # Already in the snapshot: not said twice.
            {
                "type": "match",
                "trade_id": TRADES,
                "side": "buy",
                "size": "1",
                "price": "1",
                "time": when,
            }
        )
        feed.said.put_nowait(
            {
                "type": "match",
                "trade_id": TRADES + 1,
                "side": "sell",
                "size": "0.5",
                "price": "2.5",
                "time": when,
            }
        )
        trades, candle = await _take(watch, 2)
        feed.said.put_nowait(
            {
                "type": "l2update",
                "product_id": "BTC-USD",
                "changes": [["buy", "100.00", "0"], ["sell", "99.99", "3"]],
            }
        )
        book = (await _take(watch, 1))[0]
        feed.said.put_nowait(
            {
                "type": "ticker",
                "price": "200",
                "open_24h": "100",
                "high_24h": "201",
                "low_24h": "99",
                "volume_24h": "12",
            }
        )
        ticker = (await _take(watch, 1))[0]
    finally:
        await watch.aclose()

    assert [one.part for one in first] == ["ticker", "candles", "order_book", "trades"]
    assert len(first[3].rows) == 100
    assert [row[0] for row in trades.rows] == [str(TRADES + 1)]
    assert trades.rows[0][4] == "false"
    # The newest candle of the snapshot, with the trade laid over it.
    assert candle.mode == "upsert"
    assert candle.rows[0][4] == "0.9"
    assert candle.rows[0][3] == "2.5"
    assert candle.rows[0][5] == "2.5"
    assert candle.rows[0][6] == "5.75"
    asks = [row for row in book.rows if row[0] == "ask"]
    assert asks[0][2:4] == ["99.99", "3"]
    assert ticker.rows[0][1] == "200"
    assert ticker.rows[0][7] == "12"
    assert json.loads(feed.told[0])["type"] == "subscribe"
