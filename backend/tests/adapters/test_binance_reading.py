"""Binance's trades and candles read on by a link, against a fake Binance (D319)."""

import pytest

from app.adapters.binance.adapter import BinanceAdapter
from app.adapters.binance.options import BinanceMain
from app.adapters.binance.session import BinanceSession
from app.adapters.reading_on import Bookmark
from tests.adapters.binance_fixture import (
    CANDLES,
    HOUR_MS,
    TRADES,
    FakeBinance,
    install,
)

TRADES_NODE = "spot:symbol:BTCUSDT:trades"
CANDLES_NODE = "spot:symbol:BTCUSDT:candles:1h"
READER = "dataplayer-link-1"


class Kept:
    """Bookmarks in memory, as the connection's table keeps them."""

    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], Bookmark] = {}

    async def read(self, node_id: str, reader: str) -> Bookmark | None:
        return self.rows.get((node_id, reader))

    async def write(self, node_id: str, reader: str, at: Bookmark) -> None:
        self.rows[(node_id, reader)] = at


@pytest.fixture
def fake_binance(monkeypatch: pytest.MonkeyPatch) -> FakeBinance:
    return install(monkeypatch)


def _adapter(kept: Kept | None) -> BinanceAdapter:
    return BinanceAdapter(BinanceSession(BinanceMain(), None), kept)


def test_only_trades_and_candles_are_read_on() -> None:
    adapter = _adapter(Kept())

    assert adapter.reads_on(TRADES_NODE)
    assert adapter.reads_on(CANDLES_NODE)
    assert not adapter.reads_on("spot:tickers")
    assert not adapter.reads_on("spot:symbol:BTCUSDT:book")
    assert not adapter.reads_on("spot:symbol:BTCUSDT:candles")
    assert not adapter.reads_on("nonsense")


async def test_a_fresh_reader_of_trades_starts_at_the_end_or_an_hour_back(
    fake_binance: FakeBinance,
) -> None:
    adapter = _adapter(Kept())

    latest = await adapter.unread(TRADES_NODE, READER, "latest")
    earliest = await adapter.unread(TRADES_NODE, READER, "earliest")
    hour_back = TRADES - 60

    assert latest.fresh
    assert latest.count == 0
    assert latest.line.positions[""] == TRADES + 1
    assert earliest.start.positions[""] in {hour_back, hour_back + 1}
    assert earliest.count == TRADES + 1 - earliest.start.positions[""]
    del fake_binance


async def test_trades_are_read_in_blocks_and_the_bookmark_moves(
    fake_binance: FakeBinance,
) -> None:
    del fake_binance
    kept = Kept()
    adapter = _adapter(kept)
    await kept.write(TRADES_NODE, READER, Bookmark(positions={"": TRADES - 4}))

    span = await adapter.unread(TRADES_NODE, READER, "latest")
    first = await adapter.read_on(
        TRADES_NODE, ["id", "price"], span.start, span.line, 3
    )
    rest = await adapter.read_on(
        TRADES_NODE, ["id", "price"], first.after, span.line, 3
    )
    await adapter.mark_read(TRADES_NODE, READER, rest.after)

    assert not span.fresh
    assert span.count == 5
    assert [row[0] for row in first.rows] == [
        str(TRADES - 4),
        str(TRADES - 3),
        str(TRADES - 2),
    ]
    assert not first.done
    assert [row[0] for row in rest.rows] == [str(TRADES - 1), str(TRADES)]
    assert rest.done
    assert first.rows[0][1] == f"{1000 + TRADES - 4}.50000000"
    assert kept.rows[(TRADES_NODE, READER)].positions[""] == TRADES + 1
    assert "time" in kept.rows[(TRADES_NODE, READER)].positions


async def test_nothing_new_is_an_empty_span(fake_binance: FakeBinance) -> None:
    del fake_binance
    kept = Kept()
    await kept.write(TRADES_NODE, READER, Bookmark(positions={"": TRADES + 1}))
    adapter = _adapter(kept)

    span = await adapter.unread(TRADES_NODE, READER, "earliest")
    block = await adapter.read_on(TRADES_NODE, ["id"], span.start, span.line, 100)

    assert span.count == 0
    assert block.rows == []
    assert block.done


async def test_futures_trades_past_their_window_are_counted_as_lost(
    fake_binance: FakeBinance,
) -> None:
    node = "usdm:symbol:BTCUSDT:trades"
    kept = Kept()
    old = fake_binance.trade_ms(10)
    await kept.write(node, READER, Bookmark(positions={"": 10, "time": old}))

    span = await _adapter(kept).unread(node, READER, "latest")
    begin = span.start.positions[""]

    assert span.lost == begin - 10
    assert fake_binance.trade_ms(begin) >= fake_binance.now_ms - 2 * 86_400_000


async def test_closed_candles_only_are_read_on(fake_binance: FakeBinance) -> None:
    kept = Kept()
    adapter = _adapter(kept)
    newest = fake_binance.first_open_ms + (CANDLES - 1) * HOUR_MS
    await kept.write(
        CANDLES_NODE, READER, Bookmark(positions={"": newest - 3 * HOUR_MS})
    )

    span = await adapter.unread(CANDLES_NODE, READER, "latest")
    block = await adapter.read_on(
        CANDLES_NODE, ["open_time", "closed"], span.start, span.line, 100
    )

    # The open candle is the line, not a row.
    assert span.line.positions[""] == newest
    assert span.count == 3
    assert len(block.rows) == 3
    assert {row[1] for row in block.rows} == {"true"}
    assert block.after.positions[""] == newest
    assert block.done


async def test_a_fresh_candle_reader_from_the_earliest_starts_a_day_back(
    fake_binance: FakeBinance,
) -> None:
    newest = fake_binance.first_open_ms + (CANDLES - 1) * HOUR_MS
    span = await _adapter(Kept()).unread(CANDLES_NODE, READER, "earliest")

    assert span.fresh
    assert span.count in {23, 24}
    assert span.line.positions[""] == newest


async def test_a_column_the_feed_has_not_is_refused(fake_binance: FakeBinance) -> None:
    del fake_binance
    adapter = _adapter(Kept())
    span = await adapter.unread(TRADES_NODE, READER, "earliest")

    with pytest.raises(ValueError):
        await adapter.read_on(TRADES_NODE, ["volume"], span.start, span.line, 10)


async def test_without_a_place_to_keep_bookmarks_nothing_is_read_on(
    fake_binance: FakeBinance,
) -> None:
    del fake_binance
    with pytest.raises(ValueError):
        await _adapter(None).unread(TRADES_NODE, READER, "latest")
