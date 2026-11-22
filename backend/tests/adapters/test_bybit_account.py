"""A Bybit key and the unified account it reads, against a fake Bybit (D431)."""

import pytest
from pydantic import SecretStr

from app.adapters.bybit.adapter import BybitAdapter
from app.adapters.bybit.options import BybitMain, BybitMainKey, BybitTestnetKey
from app.adapters.bybit.session import BybitSession
from app.adapters.fetch import FetchRequest
from app.adapters.protocol import AdapterError, NodeNotFound
from app.adapters.reading_on import Bookmark
from tests.adapters.bybit_fixture import (
    API_KEY,
    API_SECRET,
    HOUR_MS,
    FakeBybit,
    install,
)

READER = "dataplayer-link-1"


@pytest.fixture
def fake_bybit(monkeypatch: pytest.MonkeyPatch) -> FakeBybit:
    return install(monkeypatch)


def _keyed(secret: str = API_SECRET, testnet: bool = False) -> BybitAdapter:
    key = SecretStr(API_KEY)
    options = (
        BybitTestnetKey(api_key=key, api_secret=SecretStr(secret))
        if testnet
        else BybitMainKey(api_key=key, api_secret=SecretStr(secret))
    )
    return BybitAdapter(BybitSession(options, None))


async def _rows(
    adapter: BybitAdapter, node_id: str
) -> dict[str, dict[str, str | None]]:
    page = await adapter.fetch(FetchRequest(node_id=node_id, limit=100))
    names = [column.name for column in page.columns]
    return {str(row[0]): dict(zip(names, row, strict=True)) for row in page.rows}


class Kept:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], Bookmark] = {}

    async def read(self, node_id: str, reader: str) -> Bookmark | None:
        return self.rows.get((node_id, reader))

    async def write(self, node_id: str, reader: str, at: Bookmark) -> None:
        self.rows[(node_id, reader)] = at


# --- the catalog ----------------------------------------------------------------------


async def test_without_a_key_there_is_no_account_anywhere(
    fake_bybit: FakeBybit,
) -> None:
    del fake_bybit
    adapter = BybitAdapter(BybitSession(BybitMain(), None))

    spot = await adapter.list_children("spot")
    symbol = await adapter.list_children("spot:symbol:BTCUSDT")

    assert "spot:account" not in [node.id for node in spot]
    assert not any(node.id.endswith(":my_trades") for node in symbol)
    with pytest.raises(NodeNotFound):
        await adapter.fetch(FetchRequest(node_id="spot:account:balances"))


async def test_a_key_adds_an_account_to_each_market_and_its_own_to_a_symbol(
    fake_bybit: FakeBybit,
) -> None:
    del fake_bybit
    adapter = _keyed()

    spot = await adapter.list_children("spot:account")
    linear = await adapter.list_children("linear:account")
    symbol = await adapter.list_children("linear:symbol:BTCUSDT")
    path = await adapter.path_to("inverse:account:positions")

    assert [node.id for node in spot] == [
        "spot:account:balances",
        "spot:account:open_orders",
        "spot:account:deposits",
        "spot:account:withdrawals",
    ]
    assert [node.id for node in linear] == [
        "linear:account:balances",
        "linear:account:positions",
        "linear:account:open_orders",
    ]
    assert [node.id.rsplit(":", 1)[1] for node in symbol][-2:] == [
        "orders",
        "my_trades",
    ]
    assert [node.id for node in path] == [
        "inverse",
        "inverse:account",
        "inverse:account:positions",
    ]
    with pytest.raises(NodeNotFound):
        await adapter.fetch(FetchRequest(node_id="linear:account:deposits"))


# --- signing (D431) ---------------------------------------------------------------


async def test_a_request_of_the_account_is_signed_and_names_the_key_in_a_header(
    fake_bybit: FakeBybit,
) -> None:
    await _rows(_keyed(), "spot:account:balances")

    assert fake_bybit.signed == ["/v5/account/wallet-balance"]
    asked = fake_bybit.asked[-1]
    assert asked.params == {"accountType": "UNIFIED"}
    assert "signature" not in asked.params


