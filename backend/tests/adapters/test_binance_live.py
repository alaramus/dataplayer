"""A Binance symbol watched live, against a fake Binance and fake streams (D323)."""

import asyncio
import json
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from websockets.exceptions import InvalidStatus
from websockets.http11 import Response

from app.adapters.binance import live as binance_live
from app.adapters.binance.adapter import BinanceAdapter
from app.adapters.binance.live import MarketStream, stream_urls
from app.adapters.binance.markets import COINM, SPOT, USDM
from app.adapters.binance.options import BinanceMain
from app.adapters.binance.session import BinanceSession
from app.adapters.live import LiveRows
from app.adapters.protocol import AdapterError, NodeNotFound
from tests.adapters.binance_fixture import TRADES, FakeBinance, install


class FakeStreams:
    """Binance's streams: what each address says, and who connected."""

    def __init__(self) -> None:
        self.said: dict[str, asyncio.Queue[dict[str, Any]]] = {}
        self.connected: list[str] = []
        self.refuse: int | None = None
        self._changed = asyncio.Condition()

    def tell(self, url: str, *messages: dict[str, Any]) -> None:
        for message in messages:
            self.said[url].put_nowait(message)

    async def opened(self, count: int) -> list[str]:
        """The addresses connected to, once there are this many."""
        async with asyncio.timeout(5), self._changed:
            await self._changed.wait_for(lambda: len(self.said) >= count)
        return list(self.said)

    @asynccontextmanager
    async def connect(self, url: str, **_: Any) -> AsyncIterator[_Socket]:
        self.connected.append(url)
        if self.refuse is not None:
            raise InvalidStatus(Response(self.refuse, "refused", None))  # type: ignore[arg-type]  # the headers are not read
        async with self._changed:
            queue = self.said.setdefault(url, asyncio.Queue())
            self._changed.notify_all()
        yield _Socket(queue)


class _Socket:
    def __init__(self, said: asyncio.Queue[dict[str, Any]]) -> None:
        self._said = said

    def __aiter__(self) -> _Socket:
        return self

    async def __anext__(self) -> str:
        return json.dumps(await self._said.get())


@pytest.fixture
def fake_binance(monkeypatch: pytest.MonkeyPatch) -> FakeBinance:
    return install(monkeypatch)


@pytest.fixture
def streams(monkeypatch: pytest.MonkeyPatch) -> FakeStreams:
    fake = FakeStreams()
    monkeypatch.setattr(binance_live, "connect", fake.connect)
    return fake


def _adapter() -> BinanceAdapter:
    return BinanceAdapter(BinanceSession(BinanceMain(), None))


async def _take(stream: AsyncGenerator[LiveRows], count: int) -> list[LiveRows]:
    taken: list[LiveRows] = []
    async with asyncio.timeout(5):
        async for rows in stream:
            taken.append(rows)
            if len(taken) == count:
                break
    return taken


def _trade(trade_id: int) -> dict[str, Any]:
    return {
        "e": "aggTrade",
        "a": trade_id,
        "p": "100.5",
        "q": "0.1",
        "f": 1,
        "l": 1,
        "T": 1_794_000_000_000,
        "m": False,
    }


# --- where the streams are ------------------------------------------------------------


def test_spot_and_coin_m_take_one_socket_and_usd_m_two() -> None:
    spot = stream_urls("binance", SPOT, "BTCUSDT", "1m")
    usdm = stream_urls("binance", USDM, "BTCUSDT", "5m")
    coin = stream_urls("testnet", COINM, "BTCUSD_PERP", "1h")

    assert spot == [
        "wss://stream.binance.com:9443/stream?streams="
        "btcusdt@depth20/btcusdt@aggTrade/btcusdt@kline_1m/btcusdt@ticker"
    ]
    assert usdm == [
        "wss://fstream.binance.com/public/stream?streams=btcusdt@depth20@500ms",
        "wss://fstream.binance.com/market/stream?streams="
        "btcusdt@aggTrade/btcusdt@kline_5m/btcusdt@ticker",
    ]
    assert coin[0].startswith(
        "wss://dstream.binancefuture.com/stream?streams=btcusd_perp@"
    )


# --- what may be watched ---------------------------------------------------------------


async def test_only_a_symbols_market_at_an_interval_it_has_is_watched(
    fake_binance: FakeBinance,
) -> None:
    del fake_binance
    adapter = _adapter()

    start = await adapter.live_start("usdm:symbol:BTCUSDT:market", None)

    assert start.interval == "1m"
    assert "1s" not in start.intervals
    with pytest.raises(ValueError):
        await adapter.live_start("usdm:symbol:BTCUSDT:market", "1s")
    with pytest.raises(ValueError):
        await adapter.live_start("spot:symbol:BTCUSDT:trades", None)
    with pytest.raises(NodeNotFound):
        await adapter.live_start("spot:symbol:NOPE:market", None)


async def test_a_symbol_offers_its_market_first(fake_binance: FakeBinance) -> None:
    del fake_binance
    children = await _adapter().list_children("spot:symbol:BTCUSDT")

    assert children[0].id == "spot:symbol:BTCUSDT:market"
    assert [one.kind for one in children[0].representations] == ["market"]
    path = await _adapter().path_to("spot:symbol:BTCUSDT:candles:1h")
    assert [node.id for node in path][-2:] == [
        "spot:symbol:BTCUSDT:candles",
        "spot:symbol:BTCUSDT:candles:1h",
    ]


