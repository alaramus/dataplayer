"""An OKX connection, its catalog and its feeds, against a fake OKX (D432, D433)."""

from datetime import UTC, datetime
from typing import Any

import pytest

from app.adapters.export import ExportRequest
from app.adapters.fetch import FetchRequest, ScalarFilter, Sort
from app.adapters.market import session as shared_session
from app.adapters.okx.adapter import OkxAdapter
from app.adapters.okx.feeds import percent_of
from app.adapters.okx.options import OkxDemo, OkxEea, OkxMain
from app.adapters.okx.session import OkxSession
from app.adapters.protocol import AdapterError, NodeNotFound
from app.adapters.resources import Pooling, ResourceStore
from tests.adapters.okx_fixture import (
    CANDLES,
    HOUR_MS,
    TRADES,
    FakeOkx,
    install,
)


@pytest.fixture
def fake_okx(monkeypatch: pytest.MonkeyPatch) -> FakeOkx:
    return install(monkeypatch)


class Clock:
    """The session's clock, moved on by its sleeps instead of waiting."""

    def __init__(self) -> None:
        self.offset = 0.0
        self.slept: list[float] = []

    def time(self) -> float:
        import time

        return time.time() + self.offset

    def monotonic(self) -> float:
        import time

        return time.monotonic() + self.offset

    def perf_counter(self) -> float:
        import time

        return time.perf_counter()

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.offset += seconds


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    found = Clock()
    monkeypatch.setattr(shared_session, "time", found)
    monkeypatch.setattr(shared_session.asyncio, "sleep", found.sleep)
    return found


def _adapter() -> OkxAdapter:
    return OkxAdapter(OkxSession(OkxMain(), None))


def _kept_adapter() -> OkxAdapter:
    """One client kept between requests, as a saved connection has."""
    store = ResourceStore(max_entries=4, max_idle_seconds=60)
    return OkxAdapter(OkxSession(OkxMain(), Pooling(store, "okx-test")))


def _iso(milliseconds: int) -> str:
    at = datetime.fromtimestamp(milliseconds / 1000, tz=UTC)
    return at.isoformat(timespec="milliseconds").replace("+00:00", "Z")


async def _page(adapter: OkxAdapter, node_id: str, **more: Any) -> Any:
    return await adapter.fetch(FetchRequest(node_id=node_id, **more))


# --- the connection (D432) ----------------------------------------------------------


async def test_a_check_asks_every_market_for_the_time(fake_okx: FakeOkx) -> None:
    result = await _adapter().check_connection()

    assert result.ok
    assert [one.path for one in fake_okx.asked] == ["/api/v5/public/time"] * 3
    assert {one.host for one in fake_okx.asked} == {"www.okx.com"}
    assert "x-simulated-trading" not in fake_okx.asked[0].headers


async def test_europe_is_its_own_host_and_demo_says_so_on_every_request(
    fake_okx: FakeOkx,
) -> None:
    await OkxAdapter(OkxSession(OkxEea(), None)).check_connection()
    assert fake_okx.asked[-1].host == "eea.okx.com"

    await OkxAdapter(OkxSession(OkxDemo(), None)).check_connection()
    assert fake_okx.asked[-1].host == "www.okx.com"
    assert fake_okx.asked[-1].headers["x-simulated-trading"] == "1"


async def test_a_region_okx_does_not_serve_is_a_configuration_failure(
    fake_okx: FakeOkx,
) -> None:
    fake_okx.refuse = (
        200,
        {"code": "50121", "msg": "You can't access our services through 1.2.3.4"},
    )

    result = await _adapter().check_connection()

    assert not result.ok
    assert result.error_kind == "config"
    assert "1.2.3.4" not in result.message


