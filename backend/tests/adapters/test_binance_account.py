"""What a Binance key reads of its account, against a fake Binance (D322)."""

import pytest

from app.adapters.binance.adapter import BinanceAdapter
from app.adapters.binance.options import (
    BinanceMain,
    BinanceMainKey,
    BinanceTestnetKey,
)
from app.adapters.binance.session import BinanceSession
from app.adapters.fetch import FetchRequest
from app.adapters.protocol import AdapterError, NodeNotFound
from app.adapters.reading_on import Bookmark
from tests.adapters.binance_fixture import (
    API_KEY,
    API_SECRET,
    FakeBinance,
    install,
)


@pytest.fixture
def fake_binance(monkeypatch: pytest.MonkeyPatch) -> FakeBinance:
    return install(monkeypatch)


def _keyed(secret: str = API_SECRET, testnet: bool = False) -> BinanceAdapter:
    model = BinanceTestnetKey if testnet else BinanceMainKey
    options = model.model_validate({"api_key": API_KEY, "api_secret": secret})
    return BinanceAdapter(BinanceSession(options, None))


async def _rows(
    adapter: BinanceAdapter, node_id: str
) -> dict[str, dict[str, str | None]]:
    """A page as rows by their first column, each a mapping of its columns."""
    result = await adapter.fetch(FetchRequest(node_id=node_id))
    names = [column.name for column in result.columns]
    return {str(row[0]): dict(zip(names, row, strict=True)) for row in result.rows}


# --- the catalog ------------------------------------------------------------------


async def test_without_a_key_there_is_no_account_anywhere(
    fake_binance: FakeBinance,
) -> None:
    del fake_binance
    adapter = BinanceAdapter(BinanceSession(BinanceMain(), None))

    market = [node.id for node in await adapter.list_children("spot")]
    symbol = [node.id for node in await adapter.list_children("spot:symbol:BTCUSDT")]
    section = [node.id for node in await adapter.list_children("exchange")]

    assert "spot:account" not in market
    assert not any(one.endswith((":orders", ":my_trades")) for one in symbol)
    assert "report:key" not in section
    with pytest.raises(NodeNotFound):
        await adapter.fetch(FetchRequest(node_id="spot:account:balances"))


async def test_a_key_adds_an_account_to_each_market_and_its_own_to_a_symbol(
    fake_binance: FakeBinance,
) -> None:
    del fake_binance
    adapter = _keyed()

    market = [node.id for node in await adapter.list_children("spot")]
    spot = [node.id for node in await adapter.list_children("spot:account")]
    usdm = [node.id for node in await adapter.list_children("usdm:account")]
    symbol = [node.id for node in await adapter.list_children("spot:symbol:BTCUSDT")]

    assert market[:3] == ["spot:tickers", "spot:symbols", "spot:account"]
    assert spot == [
        "spot:account:balances",
        "spot:account:open_orders",
        "spot:account:deposits",
        "spot:account:withdrawals",
    ]
    assert usdm == [
        "usdm:account:balances",
        "usdm:account:positions",
        "usdm:account:open_orders",
    ]
    assert symbol[-2:] == [
        "spot:symbol:BTCUSDT:orders",
        "spot:symbol:BTCUSDT:my_trades",
    ]
    path = await adapter.path_to("usdm:account:positions")
    assert [node.id for node in path] == [
        "usdm",
        "usdm:account",
        "usdm:account:positions",
    ]


async def test_the_testnet_has_no_wallet_transfers_and_spot_has_no_positions(
    fake_binance: FakeBinance,
) -> None:
    del fake_binance
    adapter = _keyed(testnet=True)

    spot = [node.id for node in await adapter.list_children("spot:account")]

    assert spot == ["spot:account:balances", "spot:account:open_orders"]
    for gone in ("spot:account:deposits", "spot:account:positions"):
        with pytest.raises(NodeNotFound):
            await adapter.fetch(FetchRequest(node_id=gone))


