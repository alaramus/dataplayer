"""A Bybit connection, its catalog and its feeds, against a fake Bybit (D426, D427)."""

import uuid
from datetime import UTC, datetime

import pytest

from app.adapters.bybit.adapter import BybitAdapter
from app.adapters.bybit.feeds import close_ms, percent_of
from app.adapters.bybit.options import BybitBytick, BybitMain, BybitTestnet
from app.adapters.bybit.session import BybitSession
from app.adapters.export import ExportRequest
from app.adapters.fetch import FetchRequest, ScalarFilter, Sort
from app.adapters.protocol import AdapterError, NodeNotFound
from app.adapters.resources import Pooling, ResourceStore
from tests.adapters.bybit_fixture import (
    CANDLES,
    HOUR_MS,
    TRADES,
    FakeBybit,
    install,
)


@pytest.fixture
def fake_bybit(monkeypatch: pytest.MonkeyPatch) -> FakeBybit:
    return install(monkeypatch)


def _adapter() -> BybitAdapter:
    return BybitAdapter(BybitSession(BybitMain(), None))


def _iso(milliseconds: int) -> str:
    at = datetime.fromtimestamp(milliseconds / 1000, tz=UTC)
    return at.isoformat(timespec="milliseconds").replace("+00:00", "Z")


# --- the connection (D426) ----------------------------------------------------------


async def test_a_check_asks_every_market_for_the_time(fake_bybit: FakeBybit) -> None:
    result = await _adapter().check_connection()

    assert result.ok
    assert [one.path for one in fake_bybit.asked] == ["/v5/market/time"] * 3
    assert {one.host for one in fake_bybit.asked} == {"api.bybit.com"}


@pytest.mark.parametrize(
    ("options", "host"),
    [(BybitBytick(), "api.bytick.com"), (BybitTestnet(), "api-testnet.bybit.com")],
)
async def test_each_endpoint_is_its_own_host(
    fake_bybit: FakeBybit, options: BybitBytick | BybitTestnet, host: str
) -> None:
    await BybitAdapter(BybitSession(options, None)).check_connection()

    assert fake_bybit.asked[0].host == host


async def test_a_region_bybit_does_not_serve_is_a_configuration_failure(
    fake_bybit: FakeBybit,
) -> None:
    fake_bybit.refuse = (
        200,
        {"retCode": 10009, "retMsg": "Service Restricted: your region", "result": {}},
    )

    result = await _adapter().check_connection()

    assert not result.ok
    assert result.error_kind == "config"
    assert "Restricted" not in result.message


async def test_a_ban_holds_every_market_and_says_nothing_of_bybit(
    fake_bybit: FakeBybit,
) -> None:
    fake_bybit.refuse = (403, {"retCode": 10018, "retMsg": "access too frequent"})
    session = BybitSession(BybitMain(), None)
    async with session.kept() as kept:
        with pytest.raises(AdapterError) as first:
            await session._get(kept, session.markets[0], "time", {}, "")  # noqa: SLF001 - the ban is the session's own
        fake_bybit.refuse = None
        with pytest.raises(AdapterError) as held:
            await session._get(kept, session.markets[2], "time", {}, "")  # noqa: SLF001

    assert "frequent" not in first.value.message
    assert "s more" in held.value.message
    assert len(fake_bybit.asked) == 1


async def test_requests_are_counted_here_and_stop_at_two_fifths_of_five_seconds(
    fake_bybit: FakeBybit,
) -> None:
    session = BybitSession(BybitMain(), None)
    async with session.kept() as kept:
        assert kept.address is not None
        kept.address.used = 239
        kept.address.window = kept.address.window_of(datetime.now(UTC).timestamp())
        await session._get(kept, session.markets[1], "time", {}, "")  # noqa: SLF001 - the count is the session's own
        with pytest.raises(AdapterError) as refused:
            await session._get(kept, session.markets[0], "time", {}, "")  # noqa: SLF001

    assert "rate limit" in refused.value.message
    assert len(fake_bybit.asked) == 1


async def test_an_answer_bybit_refuses_is_a_code_not_its_words(
    fake_bybit: FakeBybit,
) -> None:
    fake_bybit.refuse = (200, {"retCode": 170001, "retMsg": "Internal secret"})
    session = BybitSession(BybitMain(), None)

    with pytest.raises(AdapterError) as refused:
        await session.get(session.markets[0], "time", {})

    assert "170001" in refused.value.message
    assert "secret" not in refused.value.message


# --- the catalog (D427, D425) ------------------------------------------------------


async def test_the_top_is_the_exchange_section_the_markets_folder_and_three_markets(
    fake_bybit: FakeBybit,
) -> None:
    del fake_bybit
    nodes = await _adapter().list_children(None)

    assert [node.id for node in nodes] == [
        "exchange",
        "markets",
        "spot",
        "linear",
        "inverse",
    ]