async def test_a_rate_limit_refusal_holds_that_path_and_says_nothing_of_okx(
    fake_okx: FakeOkx,
) -> None:
    fake_okx.refuse = (429, {"code": "50011", "msg": "Too Many Requests"})
    session = OkxSession(OkxMain(), None)
    async with session.kept() as kept:
        with pytest.raises(AdapterError) as first:
            await session._get(kept, session.markets[0], "/api/v5/public/time", {}, "")  # noqa: SLF001 - the hold is the session's own
        fake_okx.refuse = None
        with pytest.raises(AdapterError) as held:
            await session._get(kept, session.markets[2], "/api/v5/public/time", {}, "")  # noqa: SLF001
        # Another path has a budget of its own and is not held.
        await session._get(kept, session.markets[0], "/api/v5/system/status", {}, "")  # noqa: SLF001

    assert "Too Many" not in first.value.message
    assert "s more" in held.value.message


async def test_a_request_over_the_ceiling_waits_for_the_next_window(
    fake_okx: FakeOkx, clock: Clock
) -> None:
    session = OkxSession(OkxMain(), None)
    async with session.kept() as kept:
        for _ in range(9):
            await session._get(kept, session.markets[0], "/api/v5/public/time", {}, "")  # noqa: SLF001 - the budget is the session's own

    # Ten in two seconds, stopped at 40%: four a window, so two waits.
    assert len(clock.slept) == 2
    assert all(0 < one <= 2.001 for one in clock.slept)
    assert len(fake_okx.asked) == 9


async def test_a_page_deeper_than_a_window_allows_is_read_whole(
    fake_okx: FakeOkx, clock: Clock
) -> None:
    page = await _page(
        _kept_adapter(), "spot:symbol:BTC-USDT:candles:1h", limit=1000, offset=2500
    )

    assert len(page.rows) == CANDLES - 2500
    assert clock.slept
    del fake_okx


async def test_maintenance_of_trading_is_said(fake_okx: FakeOkx) -> None:
    fake_okx.maintenance = True

    assert await OkxSession(OkxMain(), None).system_status() == "maintenance"


# --- the catalog (D433) -------------------------------------------------------------


async def test_the_root_holds_the_section_the_folder_and_three_markets(
    fake_okx: FakeOkx,
) -> None:
    nodes = await _adapter().list_children(None)

    assert [node.id for node in nodes] == [
        "exchange",
        "markets",
        "spot",
        "linear",
        "inverse",
    ]
    del fake_okx


async def test_contracts_are_split_by_what_they_are_counted_in(
    fake_okx: FakeOkx,
) -> None:
    adapter = _adapter()

    linear = [node.id for node in await adapter.list_children("linear")]
    inverse = [node.id for node in await adapter.list_children("inverse")]
    usdt = await adapter.list_children("linear:quote:USDT")

    assert linear == [
        "linear:tickers",
        "linear:symbols",
        "linear:quote:USDT",
        "linear:quote:USDC",
    ]
    assert inverse == ["inverse:tickers", "inverse:symbols", "inverse:quote:USD"]
    assert [node.name for node in usdt] == ["BTC-USDT-261225", "BTC-USDT-SWAP"]
    assert [getattr(node, "contract_type", None) for node in usdt] == [
        "FUTURES",
        "SWAP",
    ]
    del fake_okx


async def test_a_symbol_not_live_is_not_a_node(fake_okx: FakeOkx) -> None:
    with pytest.raises(NodeNotFound):
        await _adapter().path_to("linear:symbol:NEW-USDT-SWAP")
    with pytest.raises(NodeNotFound):
        await _page(_adapter(), "spot:symbol:GONE-USDT:trades")
    # Nothing was asked of a symbol the list does not hold.
    assert not [one for one in fake_okx.asked if "instId" in one.params]


# --- tickers and symbols (D433) -------------------------------------------------------


async def test_spot_tickers_keep_both_volumes_busiest_first(fake_okx: FakeOkx) -> None:
    page = await _page(_adapter(), "spot:tickers")
    names = [column.name for column in page.columns]

    assert names[-2:] == ["volume", "quote_volume"]
    assert page.rows[0][0] == "ETH-USDT"
    eth = page.rows[0]
    assert eth[names.index("volume")] == "9000"
    assert eth[names.index("quote_volume")] == "900000"
    assert eth[names.index("price_change")] == "1.5"
    assert eth[names.index("price_change_percent")] == "1.500"
    # A symbol not live is left out.
    assert "GONE-USDT" not in [row[0] for row in page.rows]
    del fake_okx


