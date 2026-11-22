"""Bybit's trades and candles read on by a link, against a fake Bybit (D428)."""

import pytest

from app.adapters.bybit.adapter import BybitAdapter
from app.adapters.bybit.options import BybitMain
from app.adapters.bybit.session import BybitSession
from app.adapters.reading_on import Bookmark
from tests.adapters.bybit_fixture import CANDLES, HOUR_MS, TRADES, FakeBybit, install

TRADES_NODE = "linear:symbol:BTCUSDT:trades"
SPOT_TRADES = "spot:symbol:BTCUSDT:trades"
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
def fake_bybit(monkeypatch: pytest.MonkeyPatch) -> FakeBybit:
    return install(monkeypatch)


def _adapter(kept: Kept | None) -> BybitAdapter:
    return BybitAdapter(BybitSession(BybitMain(), None), kept)


def test_only_trades_and_candles_are_read_on() -> None:
    adapter = _adapter(Kept())

    assert adapter.reads_on(TRADES_NODE)
    assert adapter.reads_on(CANDLES_NODE)
    assert not adapter.reads_on("spot:tickers")
    assert not adapter.reads_on("spot:symbol:BTCUSDT:book")
    assert not adapter.reads_on("nonsense")


async def test_a_fresh_reader_of_trades_starts_now_or_at_the_oldest_given(
    fake_bybit: FakeBybit,
) -> None:
    adapter = _adapter(Kept())

    latest = await adapter.unread(TRADES_NODE, READER, "latest")
    earliest = await adapter.unread(TRADES_NODE, READER, "earliest")

    newest = fake_bybit.trade_ms(TRADES)
    assert latest.fresh
    assert latest.count == 0
    assert latest.line.positions[""] == newest + 1
    assert earliest.start.positions[""] == fake_bybit.trade_ms(TRADES - 999)
    assert earliest.count == 1000


async def test_trades_are_read_by_time_and_the_bookmark_moves(
    fake_bybit: FakeBybit,
) -> None:
    kept = Kept()
    adapter = _adapter(kept)
    await kept.write(
        TRADES_NODE, READER, Bookmark(positions={"": fake_bybit.trade_ms(TRADES - 4)})
    )

    span = await adapter.unread(TRADES_NODE, READER, "latest")
    first = await adapter.read_on(
        TRADES_NODE, ["id", "price"], span.start, span.line, 3
    )
    second = await adapter.read_on(TRADES_NODE, ["id"], first.after, span.line, 3)
    await adapter.mark_read(TRADES_NODE, READER, second.after)

    assert span.count == 5
    assert span.lost == 0
    assert [row[0] for row in first.rows] == [
        f"uuid-{TRADES - 4}",
        f"uuid-{TRADES - 3}",
        f"uuid-{TRADES - 2}",
    ]
    assert not first.done
    assert [row[0] for row in second.rows] == [f"uuid-{TRADES - 1}", f"uuid-{TRADES}"]
    assert second.done
    assert kept.rows[(TRADES_NODE, READER)].positions[""] == span.line.positions[""]


async def test_trades_gone_from_bybits_newest_are_counted_lost(
    fake_bybit: FakeBybit,
) -> None:
    kept = Kept()
    # Spot answers sixty; a reader two hundred behind finds them gone.
    await kept.write(
        SPOT_TRADES,
        READER,
        Bookmark(positions={"": fake_bybit.trade_ms(TRADES - 200)}),
    )

    span = await _adapter(kept).unread(SPOT_TRADES, READER, "latest")

    assert span.lost == 1
    assert span.start.positions[""] == fake_bybit.trade_ms(TRADES - 59)
    assert span.count == 60


async def test_a_reader_up_to_date_has_nothing_to_read(fake_bybit: FakeBybit) -> None:
    kept = Kept()
    adapter = _adapter(kept)
    await kept.write(
        TRADES_NODE, READER, Bookmark(positions={"": fake_bybit.trade_ms(TRADES) + 1})
    )

    span = await adapter.unread(TRADES_NODE, READER, "latest")
    block = await adapter.read_on(TRADES_NODE, ["id"], span.start, span.line, 100)

    assert span.count == 0
    assert block.rows == []
    assert block.done


async def test_a_fresh_reader_of_candles_starts_a_day_back_and_stops_at_the_open_one(
    fake_bybit: FakeBybit,
) -> None:
    span = await _adapter(Kept()).unread(CANDLES_NODE, READER, "earliest")

    still_open = fake_bybit.first_open_ms + (CANDLES - 1) * HOUR_MS
    assert span.line.positions[""] == still_open
    assert span.count in {23, 24}


async def test_closed_candles_are_read_in_blocks(fake_bybit: FakeBybit) -> None:
    kept = Kept()
    adapter = _adapter(kept)
    newest_closed = fake_bybit.first_open_ms + (CANDLES - 2) * HOUR_MS
    await kept.write(
        CANDLES_NODE,
        READER,
        Bookmark(positions={"": newest_closed - 2 * HOUR_MS}),
    )

    span = await adapter.unread(CANDLES_NODE, READER, "latest")
    first = await adapter.read_on(
        CANDLES_NODE, ["open_time", "closed"], span.start, span.line, 2
    )
    second = await adapter.read_on(
        CANDLES_NODE, ["open_time"], first.after, span.line, 2
    )

    assert span.count == 3
    assert [row[1] for row in first.rows] == ["true", "true"]
    assert not first.done
    assert len(second.rows) == 1
    assert second.done


def test_a_trade_is_keyed_by_id_and_a_candle_by_its_open_time() -> None:
    adapter = _adapter(Kept())

    assert adapter.row_key(TRADES_NODE) == ["id"]
    assert adapter.row_key(CANDLES_NODE) == ["open_time"]


async def test_a_source_without_a_bookmark_store_refuses_to_read_on(
    fake_bybit: FakeBybit,
) -> None:
    del fake_bybit
    with pytest.raises(ValueError, match="reader's place"):
        await _adapter(None).unread(TRADES_NODE, READER, "latest")
