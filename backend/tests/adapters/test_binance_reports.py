"""Binance's reports, metrics and search, against a fake Binance (D320)."""

import pytest

from app.adapters.binance.adapter import BinanceAdapter
from app.adapters.binance.options import BinanceMain, BinanceMarketData
from app.adapters.binance.session import BinanceSession
from app.adapters.fetch import FetchRequest
from app.adapters.protocol import NodeNotFound
from app.adapters.registry import capabilities_of
from app.adapters.registry import get as get_adapter_type
from app.adapters.search import NodeSearchRequest, SearchBounds
from tests.adapters.binance_fixture import FakeBinance, install


@pytest.fixture
def fake_binance(monkeypatch: pytest.MonkeyPatch) -> FakeBinance:
    return install(monkeypatch)


def _adapter(market_data: bool = False) -> BinanceAdapter:
    options = BinanceMarketData() if market_data else BinanceMain()
    return BinanceAdapter(BinanceSession(options, None))


async def _report(adapter: BinanceAdapter, key: str) -> dict[str, str]:
    page = await adapter.fetch(FetchRequest(node_id=f"report:{key}"))
    return {row[0] or "": row[1] or "" for row in page.rows}


async def test_the_exchange_section_holds_four_reports(
    fake_binance: FakeBinance,
) -> None:
    del fake_binance
    adapter = _adapter()
    reports = await adapter.list_children("exchange")
    path = await adapter.path_to("report:clock")

    assert [node.id for node in reports] == [
        "report:status",
        "report:clock",
        "report:rate-limit",
        "report:markets",
    ]
    assert [node.id for node in path] == ["exchange", "report:clock"]
    with pytest.raises(NodeNotFound):
        await adapter.list_children("report:gone")


async def test_the_status_says_binance_is_normal_and_every_market_answers(
    fake_binance: FakeBinance,
) -> None:
    del fake_binance
    rows = await _report(_adapter(), "status")

    assert rows == {
        "Endpoint": "Binance",
        "System status": "normal",
        "Spot": "reached",
        "USDⓈ-M futures": "reached",
        "COIN-M futures": "reached",
    }


async def test_another_endpoint_does_not_know_the_system_status(
    fake_binance: FakeBinance,
) -> None:
    rows = await _report(_adapter(market_data=True), "status")

    assert rows["System status"] == "not known on this endpoint"
    assert not any(one.path.endswith("system/status") for one in fake_binance.asked)


async def test_the_rate_limit_says_what_this_minute_used(
    fake_binance: FakeBinance,
) -> None:
    fake_binance.used = 1234
    rows = await _report(_adapter(), "rate-limit")

    # The ping that made the count current weighs one.
    assert rows["Spot: used this minute"] == "1235"
    assert rows["Spot: limit a minute"] == "6000"
    assert rows["Spot: this connection stops at"] == "4800"
    assert rows["USDⓈ-M futures: this connection stops at"] == "1920"
    assert rows["Spot: requests held"] == "no"


async def test_the_markets_count_their_trading_symbols(
    fake_binance: FakeBinance,
) -> None:
    del fake_binance
    rows = await _report(_adapter(), "markets")

    assert rows["Spot: symbols trading"] == "4"
    assert rows["Spot: quote assets"] == "2"
    assert rows["USDⓈ-M futures: symbols trading"] == "2"
    assert rows["COIN-M futures: symbols trading"] == "2"


async def test_the_clock_says_each_market_against_this_server(
    fake_binance: FakeBinance,
) -> None:
    del fake_binance
    rows = await _report(_adapter(), "clock")

    assert set(rows) == {
        "Spot: server time",
        "Spot: ahead of this server",
        "USDⓈ-M futures: server time",
        "USDⓈ-M futures: ahead of this server",
        "COIN-M futures: server time",
        "COIN-M futures: ahead of this server",
        "This server's time",
    }
    assert rows["Spot: ahead of this server"].endswith(" ms")


async def test_metrics_are_the_connections_own_use_of_binance(
    fake_binance: FakeBinance,
) -> None:
    fake_binance.used = 100
    samples = await _adapter().metric_samples()
    by = {(one.metric, one.field, one.label): one.value for one in samples}

    assert by[("reachable", "up", "spot")] == 1.0
    assert by[("weight", "used", "spot")] == 101.0
    assert by[("weight", "ceiling", "usdm")] == 1920.0
    assert ("latency", "ms", "usdm") in by
    assert [preset.key for preset in BinanceAdapter.metric_presets()] == [
        "binance-connection"
    ]


async def test_a_market_that_does_not_answer_is_measured_as_down(
    fake_binance: FakeBinance,
) -> None:
    fake_binance.refuse = (503, {}, {"code": -1, "msg": "?"})
    samples = await _adapter().metric_samples()
    up = {one.label: one.value for one in samples if one.metric == "reachable"}

    assert up == {"spot": 0.0, "usdm": 0.0, "coinm": 0.0}


async def test_a_search_finds_a_symbol_by_its_name_before_its_assets(
    fake_binance: FakeBinance,
) -> None:
    del fake_binance
    found = await _adapter().search_nodes(NodeSearchRequest(query="btc"))
    names = [(match.node.name, match.location) for match in found.matches]

    assert names[:3] == [
        ("BTCUSDT", "Spot / USDT"),
        ("BTCUSDT", "USDⓈ-M futures / USDT"),
        ("BTCUSDT_261225", "USDⓈ-M futures / USDT"),
    ]
    assert ("ETHBTC", "Spot / BTC") in names
    assert names.index(("ETHBTC", "Spot / BTC")) > 2
    assert found.complete


async def test_a_search_keeps_to_the_quote_asset_it_starts_in(
    fake_binance: FakeBinance,
) -> None:
    del fake_binance
    found = await _adapter().search_nodes(
        NodeSearchRequest(node_id="spot:quote:BTC", query="eth")
    )

    assert [match.node.id for match in found.matches] == ["spot:symbol:ETHBTC"]
    assert [one.node_id for one in found.matches[0].ancestors or []] == [
        "spot",
        "spot:quote:BTC",
    ]


async def test_every_symbol_is_a_name_to_keep(fake_binance: FakeBinance) -> None:
    del fake_binance
    batches = [
        batch async for batch in _adapter().enumerate_names(3, SearchBounds.within(10))
    ]
    [batch] = batches

    assert len(batch.names) == 3
    assert batch.notice is not None
    assert batch.names[0].full_name == "BTCUSDT BTC USDT"
    assert batch.names[0].scope == "spot"


def test_the_type_says_it_searches() -> None:
    codes = {
        one.code
        for one in capabilities_of(get_adapter_type("binance"))
        if one.code is not None
    }

    assert "search" in codes