async def test_linear_tickers_have_no_quote_volume_and_their_volume_is_the_coin(
    fake_okx: FakeOkx,
) -> None:
    page = await _page(_adapter(), "linear:tickers")
    names = [column.name for column in page.columns]

    assert "quote_volume" not in names
    by_name = {row[0]: row for row in page.rows}
    # volCcy24h: the base coin's volume, not the contracts.
    assert by_name["BTC-USDC-SWAP"][names.index("volume")] == "900000"
    assert page.rows[0][0] == "BTC-USDC-SWAP"
    del fake_okx


async def test_inverse_quote_volume_is_the_contracts_worth_in_usd(
    fake_okx: FakeOkx,
) -> None:
    page = await _page(_adapter(), "inverse:tickers")
    names = [column.name for column in page.columns]
    by_name = {row[0]: row for row in page.rows}

    swap = by_name["BTC-USD-SWAP"]
    # The third SWAP: 2.5 contracts of 100 USD, and 2.25 BTC.
    assert swap[names.index("volume")] == "2.25"
    assert swap[names.index("quote_volume")] == "250.0"
    del fake_okx


def test_the_percent_is_rounded_to_three_places_never_through_a_float() -> None:
    assert percent_of("100.5", "100") == "0.500"
    assert percent_of("1", "3") == "-66.667"
    assert percent_of("1", "0") is None


async def test_symbols_say_a_step_in_the_coin_or_in_contracts(
    fake_okx: FakeOkx,
) -> None:
    adapter = _adapter()
    linear = await _page(adapter, "linear:symbols")
    inverse = await _page(adapter, "inverse:symbols")
    spot = await _page(adapter, "spot:symbols")

    linear_names = [column.name for column in linear.columns]
    inverse_names = [column.name for column in inverse.columns]
    assert "min_notional" not in linear_names
    assert "min_notional" not in [column.name for column in spot.columns]
    swap = {row[0]: row for row in linear.rows}["BTC-USDT-SWAP"]
    # A lot of 0.01 contracts of 0.01 BTC.
    assert swap[linear_names.index("quantity_step")] == "0.0001"
    assert swap[linear_names.index("delivery_time")] is None
    futures = {row[0]: row for row in linear.rows}["BTC-USDT-261225"]
    assert futures[linear_names.index("delivery_time")] == _iso(1798185600000)
    coin = {row[0]: row for row in inverse.rows}["BTC-USD-SWAP"]
    assert coin[inverse_names.index("quantity_step")] == "0.1"
    assert coin[inverse_names.index("contract_size")] == "100"
    del fake_okx


# --- candles (D433) -------------------------------------------------------------------


async def test_candles_are_read_newest_first_with_both_volumes(
    fake_okx: FakeOkx,
) -> None:
    page = await _page(_adapter(), "linear:symbol:BTC-USDT-SWAP:candles:1h", limit=3)
    names = [column.name for column in page.columns]

    assert names == [
        "open_time",
        "close_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "closed",
    ]
    newest = fake_okx.first_open_ms + (CANDLES - 1) * HOUR_MS
    assert page.rows[0][0] == _iso(newest)
    assert page.rows[0][1] == _iso(newest + HOUR_MS - 1)
    # A contract's base volume is OKX's volCcy, its quote volCcyQuote.
    assert page.rows[0][6:9] == ["7", "500", "false"]
    assert page.rows[1][8] == "true"
    assert page.has_more


async def test_spot_candles_count_the_base_in_the_first_volume(
    fake_okx: FakeOkx,
) -> None:
    page = await _page(_adapter(), "spot:symbol:BTC-USDT:candles:1h", limit=1)

    assert page.rows[0][6:8] == ["5", "500"]
    del fake_okx


async def test_candles_read_forwards_from_a_time(fake_okx: FakeOkx) -> None:
    start = fake_okx.first_open_ms + 10 * HOUR_MS
    page = await _page(
        _adapter(),
        "spot:symbol:BTC-USDT:candles:1h",
        limit=400,
        filters=[ScalarFilter(column="open_time", op="gte", value=_iso(start))],
        sort=[Sort(column="open_time", descending=False)],
    )

    opens = [row[0] for row in page.rows]
    assert opens[0] == _iso(start)
    assert opens[-1] == _iso(start + 399 * HOUR_MS)
    assert opens == sorted(opens)
    assert len(set(opens)) == 400


