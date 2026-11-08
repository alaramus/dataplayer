"""The Binance source against a Binance answering from memory (D316–D318)."""

from datetime import UTC, datetime

import pytest

from app.adapters.binance.adapter import BinanceAdapter
from app.adapters.binance.catalog import place_of
from app.adapters.binance.markets import SPOT
from app.adapters.binance.options import BinanceMain, BinanceMarketData
from app.adapters.binance.session import BinanceSession
from app.adapters.export import ExportRequest
from app.adapters.fetch import FetchRequest, InFilter, ScalarFilter, Sort
from app.adapters.protocol import AdapterError, NodeNotFound
from tests.adapters.binance_fixture import (
    CANDLES,
    HOUR_MS,
    TRADES,
    FakeBinance,
    install,
)


@pytest.fixture
def fake_binance(monkeypatch: pytest.MonkeyPatch) -> FakeBinance:
    return install(monkeypatch)


def _adapter() -> BinanceAdapter:
    return BinanceAdapter(BinanceSession(BinanceMain(), None))


def _iso(milliseconds: int) -> str:
    at = datetime.fromtimestamp(milliseconds / 1000, tz=UTC)
    return at.isoformat(timespec="milliseconds").replace("+00:00", "Z")


async def _page(node_id: str, **kwargs: object) -> list[list[str | None]]:
    result = await _adapter().fetch(FetchRequest(node_id=node_id, **kwargs))  # type: ignore[arg-type]  # the page's own fields, passed through
    return result.rows


# --- the connection --------------------------------------------------------------


async def test_a_check_pings_both_markets(fake_binance: FakeBinance) -> None:
    result = await _adapter().check_connection()

    assert result.ok
    assert {(one.host, one.path) for one in fake_binance.asked} == {
        ("api.binance.com", "/api/v3/ping"),
        ("fapi.binance.com", "/fapi/v1/ping"),
    }


async def test_the_market_data_endpoint_asks_its_own_host(
    fake_binance: FakeBinance,
) -> None:
    adapter = BinanceAdapter(BinanceSession(BinanceMarketData(), None))

    await adapter.check_connection()

    assert fake_binance.asked[0].host == "data-api.binance.vision"


async def test_an_address_binance_does_not_serve_is_a_configuration_failure(
    fake_binance: FakeBinance,
) -> None:
    fake_binance.refuse = (
        451,
        {},
        {"code": 0, "msg": "Service unavailable from a restricted location"},
    )

    result = await _adapter().check_connection()

    assert not result.ok
    assert result.error_kind == "config"
    assert "restricted" not in result.message


# --- the rate limit ----------------------------------------------------------------


