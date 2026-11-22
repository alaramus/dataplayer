"""An OKX key and the account it reads, against a fake OKX (D437)."""

import pytest
from pydantic import SecretStr

from app.adapters.fetch import FetchRequest
from app.adapters.okx.adapter import OkxAdapter
from app.adapters.okx.options import OkxDemoKey, OkxMain, OkxMainKey
from app.adapters.okx.session import OkxSession
from app.adapters.protocol import NodeNotFound
from app.adapters.reading_on import Bookmark
from tests.adapters.okx_fixture import API_KEY, API_SECRET, PASSPHRASE, FakeOkx, install

READER = "dataplayer-link-1"


class Kept:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], Bookmark] = {}

    async def read(self, node_id: str, reader: str) -> Bookmark | None:
        return self.rows.get((node_id, reader))

    async def write(self, node_id: str, reader: str, at: Bookmark) -> None:
        self.rows[(node_id, reader)] = at


@pytest.fixture
def fake_okx(monkeypatch: pytest.MonkeyPatch) -> FakeOkx:
    return install(monkeypatch)


def _key(secret: str = API_SECRET, passphrase: str = PASSPHRASE) -> OkxMainKey:
    return OkxMainKey(
        api_key=SecretStr(API_KEY),
        api_secret=SecretStr(secret),
        api_passphrase=SecretStr(passphrase),
    )


def _adapter(
    options: OkxMainKey | OkxDemoKey | None = None, kept: Kept | None = None
) -> OkxAdapter:
    return OkxAdapter(OkxSession(options or _key(), None), kept)


async def _rows(
    adapter: OkxAdapter, node_id: str
) -> tuple[list[str], list[list[str | None]]]:
    page = await adapter.fetch(FetchRequest(node_id=node_id))
    return [column.name for column in page.columns], page.rows


async def test_a_read_only_key_passes_the_check(fake_okx: FakeOkx) -> None:
    result = await _adapter().check_connection()

    assert result.ok
    assert result.message == "Connection successful"
    assert fake_okx.signed == ["/api/v5/account/config"]
    asked = [one for one in fake_okx.asked if one.path == "/api/v5/account/config"]
    assert asked[0].headers["ok-access-passphrase"] == PASSPHRASE


async def test_a_key_that_may_trade_passes_and_is_said_to(fake_okx: FakeOkx) -> None:
    fake_okx.perm = "read_only,trade"

    result = await _adapter().check_connection()

    assert result.ok
    assert "trade or move money" in result.message


async def test_a_wrong_passphrase_or_secret_is_refused_in_words(
    fake_okx: FakeOkx,
) -> None:
    del fake_okx
    for options in (_key(passphrase="wrong"), _key(secret="wrong")):
        result = await _adapter(options).check_connection()
        assert not result.ok
        assert result.error_kind == "auth"
        assert "passphrase" in result.message
        assert "Invalid" not in result.message


async def test_a_stale_time_is_measured_again_and_sent_once_more(
    fake_okx: FakeOkx,
) -> None:
    fake_okx.stale = 1

    result = await _adapter().check_connection()

    assert result.ok
    assert fake_okx.signed == ["/api/v5/account/config"]


async def test_demo_signs_with_the_demo_header(fake_okx: FakeOkx) -> None:
    options = OkxDemoKey(
        api_key=SecretStr(API_KEY),
        api_secret=SecretStr(API_SECRET),
        api_passphrase=SecretStr(PASSPHRASE),
    )
    await _adapter(options).check_connection()

    signed = [one for one in fake_okx.asked if "ok-access-sign" in one.headers]
    assert signed[0].headers["x-simulated-trading"] == "1"


async def test_a_keyless_connection_has_no_account(fake_okx: FakeOkx) -> None:
    del fake_okx
    adapter = OkxAdapter(OkxSession(OkxMain(), None))

    children = [node.id for node in await adapter.list_children("spot")]
    assert "spot:account" not in children
    with pytest.raises(NodeNotFound):
        await adapter.fetch(FetchRequest(node_id="spot:account:balances"))


async def test_each_market_holds_its_account(fake_okx: FakeOkx) -> None:
    del fake_okx
    adapter = _adapter()

    spot = [node.id for node in await adapter.list_children("spot:account")]
    linear = [node.id for node in await adapter.list_children("linear:account")]
    report = [node.id for node in await adapter.list_children("exchange")]

    assert spot == [
        "spot:account:balances",
        "spot:account:open_orders",
        "spot:account:deposits",
        "spot:account:withdrawals",
    ]
    assert linear == [
        "linear:account:balances",
        "linear:account:positions",
        "linear:account:open_orders",
    ]
    assert "report:key" in report


