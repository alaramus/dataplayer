"""An OKX symbol watched live, against a fake OKX and fake streams (D435)."""

import asyncio
import json
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from websockets.exceptions import InvalidStatus
from websockets.http11 import Response

from app.adapters.live import LiveRows
from app.adapters.market import stream as market_stream
from app.adapters.okx.adapter import OkxAdapter
from app.adapters.okx.live import stream_specs
from app.adapters.okx.options import OkxMain
from app.adapters.okx.session import OkxSession
from app.adapters.protocol import AdapterError, NodeNotFound
from tests.adapters.okx_fixture import TRADES, FakeOkx, install

NODE = "linear:symbol:BTC-USDT-SWAP:market"
PUBLIC = "wss://ws.okx.com/ws/v5/public"
BUSINESS = "wss://ws.okx.com/ws/v5/business"

type Said = dict[str, Any] | str


class FakeStreams:
    """OKX's sockets: what each says, what each was told."""

    def __init__(self) -> None:
        self.said: dict[str, asyncio.Queue[Said]] = {}
        self.told: dict[str, list[str]] = {}
        self.refuse: int | None = None
        self._changed = asyncio.Condition()

    def tell(self, url: str, *messages: Said) -> None:
        for message in messages:
            self.said[url].put_nowait(message)

    async def opened(self, count: int) -> None:
        async with asyncio.timeout(5), self._changed:
            await self._changed.wait_for(lambda: len(self.said) >= count)

    @asynccontextmanager
    async def connect(self, url: str, **_: Any) -> AsyncIterator[_Socket]:
        if self.refuse is not None:
            raise InvalidStatus(Response(self.refuse, "refused", None))  # type: ignore[arg-type]  # the headers are not read
        async with self._changed:
            queue = self.said.setdefault(url, asyncio.Queue())
            self._changed.notify_all()
        yield _Socket(queue, self.told.setdefault(url, []))


class _Socket:
    def __init__(self, said: asyncio.Queue[Said], told: list[str]) -> None:
        self._said = said
        self._told = told

    async def send(self, message: str) -> None:
        self._told.append(message)

    def __aiter__(self) -> _Socket:
        return self

    async def __anext__(self) -> str:
        message = await self._said.get()
        return message if isinstance(message, str) else json.dumps(message)


@pytest.fixture
def fake_okx(monkeypatch: pytest.MonkeyPatch) -> FakeOkx:
    return install(monkeypatch)


@pytest.fixture
def streams(monkeypatch: pytest.MonkeyPatch) -> FakeStreams:
    fake = FakeStreams()
    monkeypatch.setattr(market_stream, "connect", fake.connect)
    return fake


def _adapter() -> OkxAdapter:
    return OkxAdapter(OkxSession(OkxMain(), None))


async def _take(stream: AsyncGenerator[LiveRows], count: int) -> list[LiveRows]:
    taken: list[LiveRows] = []
    async with asyncio.timeout(5):
        async for rows in stream:
            taken.append(rows)
            if len(taken) == count:
                break
    return taken


def test_two_sockets_the_book_and_day_on_one_candles_and_trades_on_the_other() -> None:
    public, business = stream_specs("okx", "BTC-USDT", "1d")

    assert public.url == PUBLIC
    assert json.loads(public.greeting[0]) == {
        "op": "subscribe",
        "args": [
            {"channel": "books", "instId": "BTC-USDT"},
            {"channel": "tickers", "instId": "BTC-USDT"},
        ],
    }
    assert business.url == BUSINESS
    assert [one["channel"] for one in json.loads(business.greeting[0])["args"]] == [
        "candle1Dutc",
        "trades-all",
    ]
    assert public.ping == "ping"
    assert public.pong == "pong"
    assert stream_specs("demo", "BTC-USDT", "1h")[0].url == (
        "wss://wspap.okx.com/ws/v5/public"
    )


async def test_a_watch_offers_okxs_intervals(fake_okx: FakeOkx) -> None:
    del fake_okx
    start = await _adapter().live_start(NODE, None)

    assert start.interval == "1m"
    assert "1s" in start.intervals
    assert "8h" not in start.intervals


async def test_a_watch_of_an_unknown_symbol_is_refused(fake_okx: FakeOkx) -> None:
    del fake_okx
    with pytest.raises(NodeNotFound):
        await _adapter().live_start("linear:symbol:NOPE-USDT-SWAP:market", None)


async def test_the_snapshot_then_what_the_streams_say(
    fake_okx: FakeOkx, streams: FakeStreams
) -> None:
    watch = _adapter().live(NODE, "1h")
    try:
        first = await _take(watch, 4)
        await streams.opened(2)
        streams.tell(
            PUBLIC,
            {"event": "subscribe", "arg": {"channel": "books"}},
            # A plain pong is skipped, not read as a broken message.
            "pong",
            {
                "arg": {"channel": "books", "instId": "BTC-USDT-SWAP"},
                "action": "update",
                "data": [
                    {
                        "bids": [["100.00", "0", "0", "0"]],
                        "asks": [["99.99", "3", "0", "1"]],
                    }
                ],
            },
        )
        book = (await _take(watch, 1))[0]
        streams.tell(
            PUBLIC,
            {
                "arg": {"channel": "tickers", "instId": "BTC-USDT-SWAP"},
                "data": [
                    {
                        "instId": "BTC-USDT-SWAP",
                        "last": "200",
                        "open24h": "100",
                        "high24h": "201",
                        "low24h": "99",
                        "vol24h": "10",
                        "volCcy24h": "0.1",
                    }
                ],
            },
        )
        ticker = (await _take(watch, 1))[0]
        streams.tell(
            BUSINESS,
            {
                "arg": {"channel": "trades-all", "instId": "BTC-USDT-SWAP"},
                "data": [
                    # Already in the snapshot: not said twice.
                    {
                        "tradeId": str(TRADES),
                        "px": "1",
                        "sz": "1",
                        "side": "buy",
                        "ts": "1",
                    },
                    {
                        "tradeId": str(TRADES + 1),
                        "px": "2.5",
                        "sz": "3",
                        "side": "sell",
                        "ts": str(fake_okx.now_ms),
                    },
                ],
            },
        )
        trades = (await _take(watch, 1))[0]
    finally:
        await watch.aclose()

    assert [one.part for one in first] == ["ticker", "candles", "order_book", "trades"]
    assert len(first[3].rows) == 100
    assert first[1].key == ["open_time"]
    # The update took the best bid away and put an ask below it, in BTC.
    assert book.mode == "replace"
    asks = [row for row in book.rows if row[0] == "ask"]
    assert asks[0][2:4] == ["99.99", "0.03"]
    assert ticker.rows[0][1] == "200"
    assert ticker.rows[0][7] == "0.1"
    assert trades.mode == "append"
    assert [row[0] for row in trades.rows] == [str(TRADES + 1)]
    # Three contracts of 0.01 BTC, sold by the taker.
    assert trades.rows[0][2] == "0.03"
    assert trades.rows[0][4] == "true"
    assert json.loads(streams.told[PUBLIC][0])["op"] == "subscribe"


async def test_a_refused_address_ends_the_watch_in_words(
    fake_okx: FakeOkx, streams: FakeStreams
) -> None:
    del fake_okx
    streams.refuse = 403
    watch = _adapter().live(NODE, "1h")
    try:
        await _take(watch, 4)
        with pytest.raises(AdapterError) as refused:
            await _take(watch, 1)
    finally:
        await watch.aclose()

    assert refused.value.error_kind == "config"