# --- signing -----------------------------------------------------------------------


async def test_a_request_of_the_account_is_signed_and_names_the_key_in_a_header(
    fake_binance: FakeBinance,
) -> None:
    await _rows(_keyed(), "spot:account:balances")

    signed = [one for one in fake_binance.asked if "signature" in one.params]
    assert [one.path for one in signed] == ["/api/v3/account"]
    params = signed[0].params
    assert {"timestamp", "recvWindow", "omitZeroBalances"} <= set(params)
    assert API_SECRET not in str(params) and API_KEY not in str(params)
    # The clock was measured first, unsigned.
    assert fake_binance.asked[0].path == "/api/v3/time"


async def test_a_secret_binance_would_not_take_is_said_without_the_secret(
    fake_binance: FakeBinance,
) -> None:
    del fake_binance
    with pytest.raises(AdapterError) as refused:
        await _rows(_keyed(secret="wrong-secret"), "spot:account:balances")

    assert refused.value.error_kind == "auth"
    assert "wrong-secret" not in refused.value.message


async def test_a_stale_time_is_measured_again_once(fake_binance: FakeBinance) -> None:
    fake_binance.stale = 1
    rows = await _rows(_keyed(), "spot:account:balances")
    assert "BTC" in rows

    fake_binance.stale = 2
    with pytest.raises(AdapterError) as refused:
        await _rows(_keyed(), "spot:account:balances")
    assert refused.value.error_kind == "config"


# --- rows ----------------------------------------------------------------------------


async def test_spot_balances_leave_out_nothing_held_and_add_up_what_is(
    fake_binance: FakeBinance,
) -> None:
    del fake_binance
    rows = await _rows(_keyed(), "spot:account:balances")

    assert set(rows) == {"BTC", "USDT"}
    assert rows["BTC"]["total"] == "0.6"


async def test_futures_balances_and_positions_leave_out_what_is_empty(
    fake_binance: FakeBinance,
) -> None:
    del fake_binance
    adapter = _keyed()

    balances = await _rows(adapter, "usdm:account:balances")
    positions = await _rows(adapter, "coinm:account:positions")

    assert set(balances) == {"USDT"}
    assert balances["USDT"]["margin_balance"] == "10.5"
    assert set(positions) == {"BTCUSD_PERP"}
    assert positions["BTCUSD_PERP"]["side"] == "both"
    assert positions["BTCUSD_PERP"]["liquidation_price"] is None


async def test_orders_open_and_past_read_as_rows(fake_binance: FakeBinance) -> None:
    adapter = _keyed()

    open_orders = await _rows(adapter, "spot:account:open_orders")
    history = await adapter.fetch(FetchRequest(node_id="spot:symbol:BTCUSDT:orders"))

    assert open_orders["1"]["status"] == "new"
    assert open_orders["1"]["average_price"] is None
    assert open_orders["1"]["stop_price"] is None
    # Newest first, by time.
    assert [row[0] for row in history.rows] == ["1", "2", "3"]
    asked = [one for one in fake_binance.asked if one.path == "/api/v3/allOrders"]
    assert asked[0].params["symbol"] == "BTCUSDT"


async def test_own_trades_say_their_side_and_on_coin_m_their_worth(
    fake_binance: FakeBinance,
) -> None:
    del fake_binance
    adapter = _keyed()

    spot = await _rows(adapter, "spot:symbol:BTCUSDT:my_trades")
    coin = await _rows(adapter, "coinm:symbol:BTCUSD_PERP:my_trades")

    assert set(spot) == {"70", "40", "25", "10"}
    assert spot["10"]["side"] == "sell"
    assert spot["10"]["quote_quantity"] == "301.5"
    assert spot["10"]["realized_pnl"] is None
    # Three contracts of 100 USD.
    assert coin["10"]["quote_quantity"] == "300"
    assert coin["10"]["side"] == "buy"
    assert coin["10"]["realized_pnl"] == "0.5"


