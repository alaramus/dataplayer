"""OKX's trades and candles read on by a link, against a fake OKX (D434)."""

import pytest

from app.adapters.okx.adapter import OkxAdapter
from app.adapters.okx.options import OkxMain
from app.adapters.okx.session import OkxSession
from app.adapters.reading_on import Bookmark
from tests.adapters.okx_fixture import CANDLES, HOUR_MS, TRADES, FakeOkx, install

TRADES_NODE = "linear:symbol:BTC-USDT-SWAP:trades"
INVERSE_TRADES = "inverse:symbol:BTC-USD-SWAP:trades"
CANDLES_NODE = "spot:symbol:BTC-USDT:candles:1h"
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
def fake_okx(monkeypatch: pytest.MonkeyPatch) -> FakeOkx:
    return install(monkeypatch)


def _adapter(kept: Kept | None) -> OkxAdapter:
    return OkxAdapter(OkxSession(OkxMain(), None), kept)


def test_only_trades_and_candles_are_read_on() -> None:
    adapter = _adapter(Kept())

    assert adapter.reads_on(TRADES_NODE)
    assert adapter.reads_on(CANDLES_NODE)
    assert not adapter.reads_on("spot:tickers")
    assert not adapter.reads_on("spot:symbol:BTC-USDT:book")
    assert not adapter.reads_on("nonsense")


async def test_a_fresh_reader_of_trades_starts_now_or_an_hour_back(
    fake_okx: FakeOkx,
) -> None:
    adapter = _adapter(Kept())

    latest = await adapter.unread(TRADES_NODE, READER, "latest")
    earliest = await adapter.unread(TRADES_NODE, READER, "earliest")

    assert latest.fresh
    assert latest.count == 0
    assert latest.line.positions[""] == TRADES + 1
    # A trade a second: about the last 3,600.
    assert 3599 <= earliest.count <= 3601
    assert earliest.start.positions[""] == TRADES + 1 - earliest.count
    del fake_okx


async def test_trades_are_read_by_id_and_the_bookmark_moves(
    fake_okx: FakeOkx,
) -> None:
    kept = Kept()
    adapter = _adapter(kept)
    await kept.write(TRADES_NODE, READER, Bookmark(positions={"": TRADES - 4}))

    span = await adapter.unread(TRADES_NODE, READER, "latest")
    first = await adapter.read_on(
        TRADES_NODE, ["id", "quantity"], span.start, span.line, 3
    )
    second = await adapter.read_on(TRADES_NODE, ["id"], first.after, span.line, 3)
    await adapter.mark_read(TRADES_NODE, READER, second.after)

    assert span.count == 5
    assert span.lost == 0
    assert first.rows == [
        [str(TRADES - 4), "0.02"],
        [str(TRADES - 3), "0.02"],
        [str(TRADES - 2), "0.02"],
    ]
    assert not first.done
    assert second.rows == [[str(TRADES - 1)], [str(TRADES)]]
    assert second.done
    assert kept.rows[(TRADES_NODE, READER)].positions[""] == TRADES + 1
    fake_okx.add_trades(2)
    again = await adapter.unread(TRADES_NODE, READER, "latest")
    assert again.count == 2


async def test_an_inverse_trade_is_read_as_what_it_is_worth(
    fake_okx: FakeOkx,
) -> None:
    adapter = _adapter(Kept())
    at = Bookmark(positions={"": TRADES})
    line = Bookmark(positions={"": TRADES + 1})

    block = await adapter.read_on(
        INVERSE_TRADES, ["id", "quote_quantity"], at, line, 10
    )

    assert block.rows == [[str(TRADES), "200"]]
    del fake_okx


async def test_trades_older_than_okx_keeps_are_counted_lost_exactly(
    fake_okx: FakeOkx,
) -> None:
    # A trade every half hour: five thousand of them reach past three months.
    fake_okx.spacing_ms = 30 * 60_000
    fake_okx.first_trade = 1
    kept = Kept()
    adapter = _adapter(kept)
    await kept.write(TRADES_NODE, READER, Bookmark(positions={"": 100}))

    span = await adapter.unread(TRADES_NODE, READER, "latest")

    oldest = span.start.positions[""]
    assert oldest > fake_okx.kept_from
    assert span.lost == oldest - 100
    assert span.count == TRADES + 1 - oldest


async def test_a_fresh_reader_of_candles_starts_at_the_last_closed_or_a_day_back(
    fake_okx: FakeOkx,
) -> None:
    adapter = _adapter(Kept())

    latest = await adapter.unread(CANDLES_NODE, READER, "latest")
    earliest = await adapter.unread(CANDLES_NODE, READER, "earliest")

    still_open = fake_okx.first_open_ms + (CANDLES - 1) * HOUR_MS
    assert latest.line.positions[""] == still_open
    assert latest.count == 0
    assert 23 <= earliest.count <= 24
    assert earliest.start.positions[""] == still_open - earliest.count * HOUR_MS


async def test_candles_are_read_in_blocks_up_to_the_open_one(
    fake_okx: FakeOkx,
) -> None:
    kept = Kept()
    adapter = _adapter(kept)
    still_open = fake_okx.first_open_ms + (CANDLES - 1) * HOUR_MS
    await kept.write(
        CANDLES_NODE, READER, Bookmark(positions={"": still_open - 5 * HOUR_MS})
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
    assert not first.done
    assert len(second.rows) == 2
    assert second.done
    assert second.after.positions[""] == still_open


def test_a_trade_is_keyed_by_its_id_and_a_candle_by_its_open() -> None:
    adapter = _adapter(Kept())

    assert adapter.row_key(TRADES_NODE) == ["id"]
    assert adapter.row_key(CANDLES_NODE) == ["open_time"]