async def test_linear_symbols_are_read_page_by_page_by_cursor(
    fake_bybit: FakeBybit,
) -> None:
    nodes = await _adapter().list_children("linear")

    pages = [one for one in fake_bybit.asked if one.path.endswith("instruments-info")]
    assert len(pages) == 2
    assert pages[1].params["cursor"] == "2"
    # Trading only, quote assets fullest first.
    assert [node.id for node in nodes] == [
        "linear:tickers",
        "linear:symbols",
        "linear:quote:USDT",
        "linear:quote:USDC",
    ]


async def test_a_quote_lists_its_symbols_a_dated_future_among_them(
    fake_bybit: FakeBybit,
) -> None:
    del fake_bybit
    nodes = await _adapter().list_children("linear:quote:USDT")

    assert [node.name for node in nodes] == ["BTCUSDT", "BTCUSDT-27NOV26"]


async def test_a_symbol_holds_its_market_candles_trades_and_book(
    fake_bybit: FakeBybit,
) -> None:
    del fake_bybit
    adapter = _adapter()
    nodes = await adapter.list_children("spot:symbol:BTCUSDT")
    candles = await adapter.list_children("spot:symbol:BTCUSDT:candles")

    assert [node.id.rsplit(":", 1)[1] for node in nodes] == [
        "market",
        "candles",
        "trades",
        "book",
    ]
    assert [node.name for node in candles][:3] == ["1m", "3m", "5m"]
    assert "1s" not in [node.name for node in candles]


async def test_a_symbol_not_trading_is_not_there(fake_bybit: FakeBybit) -> None:
    del fake_bybit
    with pytest.raises(NodeNotFound):
        await _adapter().list_children("linear:symbol:NEWUSDT")


async def test_the_path_to_a_candle_series(fake_bybit: FakeBybit) -> None:
    del fake_bybit
    path = await _adapter().path_to("inverse:symbol:BTCUSD:candles:1h")

    assert [node.id for node in path] == [
        "inverse",
        "inverse:quote:USD",
        "inverse:symbol:BTCUSD",
        "inverse:symbol:BTCUSD:candles",
        "inverse:symbol:BTCUSD:candles:1h",
    ]


# --- the feeds (D427) ----------------------------------------------------------------


async def test_tickers_fill_the_shared_columns_busiest_first(
    fake_bybit: FakeBybit,
) -> None:
    del fake_bybit
    page = await _adapter().fetch(FetchRequest(node_id="spot:tickers", limit=10))

    names = [column.name for column in page.columns]
    assert names == [
        "symbol",
        "last_price",
        "price_change",
        "price_change_percent",
        "open_price",
        "high_price",
        "low_price",
        "volume",
        "quote_volume",
    ]
    assert [row[0] for row in page.rows] == ["ETHUSDT", "ETHBTC", "BTCUSDT"]
    eth = page.rows[0]
    assert eth[1:5] == ["101.5", "1.5", "0.5", "100"]
    assert eth[7:] == ["9000", "900000"]


async def test_inverse_volumes_keep_their_meaning(fake_bybit: FakeBybit) -> None:
    """Bybit counts inverse volume in USD and turnover in the coin (D427)."""
    del fake_bybit
    page = await _adapter().fetch(FetchRequest(node_id="inverse:tickers", limit=10))

    busiest = page.rows[0]
    assert busiest[0] == "BTCUSDZ26"
    assert busiest[7:] == ["900000", "9000"]


def test_a_fraction_becomes_a_percent_exactly() -> None:
    assert percent_of("0.0163") == "1.63"
    assert percent_of("0.1") == "10"
    assert percent_of("-0.005") == "-0.5"
    assert percent_of("") is None


async def test_the_symbols_list_says_a_contract_and_its_delivery(
    fake_bybit: FakeBybit,
) -> None:
    del fake_bybit
    page = await _adapter().fetch(FetchRequest(node_id="linear:symbols", limit=10))

    names = [column.name for column in page.columns]
    rows = {row[0]: dict(zip(names, row, strict=True)) for row in page.rows}
    assert rows["BTCUSDT"]["contract_type"] == "LinearPerpetual"
    assert rows["BTCUSDT"]["delivery_time"] is None
    assert rows["BTCUSDT-27NOV26"]["delivery_time"] == "2026-11-27T08:00:00.000Z"
    assert rows["BTCUSDT"]["min_notional"] == "5"
    assert "NEWUSDT" not in rows


async def test_candles_open_newest_first_the_last_one_open(
    fake_bybit: FakeBybit,
) -> None:
    page = await _adapter().fetch(
        FetchRequest(node_id="spot:symbol:BTCUSDT:candles:1h", limit=3)
    )

    newest = fake_bybit.first_open_ms + (CANDLES - 1) * HOUR_MS
    names = [column.name for column in page.columns]
    assert "trades" not in names
    assert [row[0] for row in page.rows] == [
        _iso(newest),
        _iso(newest - HOUR_MS),
        _iso(newest - 2 * HOUR_MS),
    ]
    first = dict(zip(names, page.rows[0], strict=True))
    assert first["close_time"] == _iso(newest + HOUR_MS - 1)
    assert first["closed"] == "false"
    assert page.rows[1][names.index("closed")] == "true"
    assert first["volume"] == "5"
    assert first["quote_volume"] == "500"
    assert page.has_more