async def test_a_secret_bybit_would_not_take_is_said_without_the_secret(
    fake_bybit: FakeBybit,
) -> None:
    del fake_bybit
    with pytest.raises(AdapterError) as refused:
        await _rows(_keyed(secret="wrong-secret"), "spot:account:balances")

    assert refused.value.error_kind == "auth"
    assert "wrong-secret" not in refused.value.message
    assert "signature" not in refused.value.message


async def test_a_stale_time_is_measured_again_once(fake_bybit: FakeBybit) -> None:
    fake_bybit.stale = 1

    rows = await _rows(_keyed(), "spot:account:balances")

    assert "BTC" in rows
    clock = [one for one in fake_bybit.asked if one.path == "/v5/market/time"]
    assert len(clock) == 2


async def test_a_time_still_refused_is_a_configuration_failure(
    fake_bybit: FakeBybit,
) -> None:
    fake_bybit.stale = 5

    with pytest.raises(AdapterError) as refused:
        await _rows(_keyed(), "spot:account:balances")

    assert refused.value.error_kind == "config"
    assert "clock" in refused.value.message


# --- rows ----------------------------------------------------------------------------


async def test_the_unified_wallet_leaves_out_nothing_held(
    fake_bybit: FakeBybit,
) -> None:
    del fake_bybit
    adapter = _keyed()
    spot = await _rows(adapter, "spot:account:balances")
    linear = await _rows(adapter, "linear:account:balances")

    assert set(spot) == {"BTC", "USDT"}
    assert spot["BTC"]["wallet_balance"] == "0.5"
    assert spot["BTC"]["locked"] == "0.1"
    assert spot["BTC"]["usd_value"] == "30000"
    # One wallet for every market.
    assert linear == spot


async def test_positions_are_asked_by_settle_coin_and_leave_out_the_empty(
    fake_bybit: FakeBybit,
) -> None:
    adapter = _keyed()
    linear = await _rows(adapter, "linear:account:positions")
    inverse = await _rows(adapter, "inverse:account:positions")

    assert list(linear) == ["BTCUSDT"]
    assert linear["BTCUSDT"]["side"] == "long"
    assert linear["BTCUSDT"]["liquidation_price"] is None
    assert inverse["BTCUSD"]["side"] == "short"
    coins = [
        one.params.get("settleCoin")
        for one in fake_bybit.asked
        if one.path == "/v5/position/list"
    ]
    assert coins == ["USDT", "USDC", None]


async def test_orders_open_and_past_read_as_rows_page_by_page(
    fake_bybit: FakeBybit,
) -> None:
    adapter = _keyed()
    open_orders = await _rows(adapter, "spot:account:open_orders")
    past = await _rows(adapter, "linear:symbol:BTCUSDT:orders")

    assert open_orders["o-1"]["status"] == "new"
    assert open_orders["o-1"]["average_price"] is None
    assert open_orders["o-1"]["stop_price"] is None
    # Three orders on pages of two: Bybit's cursor was followed.
    assert set(past) == {"o-2", "o-3", "o-4"}
    assert past["o-2"]["status"] == "filled"
    history = [one for one in fake_bybit.asked if one.path == "/v5/order/history"]
    assert [one.params.get("cursor") for one in history] == [None, "2"]


async def test_own_trades_are_the_last_week_newest_first(
    fake_bybit: FakeBybit,
) -> None:
    del fake_bybit
    page = await _keyed().fetch(
        FetchRequest(node_id="spot:symbol:BTCUSDT:my_trades", limit=100)
    )

    assert [row[0] for row in page.rows] == ["e-1", "e-2", "e-3", "e-30"]


async def test_inverse_own_trades_keep_their_quantity_in_the_coin(
    fake_bybit: FakeBybit,
) -> None:
    del fake_bybit
    rows = await _rows(_keyed(), "inverse:symbol:BTCUSD:my_trades")

    assert rows["e-1"]["quantity"] == "0.003"
    assert rows["e-1"]["quote_quantity"] == "300"
    assert rows["e-1"]["is_maker"] == "true"


