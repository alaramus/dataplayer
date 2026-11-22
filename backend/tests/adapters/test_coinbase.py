"""A Coinbase Exchange connection, its catalog, feeds and reports, against a
fake Coinbase (D438, D439, D442)."""

from datetime import UTC, datetime
from typing import Any

import pytest

from app.adapters.coinbase.adapter import CoinbaseAdapter
from app.adapters.coinbase.options import CoinbaseMain, CoinbaseSandbox
from app.adapters.coinbase.session import CoinbaseSession
from app.adapters.fetch import FetchRequest, ScalarFilter, Sort
from app.adapters.protocol import AdapterError, NodeNotFound
from app.adapters.registry import capabilities_of
from app.adapters.registry import get as get_adapter_type
from app.adapters.search import NodeSearchRequest, SearchBounds
from tests.adapters.coinbase_fixture import (
    CANDLES,
    HOUR_S,
    TRADES,
    FakeCoinbase,
    install,
)


@pytest.fixture
def fake_coinbase(monkeypatch: pytest.MonkeyPatch) -> FakeCoinbase:
    return install(monkeypatch)


def _adapter() -> CoinbaseAdapter:
    return CoinbaseAdapter(CoinbaseSession(CoinbaseMain(), None))


def _iso(seconds: int) -> str:
    at = datetime.fromtimestamp(seconds, tz=UTC)
    return at.isoformat(timespec="milliseconds").replace("+00:00", "Z")


async def _page(adapter: CoinbaseAdapter, node_id: str, **more: Any) -> Any:
    return await adapter.fetch(FetchRequest(node_id=node_id, **more))


# --- the connection (D438) ----------------------------------------------------------


async def test_a_check_asks_the_time(fake_coinbase: FakeCoinbase) -> None:
    result = await _adapter().check_connection()

    assert result.ok
    assert [one.path for one in fake_coinbase.asked] == ["/time"]
    assert fake_coinbase.asked[0].host == "api.exchange.coinbase.com"


async def test_the_sandbox_is_its_own_host(fake_coinbase: FakeCoinbase) -> None:
    await CoinbaseAdapter(CoinbaseSession(CoinbaseSandbox(), None)).check_connection()

    assert fake_coinbase.asked[0].host == "api-public.sandbox.exchange.coinbase.com"


async def test_a_rate_limit_refusal_holds_the_address(
    fake_coinbase: FakeCoinbase,
) -> None:
    fake_coinbase.refuse = (429, "Public rate limit exceeded")
    session = CoinbaseSession(CoinbaseMain(), None)
    async with session.kept() as kept:
        with pytest.raises(AdapterError) as first:
            await session._get(kept, session.markets[0], "/time", {}, "")  # noqa: SLF001 - the hold is the session's own
        fake_coinbase.refuse = None
        with pytest.raises(AdapterError) as held:
            await session._get(kept, session.markets[0], "/products", {}, "")  # noqa: SLF001

    assert "exceeded" not in first.value.message
    assert "s more" in held.value.message


async def test_the_clock_is_read_from_a_json_number(
    fake_coinbase: FakeCoinbase,
) -> None:
    server = await CoinbaseSession(CoinbaseMain(), None).server_time_ms(
        CoinbaseSession(CoinbaseMain(), None).markets[0]
    )

    assert server is not None
    assert abs(server - fake_coinbase.now_ms) <= 1


# --- the catalog and lists (D439) --------------------------------------------------


async def test_one_market_and_its_quote_assets(fake_coinbase: FakeCoinbase) -> None:
    del fake_coinbase
    adapter = _adapter()
    root = [node.id for node in await adapter.list_children(None)]
    spot = [node.id for node in await adapter.list_children("spot")]
    usd = [node.name for node in await adapter.list_children("spot:quote:USD")]

    assert root == ["exchange", "markets", "spot"]
    assert spot == ["spot:tickers", "spot:symbols", "spot:quote:USD", "spot:quote:BTC"]
    assert usd == ["BTC-USD", "ETH-USD"]
    with pytest.raises(NodeNotFound):
        await adapter.path_to("spot:symbol:GONE-USD")


async def test_tickers_have_no_quote_volume_and_are_busiest_by_volume(
    fake_coinbase: FakeCoinbase,
) -> None:
    page = await _page(_adapter(), "spot:tickers")
    names = [column.name for column in page.columns]

    assert "quote_volume" not in names
    assert page.rows[0][0] == "ETH-USD"
    eth = page.rows[0]
    assert eth[names.index("price_change")] == "1.5"
    assert eth[names.index("price_change_percent")] == "1.500"
    assert [one.path for one in fake_coinbase.asked].count("/products/stats") == 1


async def test_symbols_say_their_steps_and_minimum(fake_coinbase: FakeCoinbase) -> None:
    del fake_coinbase
    page = await _page(_adapter(), "spot:symbols")
    names = [column.name for column in page.columns]

    assert [row[0] for row in page.rows] == ["BTC-USD", "ETH-BTC", "ETH-USD"]
    assert page.rows[0][names.index("min_notional")] == "1"