# --- the watch --------------------------------------------------------------------------


async def test_a_watch_says_the_symbol_as_it_stands_then_as_it_changes(
    fake_binance: FakeBinance, streams: FakeStreams
) -> None:
    del fake_binance
    watch = _adapter().live("spot:symbol:BTCUSDT:market", "1h")

    first = await _take(watch, 4)
    assert [(one.part, one.mode) for one in first] == [
        ("ticker", "replace"),
        ("candles", "replace"),
        ("order_book", "replace"),
        ("trades", "replace"),
    ]
    candles = first[1]
    assert candles.key == ["open_time"]
    assert len(candles.rows) == 300
    # Oldest first, as a chart draws them.
    assert candles.rows[0][0] is not None and candles.rows[-1][0] is not None
    assert candles.rows[0][0] < candles.rows[-1][0]
    assert first[3].rows[-1][0] == str(TRADES)

    (url,) = await streams.opened(1)
    streams.tell(
        url,
        # Already in the snapshot: not said twice.
        {"stream": "btcusdt@aggTrade", "data": _trade(TRADES)},
        {"stream": "btcusdt@aggTrade", "data": _trade(TRADES + 1)},
        {
            "stream": "btcusdt@kline_1h",
            "data": {
                "k": {
                    "t": 1_794_000_000_000,
                    "T": 1_794_003_599_999,
                    "o": "1",
                    "h": "2",
                    "l": "0.5",
                    "c": "1.5",
                    "v": "10",
                    "q": "15",
                    "n": 3,
                    "V": "4",
                    "Q": "6",
                }
            },
        },
        {
            "stream": "btcusdt@depth20",
            "data": {"lastUpdateId": 1, "bids": [["99", "2"]], "asks": [["101", "3"]]},
        },
    )
    after = await _take(watch, 3)
    await watch.aclose()

    assert [(one.part, one.mode) for one in after] == [
        ("trades", "append"),
        ("candles", "upsert"),
        ("order_book", "replace"),
    ]
    assert after[0].rows[0][0] == str(TRADES + 1)
    assert after[1].rows[0][2:6] == ["1", "2", "0.5", "1.5"]
    assert after[2].rows == [
        ["bid", "1", "99", "2", "2"],
        ["ask", "1", "101", "3", "3"],
    ]


async def test_futures_name_the_sides_of_their_book_otherwise(
    fake_binance: FakeBinance, streams: FakeStreams
) -> None:
    del fake_binance
    watch = _adapter().live("usdm:symbol:BTCUSDT:market", "1h")
    await _take(watch, 4)

    book = next(url for url in await streams.opened(2) if "/public/" in url)
    streams.tell(
        book,
        {
            "stream": "btcusdt@depth20@500ms",
            "data": {"e": "depthUpdate", "b": [["99", "2"]], "a": [["101", "3"]]},
        },
    )
    (rows,) = await _take(watch, 1)
    await watch.aclose()

    assert rows.part == "order_book"
    assert [row[0] for row in rows.rows] == ["bid", "ask"]


async def test_coin_m_counts_its_day_in_the_base_and_usd(
    fake_binance: FakeBinance, streams: FakeStreams
) -> None:
    del fake_binance
    watch = _adapter().live("coinm:symbol:BTCUSD_PERP:market", "1h")
    first = await _take(watch, 4)
    columns = first[0].columns

    (url,) = await streams.opened(1)
    streams.tell(
        url,
        {
            "stream": "btcusd_perp@ticker",
            "data": {
                "s": "BTCUSD_PERP",
                "c": "74000",
                "p": "-1",
                "P": "-0.1",
                "w": "74100",
                "o": "74001",
                "h": "75000",
                "l": "73000",
                "v": "1000",
                "q": "1.35",
                "n": 5,
                "O": 1,
                "C": 2,
            },
        },
    )
    (day,) = await _take(watch, 1)
    await watch.aclose()

    row = dict(zip(columns, day.rows[0], strict=True))
    assert row["volume"] == "1.35"
    # A thousand contracts of 100 USD.
    assert row["quote_volume"] == "100000"


async def test_a_stream_binance_refuses_ends_the_watch_in_words(
    fake_binance: FakeBinance, streams: FakeStreams
) -> None:
    del fake_binance
    streams.refuse = 451
    watch = _adapter().live("spot:symbol:BTCUSDT:market", "1h")
    await _take(watch, 4)

    with pytest.raises(AdapterError) as ended:
        await _take(watch, 1)
    await watch.aclose()
    assert ended.value.error_kind == "config"


# --- one stream, many watchers -----------------------------------------------------------


async def test_watchers_share_one_upstream_and_the_last_one_stops_it(
    streams: FakeStreams,
) -> None:
    forgotten: list[MarketStream] = []
    stream = MarketStream("wss://example/stream", on_idle=forgotten.append)
    first: asyncio.Queue[Any] = asyncio.Queue()
    second: asyncio.Queue[Any] = asyncio.Queue()

    async with stream.watched(first):
        async with stream.watched(second):
            (url,) = await streams.opened(1)
            streams.tell(url, {"stream": "x", "data": {}})
            async with asyncio.timeout(2):
                assert (await first.get())["stream"] == "x"
                assert (await second.get())["stream"] == "x"
        assert stream.task is not None
    assert stream.task is None
    assert forgotten == [stream]
    assert streams.connected == ["wss://example/stream"]