async def test_a_request_past_the_ceiling_is_not_sent(
    fake_binance: FakeBinance,
) -> None:
    session = BinanceSession(BinanceMain(), None)
    async with session.kept() as kept:
        state = kept.markets["spot"]
        state.used = 4790
        state.minute = int(datetime.now(UTC).timestamp() // 60)
        with pytest.raises(AdapterError) as refused:
            await session._get(kept, SPOT, "exchangeInfo", {}, "")  # noqa: SLF001 - the ceiling is the session's own

    assert "rate limit" in refused.value.message
    assert fake_binance.asked == []


async def test_the_weight_binance_reports_is_kept(fake_binance: FakeBinance) -> None:
    fake_binance.used = 1000
    session = BinanceSession(BinanceMain(), None)
    async with session.kept() as kept:
        await session._get(kept, SPOT, "ping", {}, "")  # noqa: SLF001 - the count is the session's own

        assert kept.markets["spot"].used == 1001
        assert kept.markets["usdm"].used == 0


async def test_a_ban_holds_the_market_until_its_time(fake_binance: FakeBinance) -> None:
    fake_binance.refuse = (
        429,
        {"retry-after": "30"},
        {"code": -1003, "msg": "Too many"},
    )
    session = BinanceSession(BinanceMain(), None)
    async with session.kept() as kept:
        with pytest.raises(AdapterError):
            await session._get(kept, SPOT, "ping", {}, "")  # noqa: SLF001 - the ban is the session's own
        fake_binance.refuse = None
        with pytest.raises(AdapterError) as held:
            await session._get(kept, SPOT, "ping", {}, "")  # noqa: SLF001

    assert "s more" in held.value.message
    assert len(fake_binance.asked) == 1


# --- the catalog (D317) -------------------------------------------------------------


async def test_the_top_is_the_exchange_section_and_the_two_markets(
    fake_binance: FakeBinance,
) -> None:
    del fake_binance
    nodes = await _adapter().list_children(None)

    assert [node.id for node in nodes] == ["exchange", "spot", "usdm"]


async def test_a_market_holds_its_lists_then_its_quotes_fullest_first(
    fake_binance: FakeBinance,
) -> None:
    del fake_binance
    nodes = await _adapter().list_children("spot")

    assert [node.id for node in nodes] == [
        "spot:tickers",
        "spot:symbols",
        "spot:quote:USDT",
        "spot:quote:BTC",
    ]
    assert nodes[0].kind == "feed"


async def test_a_quote_lists_its_trading_symbols_whatever_their_script(
    fake_binance: FakeBinance,
) -> None:
    del fake_binance
    nodes = await _adapter().list_children("spot:quote:USDT")

    assert [node.name for node in nodes] == ["BTCUSDT", "ETHUSDT", "币安人生USDT"]
    assert nodes[0].kind == "symbol"


async def test_futures_leave_out_a_contract_that_no_longer_trades(
    fake_binance: FakeBinance,
) -> None:
    del fake_binance
    nodes = await _adapter().list_children("usdm:quote:USDT")

    assert [node.name for node in nodes] == ["BTCUSDT", "BTCUSDT_261225"]


async def test_a_symbol_holds_its_candles_trades_and_book(
    fake_binance: FakeBinance,
) -> None:
    del fake_binance
    adapter = _adapter()
    children = await adapter.list_children("spot:symbol:BTCUSDT")
    candles = await adapter.list_children("spot:symbol:BTCUSDT:candles")
    futures = await adapter.list_children("usdm:symbol:BTCUSDT:candles")

    assert [node.id for node in children] == [
        "spot:symbol:BTCUSDT:candles",
        "spot:symbol:BTCUSDT:trades",
        "spot:symbol:BTCUSDT:book",
    ]
    assert candles[0].id == "spot:symbol:BTCUSDT:candles:1s"
    assert "usdm:symbol:BTCUSDT:candles:1s" not in {node.id for node in futures}


async def test_the_path_to_a_candle_series(fake_binance: FakeBinance) -> None:
    del fake_binance
    path = await _adapter().path_to("spot:symbol:ETHBTC:candles:1h")

    assert [node.id for node in path] == [
        "spot",
        "spot:quote:BTC",
        "spot:symbol:ETHBTC",
        "spot:symbol:ETHBTC:candles",
        "spot:symbol:ETHBTC:candles:1h",
    ]


async def test_a_symbol_the_market_does_not_trade_is_not_there(
    fake_binance: FakeBinance,
) -> None:
    adapter = _adapter()

    for node_id in (
        "spot:symbol:GONEUSDT",
        "spot:symbol:NOPE:trades",
        "spot:quote:XYZ",
    ):
        with pytest.raises(NodeNotFound):
            await adapter.list_children(node_id)
    # Looked up in the list; nothing was asked about the symbol itself.
    assert all(one.path.endswith("exchangeInfo") for one in fake_binance.asked)


@pytest.mark.parametrize(
    "node_id",
    [
        "margin",
        "spot:symbol",
        "spot:symbol:BTCUSDT:candles:2h:extra",
        "spot:symbol:BTCUSDT:candles:7m",
        "usdm:symbol:BTCUSDT:candles:1s",
        "spot:symbol:BTCUSDT:orders",
    ],
)
def test_an_id_naming_nothing_of_this_source_is_refused(node_id: str) -> None:
    with pytest.raises(ValueError):
        place_of(node_id)


# --- tickers and symbols (D318) --------------------------------------------------


async def test_tickers_are_the_trading_symbols_busiest_first(
    fake_binance: FakeBinance,
) -> None:
    del fake_binance
    rows = await _page("spot:tickers")

    assert [row[0] for row in rows][:1] == ["ETHUSDT"]
    assert "GONEUSDT" not in {row[0] for row in rows}
    # A decimal is the text Binance wrote, not a float's.
    assert rows[0][1] == "101.10000000"


async def test_tickers_filter_and_sort_by_any_column(fake_binance: FakeBinance) -> None:
    del fake_binance
    starting = await _page(
        "spot:tickers",
        filters=[ScalarFilter(column="symbol", op="starts_with", value="eth")],
        sort=[Sort(column="symbol")],
    )
    cheap = await _page(
        "spot:tickers",
        filters=[ScalarFilter(column="last_price", op="lt", value="101.5")],
    )
    listed = await _page(
        "spot:tickers",
        filters=[InFilter(column="symbol", op="in", values=["BTCUSDT", "ETHBTC"])],
    )

    assert [row[0] for row in starting] == ["ETHBTC", "ETHUSDT"]
    assert {row[0] for row in cheap} == {"BTCUSDT", "ETHUSDT"}
    assert {row[0] for row in listed} == {"BTCUSDT", "ETHBTC"}


async def test_a_ticker_number_filter_refuses_a_word(fake_binance: FakeBinance) -> None:
    del fake_binance
    with pytest.raises(ValueError):
        await _page(
            "spot:tickers",
            filters=[ScalarFilter(column="volume", op="gt", value="lots")],
        )


async def test_futures_symbols_say_their_contract_and_no_delivery_for_a_perpetual(
    fake_binance: FakeBinance,
) -> None:
    del fake_binance
    result = await _adapter().fetch(FetchRequest(node_id="usdm:symbols"))
    names = [column.name for column in result.columns]
    rows = {row[0]: row for row in result.rows}

    assert names[-3:] == ["contract_type", "delivery_time", "listed_time"]
    assert rows["BTCUSDT"][names.index("delivery_time")] is None
    assert rows["BTCUSDT_261225"][names.index("delivery_time")] is not None
    assert rows["BTCUSDT"][names.index("price_step")] == "0.10"


# --- candles ------------------------------------------------------------------------


async def test_candles_open_newest_first_and_the_open_one_is_not_closed(
    fake_binance: FakeBinance,
) -> None:
    rows = await _page("spot:symbol:BTCUSDT:candles:1h", limit=3)
    newest = fake_binance.first_open_ms + (CANDLES - 1) * HOUR_MS

    assert [row[0] for row in rows] == [
        _iso(newest),
        _iso(newest - HOUR_MS),
        _iso(newest - 2 * HOUR_MS),
    ]
    assert rows[0][-1] == "false"
    assert rows[1][-1] == "true"


async def test_a_deep_page_of_candles_is_read_a_request_at_a_time(
    fake_binance: FakeBinance,
) -> None:
    rows = await _page("spot:symbol:BTCUSDT:candles:1h", limit=2, offset=2500)
    newest = fake_binance.first_open_ms + (CANDLES - 1) * HOUR_MS
    klines = [one for one in fake_binance.asked if one.path.endswith("klines")]

    assert [row[0] for row in rows] == [
        _iso(newest - 2500 * HOUR_MS),
        _iso(newest - 2501 * HOUR_MS),
    ]
    assert len(klines) == 3


async def test_candles_ascending_start_from_a_time(fake_binance: FakeBinance) -> None:
    start = fake_binance.first_open_ms + 10 * HOUR_MS
    rows = await _page(
        "spot:symbol:BTCUSDT:candles:1h",
        limit=2,
        sort=[Sort(column="open_time")],
        filters=[ScalarFilter(column="open_time", op="gte", value=_iso(start))],
    )

    assert [row[0] for row in rows] == [_iso(start), _iso(start + HOUR_MS)]
    assert rows[0][2] == "110.00000000"


async def test_candles_stop_at_the_lower_time_when_newest_first(
    fake_binance: FakeBinance,
) -> None:
    newest = fake_binance.first_open_ms + (CANDLES - 1) * HOUR_MS
    rows = await _page(
        "spot:symbol:BTCUSDT:candles:1h",
        filters=[
            ScalarFilter(column="open_time", op="gt", value=_iso(newest - 3 * HOUR_MS))
        ],
    )

    assert len(rows) == 3


async def test_candles_are_not_read_deeper_than_the_ceiling(
    fake_binance: FakeBinance,
) -> None:
    with pytest.raises(ValueError):
        await _page("spot:symbol:BTCUSDT:candles:1h", offset=9950, limit=100)
    assert fake_binance.asked == [] or all(
        not one.path.endswith("klines") for one in fake_binance.asked
    )


async def test_candles_filter_only_on_their_open_time(
    fake_binance: FakeBinance,
) -> None:
    del fake_binance
    with pytest.raises(ValueError):
        await _page(
            "spot:symbol:BTCUSDT:candles:1h",
            filters=[ScalarFilter(column="close", op="gt", value="1")],
        )


# --- trades --------------------------------------------------------------------------


async def test_trades_open_newest_first_and_page_by_id(
    fake_binance: FakeBinance,
) -> None:
    del fake_binance
    first = await _page("spot:symbol:BTCUSDT:trades", limit=3)
    later = await _page("spot:symbol:BTCUSDT:trades", limit=3, offset=1500)

    assert [row[0] for row in first] == [str(TRADES), str(TRADES - 1), str(TRADES - 2)]
    assert [row[0] for row in later] == [
        str(TRADES - 1500),
        str(TRADES - 1501),
        str(TRADES - 1502),
    ]
    assert first[0][1] == f"{1000 + TRADES}.50000000"
    assert first[0][-1] == "true"


async def test_trades_ascending_start_from_the_oldest_kept(
    fake_binance: FakeBinance,
) -> None:
    del fake_binance
    rows = await _page("spot:symbol:BTCUSDT:trades", limit=2, sort=[Sort(column="id")])

    assert [row[0] for row in rows] == ["1", "2"]


async def test_futures_trades_ascending_start_inside_their_two_days(
    fake_binance: FakeBinance,
) -> None:
    rows = await _page("usdm:symbol:BTCUSDT:trades", limit=1, sort=[Sort(column="id")])
    first = int(rows[0][0] or 0)

    assert fake_binance.trade_ms(first) >= fake_binance.now_ms - 2 * 86_400_000
    assert fake_binance.trade_ms(first - 2) < fake_binance.now_ms - 2 * 86_400_000


async def test_futures_trades_older_than_two_days_are_refused_in_words(
    fake_binance: FakeBinance,
) -> None:
    del fake_binance
    with pytest.raises(ValueError) as refused:
        await _page(
            "usdm:symbol:BTCUSDT:trades",
            filters=[ScalarFilter(column="id", op="lte", value="10")],
        )

    assert "two days" in str(refused.value)


async def test_trades_are_bounded_by_id_and_by_time(fake_binance: FakeBinance) -> None:
    by_id = await _page(
        "spot:symbol:BTCUSDT:trades",
        filters=[
            ScalarFilter(column="id", op="gte", value="100"),
            ScalarFilter(column="id", op="lt", value="103"),
        ],
    )
    by_time = await _page(
        "spot:symbol:BTCUSDT:trades",
        sort=[Sort(column="id")],
        limit=2,
        filters=[
            ScalarFilter(
                column="time", op="gte", value=_iso(fake_binance.trade_ms(4000))
            )
        ],
    )

    assert [row[0] for row in by_id] == ["102", "101", "100"]
    assert [row[0] for row in by_time] == ["4000", "4001"]


# --- the order book -----------------------------------------------------------------


async def test_the_book_lists_bids_then_asks_with_their_running_totals(
    fake_binance: FakeBinance,
) -> None:
    rows = await _page(
        "spot:symbol:BTCUSDT:book",
        filters=[ScalarFilter(column="level", op="lte", value="3")],
    )
    depth = [one for one in fake_binance.asked if one.path.endswith("depth")][0]

    assert depth.params["limit"] == "5"
    assert rows == [
        ["bid", "1", "100.00", "1.5", "1.5"],
        ["bid", "2", "99.99", "1.5", "3.0"],
        ["bid", "3", "99.98", "1.5", "4.5"],
        ["ask", "1", "100.01", "2", "2"],
        ["ask", "2", "100.02", "2", "4"],
        ["ask", "3", "100.03", "2", "6"],
    ]


async def test_one_side_of_the_book(fake_binance: FakeBinance) -> None:
    del fake_binance
    rows = await _page(
        "usdm:symbol:BTCUSDT:book",
        filters=[ScalarFilter(column="side", op="eq", value="ask")],
        limit=1000,
    )

    assert {row[0] for row in rows} == {"ask"}
    assert len(rows) == 100


# --- export ---------------------------------------------------------------------------


async def test_candles_export_to_the_page_depth(fake_binance: FakeBinance) -> None:
    del fake_binance
    rows = [
        row
        async for batch in _adapter().export_rows(
            ExportRequest(
                node_id="spot:symbol:BTCUSDT:candles:1h", columns=["close", "open_time"]
            )
        )
        for row in batch.rows
    ]

    assert len(rows) == CANDLES
    assert rows[0][0] == "1.00000000"


async def test_tickers_export_every_trading_symbol(fake_binance: FakeBinance) -> None:
    del fake_binance
    rows = [
        row
        async for batch in _adapter().export_rows(
            ExportRequest(node_id="spot:tickers", columns=["symbol"])
        )
        for row in batch.rows
    ]

    assert sorted(row[0] or "" for row in rows) == sorted(
        ["BTCUSDT", "ETHUSDT", "币安人生USDT", "ETHBTC"]
    )