async def test_deposits_and_withdrawals_say_their_state_in_words(
    fake_bybit: FakeBybit,
) -> None:
    del fake_bybit
    adapter = _keyed()
    deposits = await _rows(adapter, "spot:account:deposits")
    withdrawals = await _rows(adapter, "spot:account:withdrawals")

    assert deposits["d1"]["status"] == "success"
    assert deposits["d1"]["network"] == "BTC"
    assert withdrawals["w1"]["status"] == "success"
    assert withdrawals["w1"]["fee"] == "1"


# --- the key's check and report ------------------------------------------------------


async def test_a_read_only_key_checks_plainly(fake_bybit: FakeBybit) -> None:
    result = await _keyed().check_connection()

    assert result.ok
    assert "trade" not in result.message
    assert "/v5/user/query-api" in fake_bybit.signed


async def test_a_key_that_may_trade_is_accepted_and_said(
    fake_bybit: FakeBybit,
) -> None:
    fake_bybit.read_only = 0

    result = await _keyed().check_connection()

    assert result.ok
    assert "trade or move money" in result.message


async def test_a_key_bybit_does_not_know_fails_the_check(
    fake_bybit: FakeBybit,
) -> None:
    del fake_bybit
    result = await _keyed(secret="wrong").check_connection()

    assert not result.ok
    assert result.error_kind == "auth"


async def test_a_testnet_key_reads_the_testnet(fake_bybit: FakeBybit) -> None:
    await _keyed(testnet=True).check_connection()

    assert {one.host for one in fake_bybit.asked} == {"api-testnet.bybit.com"}


async def test_the_key_report_says_what_it_may_do(fake_bybit: FakeBybit) -> None:
    fake_bybit.read_only = 0
    adapter = _keyed()
    section = await adapter.list_children("exchange")
    page = await adapter.fetch(FetchRequest(node_id="report:key"))
    rows = {str(row[0]): str(row[1]) for row in page.rows}

    assert "report:key" in [node.id for node in section]
    assert rows["read only"] == "no"
    assert rows["trade contracts"] == "yes"
    assert rows["move money between wallets or out"] == "no"
    assert rows["limited to listed addresses"] == "yes"
    assert rows["created"] == "2026-01-02T03:04:05Z"
    assert "expires" not in rows


# --- own trades read on (D431) ------------------------------------------------------


async def test_own_trades_are_read_on_by_their_time(fake_bybit: FakeBybit) -> None:
    kept = Kept()
    adapter = BybitAdapter(
        BybitSession(
            BybitMainKey(api_key=SecretStr(API_KEY), api_secret=SecretStr(API_SECRET)),
            None,
        ),
        kept,
    )
    node = "linear:symbol:BTCUSDT:my_trades"
    await kept.write(
        node, READER, Bookmark(positions={"": fake_bybit.my_trade_ms(30) - HOUR_MS})
    )

    span = await adapter.unread(node, READER, "latest")
    first = await adapter.read_on(node, ["id", "price"], span.start, span.line, 2)
    second = await adapter.read_on(node, ["id"], first.after, span.line, 10)

    assert adapter.reads_on(node)
    assert adapter.row_key(node) == ["id"]
    assert span.line.positions[""] == fake_bybit.my_trade_ms(1) + 1
    assert span.count >= 1
    assert [row[0] for row in first.rows] == ["e-30", "e-3"]
    assert not first.done
    assert [row[0] for row in second.rows] == ["e-2", "e-1"]
    assert second.done


async def test_own_trades_are_not_read_on_without_a_key(
    fake_bybit: FakeBybit,
) -> None:
    del fake_bybit
    adapter = BybitAdapter(BybitSession(BybitMain(), None), Kept())

    with pytest.raises(ValueError, match="API key"):
        await adapter.unread("spot:symbol:BTCUSDT:my_trades", READER, "latest")
