"""A Coinbase Developer Platform key and the account it reads, against a fake
Coinbase (D443)."""

import pytest
from pydantic import SecretStr

from app.adapters.coinbase.adapter import CoinbaseAdapter
from app.adapters.coinbase.options import CoinbaseKey, CoinbaseMain
from app.adapters.coinbase.session import CoinbaseSession
from app.adapters.coinbase.signing import private_key
from app.adapters.fetch import FetchRequest
from app.adapters.protocol import NodeNotFound
from app.adapters.reading_on import Bookmark
from tests.adapters.coinbase_fixture import (
    KEY_NAME,
    PRIVATE_KEY,
    FakeCoinbase,
    install,
)

READER = "dataplayer-link-1"


class Kept:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], Bookmark] = {}

    async def read(self, node_id: str, reader: str) -> Bookmark | None:
        return self.rows.get((node_id, reader))

    async def write(self, node_id: str, reader: str, at: Bookmark) -> None:
        self.rows[(node_id, reader)] = at


@pytest.fixture
def fake_coinbase(monkeypatch: pytest.MonkeyPatch) -> FakeCoinbase:
    return install(monkeypatch)


def _key(secret: str = PRIVATE_KEY) -> CoinbaseKey:
    return CoinbaseKey(api_key=SecretStr(KEY_NAME), api_secret=SecretStr(secret))


def _adapter(secret: str = PRIVATE_KEY, kept: Kept | None = None) -> CoinbaseAdapter:
    return CoinbaseAdapter(CoinbaseSession(_key(secret), None), kept)


async def _rows(
    adapter: CoinbaseAdapter, node_id: str
) -> tuple[list[str], list[list[str | None]]]:
    page = await adapter.fetch(FetchRequest(node_id=node_id))
    return [column.name for column in page.columns], page.rows


def test_a_pasted_key_is_read_with_or_without_its_line_breaks() -> None:
    one_line = PRIVATE_KEY.replace("\n", " ")
    escaped = PRIVATE_KEY.replace("\n", "\\n")

    for text in (PRIVATE_KEY, one_line, escaped):
        assert private_key(text).key_size == 256
    with pytest.raises(ValueError):
        private_key("not a key")


async def test_a_view_only_key_passes_the_check(fake_coinbase: FakeCoinbase) -> None:
    result = await _adapter().check_connection()

    assert result.ok
    assert result.message == "Connection successful"
    assert fake_coinbase.signed == ["/api/v3/brokerage/key_permissions"]
    asked = [one for one in fake_coinbase.asked if one.host == "api.coinbase.com"]
    # The token's uri leaves the query out; the request keeps it.
    assert asked[0].path == "/api/v3/brokerage/key_permissions"


async def test_a_key_that_may_trade_passes_and_is_said_to(
    fake_coinbase: FakeCoinbase,
) -> None:
    fake_coinbase.can_trade = True

    result = await _adapter().check_connection()

    assert result.ok
    assert "trade or move money" in result.message


async def test_another_key_is_refused_in_words(fake_coinbase: FakeCoinbase) -> None:
    del fake_coinbase
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    other = (
        ec.generate_private_key(ec.SECP256R1())
        .private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
        .decode()
    )
    for secret in (other, "not a key"):
        result = await _adapter(secret).check_connection()
        assert not result.ok
        assert result.error_kind == "auth"
        assert "Unauthorized" not in result.message


async def test_a_keyless_connection_has_no_account(fake_coinbase: FakeCoinbase) -> None:
    del fake_coinbase
    adapter = CoinbaseAdapter(CoinbaseSession(CoinbaseMain(), None))

    assert "spot:account" not in [
        node.id for node in await adapter.list_children("spot")
    ]
    with pytest.raises(NodeNotFound):
        await adapter.fetch(FetchRequest(node_id="spot:account:balances"))


async def test_the_account_holds_balances_and_open_orders(
    fake_coinbase: FakeCoinbase,
) -> None:
    del fake_coinbase
    adapter = _adapter()

    children = [node.id for node in await adapter.list_children("spot:account")]
    report = [node.id for node in await adapter.list_children("exchange")]

    assert children == ["spot:account:balances", "spot:account:open_orders"]
    assert "report:key" in report


async def test_balances_are_read_page_by_page_and_empty_ones_left_out(
    fake_coinbase: FakeCoinbase,
) -> None:
    names, rows = await _rows(_adapter(), "spot:account:balances")

    assert names == ["asset", "wallet_balance", "available", "locked"]
    assert rows == [["BTC", "0.5", "0.4", "0.1"], ["USD", "100", "100", "0"]]
    assert fake_coinbase.signed.count("/api/v3/brokerage/accounts") == 3


async def test_orders_say_their_configuration(fake_coinbase: FakeCoinbase) -> None:
    del fake_coinbase
    adapter = _adapter()
    names, open_orders = await _rows(adapter, "spot:account:open_orders")
    _, orders = await _rows(adapter, "spot:symbol:BTC-USD:orders")

    assert [row[0] for row in open_orders] == ["o-1"]
    first = open_orders[0]
    assert first[names.index("price")] == "100.5"
    assert first[names.index("quantity")] == "2"
    assert first[names.index("type")] == "limit"
    assert first[names.index("time")] == "2026-11-20T10:00:00.123Z"
    by_id = {row[0]: row for row in orders}
    # A market order sized in the quote asset has no base quantity.
    assert by_id["o-2"][names.index("quantity")] is None
    assert by_id["o-2"][names.index("average_price")] == "100"


async def test_own_trades_say_a_quote_sized_fill_in_the_quote(
    fake_coinbase: FakeCoinbase,
) -> None:
    del fake_coinbase
    names, rows = await _rows(_adapter(), "spot:symbol:BTC-USD:my_trades")

    by_id = {row[0]: row for row in rows}
    assert by_id["t-1"][names.index("quantity")] == "2"
    assert by_id["t-1"][names.index("quote_quantity")] == "201.0"
    assert by_id["t-2"][names.index("quantity")] is None
    assert by_id["t-2"][names.index("quote_quantity")] == "2"
    assert by_id["t-1"][names.index("is_maker")] == "true"


async def test_the_key_report_says_what_it_may_do(fake_coinbase: FakeCoinbase) -> None:
    del fake_coinbase
    page = await _adapter().fetch(FetchRequest(node_id="report:key"))

    assert {str(row[0]): str(row[1]) for row in page.rows} == {
        "view": "yes",
        "trade": "no",
        "move money in or out": "no",
        "portfolio": "default",
    }


async def test_own_trades_are_read_on_by_time(fake_coinbase: FakeCoinbase) -> None:
    kept = Kept()
    adapter = _adapter(kept=kept)
    node = "spot:symbol:BTC-USD:my_trades"

    span = await adapter.unread(node, READER, "earliest")
    first = await adapter.read_on(node, ["id"], span.start, span.line, 2)
    second = await adapter.read_on(node, ["id"], first.after, span.line, 10)

    assert span.count == 4
    assert span.line.positions[""] == fake_coinbase.my_fill_ms(1) + 1
    assert first.rows == [["t-30"], ["t-3"]]
    assert second.rows == [["t-2"], ["t-1"]]
    assert second.done
    assert adapter.row_key(node) == ["id"]
