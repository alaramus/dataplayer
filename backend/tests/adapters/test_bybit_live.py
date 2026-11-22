"""A Bybit symbol watched live, against a fake Bybit and fake streams (D429)."""

import asyncio
import json
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from websockets.exceptions import InvalidStatus
from websockets.http11 import Response

from app.adapters.bybit.adapter import BybitAdapter
from app.adapters.bybit.live import stream_spec
from app.adapters.bybit.markets import BY_KEY
from app.adapters.bybit.options import BybitMain
from app.adapters.bybit.session import BybitSession
from app.adapters.live import LiveRows
from app.adapters.market import stream as market_stream
from app.adapters.protocol import AdapterError, NodeNotFound
from tests.adapters.bybit_fixture import TRADES, FakeBybit, install

NODE = "linear:symbol:BTCUSDT:market"
URL = "wss://stream.bybit.com/v5/public/linear"


class FakeStreams:
    """Bybit's public sockets: what each says, what each was told."""

    def __init__(self) -> None:
        self.said: dict[str, asyncio.Queue[dict[str, Any]]] = {}
        self.told: list[str] = []
        self.connected: list[str] = []
        self.refuse: int | None = None
        self._changed = asyncio.Condition()

    def tell(self, url: str, *messages: dict[str, Any]) -> None:
        for message in messages:
            self.said[url].put_nowait(message)

    async def opened(self, count: int) -> None:
        async with asyncio.timeout(5), self._changed:
            await self._changed.wait_for(lambda: len(self.said) >= count)

    @asynccontextmanager
    async def connect(self, url: str, **_: Any) -> AsyncIterator[_Socket]:
        self.connected.append(url)
        if self.refuse is not None:
            raise InvalidStatus(Response(self.refuse, "refused", None))  # type: ignore[arg-type]  # the headers are not read
        async with self._changed:
            queue = self.said.setdefault(url, asyncio.Queue())
            self._changed.notify_all()
        yield _Socket(queue, self.told)


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
def fake_bybit(monkeypatch: pytest.MonkeyPatch) -> FakeBybit:
    return install(monkeypatch)


@pytest.fixture
def streams(monkeypatch: pytest.MonkeyPatch) -> FakeStreams:
    fake = FakeStreams()
    monkeypatch.setattr(market_stream, "connect", fake.connect)
    return fake


def _adapter() -> BybitAdapter:
    return BybitAdapter(BybitSession(BybitMain(), None))


async def _take(stream: AsyncGenerator[LiveRows], count: int) -> list[LiveRows]:
    taken: list[LiveRows] = []
    async with asyncio.timeout(5):
        async for rows in stream:
            taken.append(rows)
            if len(taken) == count:
                break
    return taken


def test_one_socket_a_category_subscribed_to_the_four_topics() -> None:
    spec = stream_spec("bybit", BY_KEY["spot"], "BTCUSDT", "1h")

    assert spec.url == "wss://stream.bybit.com/v5/public/spot"
    assert json.loads(spec.greeting[0]) == {
        "op": "subscribe",
        "args": [
            "publicTrade.BTCUSDT",
            "orderbook.50.BTCUSDT",
            "kline.60.BTCUSDT",
            "tickers.BTCUSDT",
        ],
    }
    assert spec.ping == '{"op": "ping"}'
    assert stream_spec("testnet", BY_KEY["inverse"], "BTCUSD", "1d").url == (
        "wss://stream-testnet.bybit.com/v5/public/inverse"
    )


async def test_a_watch_offers_bybits_intervals(fake_bybit: FakeBybit) -> None:
    del fake_bybit
    start = await _adapter().live_start(NODE, None)

    assert start.interval == "1m"
    assert "1s" not in start.intervals
    assert "1M" in start.intervals


async def test_a_watch_of_an_unknown_symbol_is_refused(fake_bybit: FakeBybit) -> None:
    del fake_bybit
    with pytest.raises(NodeNotFound):
        await _adapter().live_start("linear:symbol:NOPE:market", None)


async def test_the_snapshot_then_what_the_streams_say(
    fake_bybit: FakeBybit, streams: FakeStreams
) -> None:
    watch = _adapter().live(NODE, "1h")
    try:
        first = await _take(watch, 4)
        await streams.opened(1)
        newest = fake_bybit.trade_ms(TRADES)
        streams.tell(
            URL,
            {"success": True, "op": "subscribe"},
            {
                "topic": "publicTrade.BTCUSDT",
                "type": "snapshot",
                "data": [
                    # Already in the snapshot: not said twice.
                    {
                        "T": newest,
                        "s": "BTCUSDT",
                        "S": "Buy",
                        "v": "0.01",
                        "p": "1.5",
                        "i": f"uuid-{TRADES}",
                    },
                    {
                        "T": newest + 5,
                        "s": "BTCUSDT",
                        "S": "Sell",
                        "v": "0.2",
                        "p": "2.5",
                        "i": "uuid-new",
                    },
                ],
            },
            {
                "topic": "orderbook.50.BTCUSDT",
                "type": "delta",
                "data": {"s": "BTCUSDT", "b": [["100.00", "0"]], "a": [["99.99", "3"]]},
            },
            {
                "topic": "tickers.BTCUSDT",
                "type": "delta",
                "data": {"symbol": "BTCUSDT", "lastPrice": "200"},
            },
        )
        rest = await _take(watch, 3)
    finally:
        await watch.aclose()

    assert [one.part for one in first] == ["ticker", "candles", "order_book", "trades"]
    assert len(first[3].rows) == 100
    assert first[1].key == ["open_time"]
    trades, book, ticker = rest
    assert trades.mode == "append"
    assert [row[0] for row in trades.rows] == ["uuid-new"]
    assert trades.rows[0][4] == "true"
    # The delta took the best bid away and put an ask below it.
    assert book.mode == "replace"
    assert book.rows[0][2] == "99.99"
    asks = [row for row in book.rows if row[0] == "ask"]
    assert asks[0][2] == "99.99"
    # A delta laid over the day the snapshot read.
    assert ticker.rows[0][1] == "200"
    assert ticker.rows[0][4] == "100"
    assert json.loads(streams.told[0])["op"] == "subscribe"


async def test_a_refused_address_ends_the_watch_in_words(
    fake_bybit: FakeBybit, streams: FakeStreams
) -> None:
    del fake_bybit
    streams.refuse = 403
    watch = _adapter().live(NODE, "1h")
    try:
        await _take(watch, 4)
        with pytest.raises(AdapterError) as refused:
            await _take(watch, 1)
    finally:
        await watch.aclose()

    assert refused.value.error_kind == "config"