# --- trades (D433) -------------------------------------------------------------------


async def test_trades_are_read_newest_first_by_their_numbers(
    fake_okx: FakeOkx,
) -> None:
    page = await _page(_adapter(), "spot:symbol:BTC-USDT:trades", limit=150)
    names = [column.name for column in page.columns]

    assert names == ["id", "price", "quantity", "time", "buyer_is_maker"]
    assert [row[0] for row in page.rows[:2]] == [str(TRADES), str(TRADES - 1)]
    assert len(page.rows) == 150
    # The taker sold an even trade: its buyer was the maker.
    assert page.rows[0][4] == "true"
    assert page.rows[0][2] == "2"
    assert page.has_more
    del fake_okx


async def test_a_contracts_trade_is_said_in_the_coin_or_in_usd(
    fake_okx: FakeOkx,
) -> None:
    adapter = _adapter()
    linear = await _page(adapter, "linear:symbol:BTC-USDT-SWAP:trades", limit=1)
    inverse = await _page(adapter, "inverse:symbol:BTC-USD-SWAP:trades", limit=1)

    # Two contracts of 0.01 BTC; two of 100 USD.
    assert linear.rows[0][2] == "0.02"
    assert [column.name for column in inverse.columns][2] == "quote_quantity"
    assert inverse.rows[0][2] == "200"
    del fake_okx


async def test_trades_by_id_and_time_ascending(fake_okx: FakeOkx) -> None:
    adapter = _adapter()
    by_id = await _page(
        adapter,
        "spot:symbol:BTC-USDT:trades",
        limit=5,
        filters=[ScalarFilter(column="id", op="gte", value="2000")],
        sort=[Sort(column="id", descending=False)],
    )
    at = fake_okx.trade_ms(3000)
    by_time = await _page(
        adapter,
        "spot:symbol:BTC-USDT:trades",
        limit=2,
        filters=[ScalarFilter(column="time", op="lte", value=_iso(at))],
    )

    assert [row[0] for row in by_id.rows] == ["2000", "2001", "2002", "2003", "2004"]
    assert [row[0] for row in by_time.rows] == ["3000", "2999"]


async def test_a_young_symbols_oldest_trades_start_at_its_first(
    fake_okx: FakeOkx,
) -> None:
    fake_okx.first_trade = 1
    page = await _page(
        _adapter(),
        "spot:symbol:BTC-USDT:trades",
        limit=2,
        sort=[Sort(column="id", descending=False)],
    )

    assert [row[0] for row in page.rows] == [
        str(fake_okx.first_trade),
        str(fake_okx.first_trade + 1),
    ]


# --- the book (D433) ------------------------------------------------------------------


async def test_the_book_is_read_to_its_depth_a_contract_in_the_coin(
    fake_okx: FakeOkx,
) -> None:
    page = await _page(
        _adapter(),
        "linear:symbol:BTC-USDT-SWAP:book",
        filters=[ScalarFilter(column="level", op="lte", value="3")],
    )

    books = [one for one in fake_okx.asked if one.path.endswith("/books")]
    assert books[-1].params["sz"] == "3"
    assert [row[0] for row in page.rows] == ["bid"] * 3 + ["ask"] * 3
    # 1.5 contracts of 0.01 BTC.
    assert page.rows[0][3] == "0.015"
    assert page.rows[2][4] == "0.045"


async def test_an_export_of_trades_reads_its_depth(fake_okx: FakeOkx) -> None:
    rows: list[list[str | None]] = []
    async for batch in _kept_adapter().export_rows(
        ExportRequest(
            node_id="spot:symbol:BTC-USDT:trades",
            columns=["id", "price"],
            filters=[ScalarFilter(column="id", op="gt", value=str(TRADES - 250))],
        )
    ):
        rows.extend(batch.rows)

    assert len(rows) == 250
    assert rows[0][0] == str(TRADES)
    del fake_okx