async def test_deposits_and_withdrawals_say_their_state_in_words(
    fake_binance: FakeBinance,
) -> None:
    del fake_binance
    adapter = _keyed()

    deposits = await _rows(adapter, "spot:account:deposits")
    withdrawals = await _rows(adapter, "spot:account:withdrawals")

    assert deposits["d1"]["status"] == "success"
    assert withdrawals["w1"]["status"] == "completed"
    assert withdrawals["w1"]["apply_time"] == "2026-11-01T10:00:00.000Z"


# --- the check and the report --------------------------------------------------------


async def test_a_read_only_key_checks_plainly(fake_binance: FakeBinance) -> None:
    del fake_binance
    result = await _keyed().check_connection()

    assert result.ok
    assert result.message == "Connection successful"


async def test_a_key_that_may_trade_is_accepted_and_said(
    fake_binance: FakeBinance,
) -> None:
    fake_binance.permissions["enableSpotAndMarginTrading"] = True
    result = await _keyed().check_connection()

    assert result.ok
    assert "may also trade" in result.message


async def test_a_key_that_may_not_read_fails_the_check(
    fake_binance: FakeBinance,
) -> None:
    fake_binance.permissions["enableReading"] = False
    result = await _keyed().check_connection()

    assert not result.ok
    assert result.error_kind == "auth"


async def test_a_testnet_key_is_tried_rather_than_asked_about(
    fake_binance: FakeBinance,
) -> None:
    result = await _keyed(testnet=True).check_connection()

    assert result.ok
    assert not any("apiRestrictions" in one for one in fake_binance.signed)
    assert "/api/v3/account" in fake_binance.signed


async def test_the_key_report_says_what_it_may_do(fake_binance: FakeBinance) -> None:
    fake_binance.permissions["enableWithdrawals"] = True
    rows = await _rows(_keyed(), "report:key")

    assert rows["read"]["Value"] == "yes"
    assert rows["withdraw"]["Value"] == "yes"
    assert rows["trade futures"]["Value"] == "no"
    assert rows["limited to listed addresses"]["Value"] == "yes"


# --- reading on ----------------------------------------------------------------------


class _Kept:
    def __init__(self) -> None:
        self.kept: dict[tuple[str, str], Bookmark] = {}

    async def read(self, node_id: str, reader: str) -> Bookmark | None:
        return self.kept.get((node_id, reader))

    async def write(self, node_id: str, reader: str, at: Bookmark) -> None:
        self.kept[(node_id, reader)] = at


async def test_own_trades_are_read_on_by_their_id(fake_binance: FakeBinance) -> None:
    options = BinanceMainKey.model_validate(
        {"api_key": API_KEY, "api_secret": API_SECRET}
    )
    adapter = BinanceAdapter(BinanceSession(options, None), _Kept())
    node = "spot:symbol:BTCUSDT:my_trades"

    assert adapter.reads_on(node)
    assert adapter.row_key(node) == ["id"]
    fresh = await adapter.unread(node, "link", "new")
    span = await adapter.unread(node, "link", "earliest")
    block = await adapter.read_on(node, ["id", "side"], span.start, span.line, 1000)

    assert fresh.count == 0
    assert span.start.positions[""] == 10
    assert span.line.positions[""] == 71
    assert [row[0] for row in block.rows] == ["10", "25", "40", "70"]
    assert block.done
    asked = [one.params for one in fake_binance.asked if one.path == "/api/v3/myTrades"]
    assert "10" in [one.get("fromId") for one in asked]


def test_the_endpoint_stays_first_in_a_form_with_a_key() -> None:
    """Choosing a key adds its fields below the choice, never above it."""
    for model in (BinanceMainKey, BinanceTestnetKey):
        assert list(model.model_json_schema()["properties"]) == [
            "endpoint",
            "api_key",
            "api_secret",
        ]