async def test_candles_deeper_than_one_request_are_read_in_turn(
    fake_bybit: FakeBybit,
) -> None:
    page = await _adapter().fetch(
        FetchRequest(node_id="spot:symbol:BTCUSDT:candles:1h", limit=500, offset=900)
    )

    assert len(page.rows) == 500
    asked = [one for one in fake_bybit.asked if one.path.endswith("kline")]
    assert len(asked) == 2
    assert "end" in asked[1].params


async def test_candles_ascending_read_forwards_from_a_time(
    fake_bybit: FakeBybit,
) -> None:
    start = fake_bybit.first_open_ms + 10 * HOUR_MS
    page = await _adapter().fetch(
        FetchRequest(
            node_id="inverse:symbol:BTCUSD:candles:1h",
            limit=2,
            sort=[Sort(column="open_time", descending=False)],
            filters=[ScalarFilter(column="open_time", op="gte", value=_iso(start))],
        )
    )

    assert [row[0] for row in page.rows] == [_iso(start), _iso(start + HOUR_MS)]
    # Inverse: Bybit's volume is the quote's, its turnover the base's.
    assert page.rows[0][6:8] == ["500", "5"]


def test_a_month_closes_by_the_calendar() -> None:
    february = int(datetime(2026, 2, 1, tzinfo=UTC).timestamp() * 1000)

    assert (
        close_ms("1M", february)
        == int(datetime(2026, 3, 1, tzinfo=UTC).timestamp() * 1000) - 1
    )


async def test_trades_are_the_newest_bybit_answers_sorted_here(
    fake_bybit: FakeBybit,
) -> None:
    page = await _adapter().fetch(
        FetchRequest(node_id="linear:symbol:BTCUSDT:trades", limit=3)
    )

    assert [column.name for column in page.columns] == [
        "id",
        "price",
        "quantity",
        "time",
        "buyer_is_maker",
    ]
    assert [row[0] for row in page.rows] == [
        f"uuid-{TRADES}",
        f"uuid-{TRADES - 1}",
        f"uuid-{TRADES - 2}",
    ]
    # The taker of an even trade sold: the buyer was resting in the book.
    assert page.rows[0][4] == "true"
    assert page.rows[1][4] == "false"
    assert page.has_more
    assert fake_bybit.asked[-1].params["limit"] == "1000"


async def test_spot_trades_are_sixty(fake_bybit: FakeBybit) -> None:
    page = await _adapter().fetch(
        FetchRequest(
            node_id="spot:symbol:BTCUSDT:trades",
            limit=100,
            sort=[Sort(column="price", descending=False)],
        )
    )

    assert len(page.rows) == 60
    assert not page.has_more
    assert page.rows[0][0] == str(TRADES - 59)
    assert fake_bybit.asked[-1].params["limit"] == "60"


async def test_the_book_is_read_to_the_levels_asked(fake_bybit: FakeBybit) -> None:
    page = await _adapter().fetch(
        FetchRequest(
            node_id="linear:symbol:BTCUSDT:book",
            filters=[ScalarFilter(column="level", op="lte", value="7")],
        )
    )

    assert fake_bybit.asked[-1].params["limit"] == "7"
    assert [row[0] for row in page.rows] == ["bid"] * 7 + ["ask"] * 7
    assert page.rows[1][4] == "3.0"


async def test_a_symbol_gone_since_the_list_was_read_is_not_found(
    fake_bybit: FakeBybit,
) -> None:
    store = ResourceStore(max_entries=4, max_idle_seconds=60)
    pooling = Pooling(store=store, connector_id=uuid.uuid4())
    adapter = BybitAdapter(BybitSession(BybitMain(), pooling))
    try:
        await adapter.fetch(FetchRequest(node_id="spot:symbols"))
        fake_bybit.refuse = (
            200,
            {"retCode": 10001, "retMsg": "Not supported symbols"},
        )
        with pytest.raises(NodeNotFound):
            await adapter.fetch(FetchRequest(node_id="spot:symbol:BTCUSDT:book"))
    finally:
        await store.aclose()


async def test_an_export_reads_candles_to_its_depth(fake_bybit: FakeBybit) -> None:
    del fake_bybit
    batches = [
        batch
        async for batch in _adapter().export_rows(
            ExportRequest(
                node_id="spot:symbol:ETHBTC:candles:1h",
                columns=["open_time", "close"],
            )
        )
    ]

    rows = [row for batch in batches for row in batch.rows]
    assert len(rows) == CANDLES
    assert rows[0][1] == "1"