# --- candles (D439) -----------------------------------------------------------------


async def test_candles_newest_first_their_numbers_as_written(
    fake_coinbase: FakeCoinbase,
) -> None:
    page = await _page(_adapter(), "spot:symbol:BTC-USD:candles:1h", limit=400)
    names = [column.name for column in page.columns]

    assert names == [
        "open_time",
        "close_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "closed",
    ]
    newest = fake_coinbase.first_open_s + (CANDLES - 1) * HOUR_S
    assert page.rows[0][0] == _iso(newest)
    assert page.rows[0][2:7] == [str(100 + CANDLES - 1), "1.1", "0.9", "1.0", "5.25"]
    assert page.rows[0][7] == "false"
    assert page.rows[1][7] == "true"
    assert len(page.rows) == 400
    opens = [row[0] for row in page.rows]
    assert opens == sorted(opens, reverse=True)
    assert len(set(opens)) == 400


async def test_candles_forwards_from_a_time(fake_coinbase: FakeCoinbase) -> None:
    start = fake_coinbase.first_open_s + 10 * HOUR_S
    page = await _page(
        _adapter(),
        "spot:symbol:BTC-USD:candles:1h",
        limit=350,
        filters=[ScalarFilter(column="open_time", op="gte", value=_iso(start))],
        sort=[Sort(column="open_time", descending=False)],
    )

    opens = [row[0] for row in page.rows]
    assert opens[0] == _iso(start)
    assert opens[-1] == _iso(start + 349 * HOUR_S)


# --- trades and the book (D439) -----------------------------------------------------


async def test_trades_newest_first_by_id_the_side_the_makers(
    fake_coinbase: FakeCoinbase,
) -> None:
    del fake_coinbase
    page = await _page(
        _adapter(), "spot:symbol:BTC-USD:trades", limit=1000, offset=500
    )
    names = [column.name for column in page.columns]

    assert names == ["id", "price", "quantity", "time", "buyer_is_maker"]
    assert [row[0] for row in page.rows[:2]] == [str(TRADES - 500), str(TRADES - 501)]
    assert len(page.rows) == 1000
    # An even trade's maker bought: its buyer was the maker.
    assert page.rows[0][4] == "true"
    assert page.rows[1][4] == "false"
    assert page.has_more


async def test_trades_from_the_first_ever(fake_coinbase: FakeCoinbase) -> None:
    del fake_coinbase
    page = await _page(
        _adapter(),
        "spot:symbol:BTC-USD:trades",
        limit=3,
        sort=[Sort(column="id", descending=False)],
    )

    assert [row[0] for row in page.rows] == ["1", "2", "3"]


async def test_a_trades_time_is_not_a_filter(fake_coinbase: FakeCoinbase) -> None:
    del fake_coinbase
    with pytest.raises(ValueError):
        await _page(
            _adapter(),
            "spot:symbol:BTC-USD:trades",
            filters=[ScalarFilter(column="time", op="gte", value=_iso(0))],
        )


async def test_the_book_is_cut_to_its_depth(fake_coinbase: FakeCoinbase) -> None:
    page = await _page(
        _adapter(),
        "spot:symbol:BTC-USD:book",
        filters=[ScalarFilter(column="level", op="lte", value="3")],
    )

    assert fake_coinbase.asked[-1].params == {"level": "2"}
    assert [row[0] for row in page.rows] == ["bid"] * 3 + ["ask"] * 3
    assert page.rows[2][4] == "4.5"


# --- reports, metrics, search (D442) -----------------------------------------------


async def test_the_exchange_section_says_one_budget(
    fake_coinbase: FakeCoinbase,
) -> None:
    del fake_coinbase
    adapter = _adapter()
    page = await adapter.fetch(FetchRequest(node_id="report:rate-limit"))
    rows = {str(row[0]): str(row[1]) for row in page.rows}

    assert rows["All markets: limit in 1 s"] == "10"
    assert rows["All markets: this connection stops at"] == "4"
    status = await adapter.fetch(FetchRequest(node_id="report:status"))
    said = {str(row[0]): str(row[1]) for row in status.rows}
    assert said["Endpoint"] == "Coinbase Exchange"
    assert said["Spot"] == "reached"


async def test_metrics_and_search(fake_coinbase: FakeCoinbase) -> None:
    del fake_coinbase
    adapter = _adapter()
    samples = await adapter.metric_samples()
    found = await adapter.search_nodes(
        NodeSearchRequest(query="eth", limit=10), SearchBounds.within(10)
    )

    assert {one.label for one in samples if one.metric == "weight"} == {"address"}
    assert found.matches[0].node.id == "spot:symbol:ETH-BTC"
    codes = {
        one.code
        for one in capabilities_of(get_adapter_type("coinbase"))
        if one.code is not None
    }
    assert {"search", "metrics"} <= codes