async def test_balances_leave_out_what_is_empty(fake_okx: FakeOkx) -> None:
    del fake_okx
    names, rows = await _rows(_adapter(), "linear:account:balances")

    assert [row[0] for row in rows] == ["BTC", "USDT"]
    assert rows[0][names.index("locked")] == "0.1"


async def test_positions_keep_to_the_market_and_say_their_worth(
    fake_okx: FakeOkx,
) -> None:
    del fake_okx
    adapter = _adapter()
    names, linear = await _rows(adapter, "linear:account:positions")
    _, inverse = await _rows(adapter, "inverse:account:positions")

    # A net position of -3 contracts of 0.01 BTC is short 0.03 BTC; the empty
    # one is left out, and the inverse one is the other market's.
    assert linear == [
        [
            "BTC-USDT-SWAP",
            "short",
            "0.03",
            "70000",
            "74000",
            "12",
            None,
            "2220",
            linear[0][names.index("update_time")],
        ]
    ]
    assert [row[:3] for row in inverse] == [["BTC-USD-SWAP", "long", "200"]]


async def test_open_orders_keep_to_the_markets_symbols(fake_okx: FakeOkx) -> None:
    del fake_okx
    adapter = _adapter()
    _, spot = await _rows(adapter, "spot:account:open_orders")
    _, linear = await _rows(adapter, "linear:account:open_orders")

    assert [row[0] for row in spot] == ["11"]
    assert [row[0] for row in linear] == ["12"]
    assert linear[0][3] == "post only"


async def test_a_symbols_orders_leave_a_quote_sized_quantity_empty(
    fake_okx: FakeOkx,
) -> None:
    names, rows = await _rows(_adapter(), "spot:symbol:BTC-USDT:orders")

    history = [one for one in fake_okx.asked if one.path.endswith("orders-history")]
    assert history[0].params["instType"] == "SPOT"
    by_id = {row[0]: row for row in rows}
    assert by_id["21"][names.index("quantity")] is None
    assert by_id["21"][names.index("executed")] == "2"
    assert by_id["22"][names.index("quantity")] == "2"


async def test_own_trades_are_the_last_three_days_a_contract_in_the_coin(
    fake_okx: FakeOkx,
) -> None:
    del fake_okx
    names, rows = await _rows(_adapter(), "linear:symbol:BTC-USDT-SWAP:my_trades")

    assert [row[0] for row in rows] == ["t-1", "t-2", "t-3", "t-30"]
    assert rows[0][names.index("quantity")] == "0.03"
    assert rows[0][names.index("is_maker")] == "true"
    assert rows[0][names.index("side")] == "sell"


async def test_deposits_and_withdrawals_say_their_state_in_words(
    fake_okx: FakeOkx,
) -> None:
    del fake_okx
    adapter = _adapter()
    names, deposits = await _rows(adapter, "spot:account:deposits")
    _, withdrawals = await _rows(adapter, "spot:account:withdrawals")

    assert deposits[0][names.index("status")] == "successful"
    assert withdrawals[0][5] == "success"


async def test_the_key_report_says_what_it_may_do(fake_okx: FakeOkx) -> None:
    fake_okx.perm = "read_only,withdraw"
    page = await _adapter().fetch(FetchRequest(node_id="report:key"))
    rows = {str(row[0]): str(row[1]) for row in page.rows}

    assert rows == {
        "read only": "no",
        "trade": "no",
        "withdraw": "yes",
        "limited to listed addresses": "yes",
        "label": "reader",
    }


async def test_own_trades_are_read_on_by_time(fake_okx: FakeOkx) -> None:
    kept = Kept()
    adapter = _adapter(kept=kept)
    node = "linear:symbol:BTC-USDT-SWAP:my_trades"

    span = await adapter.unread(node, READER, "earliest")
    block = await adapter.read_on(node, ["id"], span.start, span.line, 10)

    assert span.fresh
    assert span.line.positions[""] == fake_okx.my_trade_ms(1) + 1
    assert [row[0] for row in block.rows] == ["t-30", "t-3", "t-2", "t-1"]
    assert block.done
    assert adapter.row_key(node) == ["id"]
