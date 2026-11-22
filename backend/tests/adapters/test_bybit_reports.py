"""Bybit's Exchange section, metrics, search and Markets folder (D430, D365)."""

import pytest

from app.adapters.bybit.adapter import BybitAdapter
from app.adapters.bybit.options import BybitBytick, BybitMain
from app.adapters.bybit.session import BybitSession
from app.adapters.fetch import FetchRequest
from app.adapters.protocol import NodeNotFound
from app.adapters.registry import capabilities_of
from app.adapters.registry import get as get_adapter_type
from app.adapters.search import NodeSearchRequest, SearchBounds
from tests.adapters.bybit_fixture import FakeBybit, install


@pytest.fixture
def fake_bybit(monkeypatch: pytest.MonkeyPatch) -> FakeBybit:
    return install(monkeypatch)


def _adapter() -> BybitAdapter:
    return BybitAdapter(BybitSession(BybitMain(), None))


async def _report(adapter: BybitAdapter, key: str) -> dict[str, str]:
    page = await adapter.fetch(FetchRequest(node_id=f"report:{key}"))
    return {str(row[0]): str(row[1]) for row in page.rows}


async def test_the_exchange_section_holds_four_reports(fake_bybit: FakeBybit) -> None:
    del fake_bybit
    adapter = _adapter()
    nodes = await adapter.list_children("exchange")
    path = await adapter.path_to("report:clock")

    assert [node.id for node in nodes] == [
        "report:status",
        "report:clock",
        "report:rate-limit",
        "report:markets",
    ]
    assert [node.id for node in path] == ["exchange", "report:clock"]
    with pytest.raises(NodeNotFound):
        await adapter.list_children("report:key")


async def test_the_status_names_the_endpoint_and_every_market_answers(
    fake_bybit: FakeBybit,
) -> None:
    del fake_bybit
    rows = await _report(BybitAdapter(BybitSession(BybitBytick(), None)), "status")

    assert rows["Endpoint"] == "Bybit, through bytick.com"
    assert rows["System status"] == "not known on this endpoint"
    assert rows["Spot"] == rows["Inverse futures"] == "reached"


async def test_the_rate_limit_is_one_budget_said_once(fake_bybit: FakeBybit) -> None:
    del fake_bybit
    rows = await _report(_adapter(), "rate-limit")

    assert rows["All markets: limit in 5 s"] == "600"
    assert rows["All markets: this connection stops at"] == "240"
    assert rows["All markets: requests held"] == "no"
    # Three pings and nothing else were asked in this window.
    assert int(rows["All markets: used in these 5 s"]) >= 3
    assert not any(key.startswith("Spot:") for key in rows)


async def test_the_markets_count_their_trading_symbols(fake_bybit: FakeBybit) -> None:
    del fake_bybit
    rows = await _report(_adapter(), "markets")

    assert rows["Spot: symbols trading"] == "3"
    assert rows["USDT and USDC futures: symbols trading"] == "3"
    assert rows["USDT and USDC futures: quote assets"] == "2"
    assert rows["Inverse futures: symbols trading"] == "2"


async def test_the_clock_reads_each_markets_time(fake_bybit: FakeBybit) -> None:
    rows = await _report(_adapter(), "clock")

    assert "Spot: server time" in rows
    assert rows["Inverse futures: ahead of this server"].endswith("ms")
    assert sum(1 for one in fake_bybit.asked if one.path == "/v5/market/time") == 3


async def test_metrics_say_one_budget_and_each_markets_reach(
    fake_bybit: FakeBybit,
) -> None:
    del fake_bybit
    samples = await _adapter().metric_samples()

    weights = [one for one in samples if one.metric == "weight"]
    assert {one.label for one in weights} == {"address"}
    assert {one.field for one in weights} == {"used", "ceiling"}
    reachable = [one for one in samples if one.metric == "reachable"]
    assert {one.label for one in reachable} == {"spot", "linear", "inverse"}
    assert all(one.value == 1.0 for one in reachable)
    assert [one.key for one in BybitAdapter.metric_presets()] == ["bybit-connection"]


async def test_a_market_that_does_not_answer_is_measured_as_down(
    fake_bybit: FakeBybit,
) -> None:
    fake_bybit.refuse = (502, {})
    samples = await _adapter().metric_samples()

    assert [one.value for one in samples if one.metric == "reachable"] == [0.0] * 3


async def test_a_search_finds_a_symbol_by_its_name_before_its_assets(
    fake_bybit: FakeBybit,
) -> None:
    del fake_bybit
    found = await _adapter().search_nodes(
        NodeSearchRequest(query="eth", limit=10), SearchBounds.within(10)
    )

    ids = [match.node.id for match in found.matches]
    assert ids[0] == "spot:symbol:ETHBTC"
    assert "spot:symbol:ETHUSDT" in ids
    assert found.matches[0].location == "Spot / BTC"


async def test_a_search_keeps_to_the_market_it_starts_in(
    fake_bybit: FakeBybit,
) -> None:
    del fake_bybit
    found = await _adapter().search_nodes(
        NodeSearchRequest(query="btc", limit=10, node_id="inverse"),
        SearchBounds.within(10),
    )

    assert {match.node.id for match in found.matches} == {
        "inverse:symbol:BTCUSD",
        "inverse:symbol:BTCUSDZ26",
    }


async def test_every_symbol_is_a_name_to_keep(fake_bybit: FakeBybit) -> None:
    del fake_bybit
    batches = [
        batch
        async for batch in _adapter().enumerate_names(100, SearchBounds.within(10))
    ]

    names = [name for batch in batches for name in batch.names]
    assert len(names) == 8
    assert {name.scope for name in names} == {"spot", "linear", "inverse"}


async def test_the_markets_folder_lists_each_markets_symbols_as_their_views(
    fake_bybit: FakeBybit,
) -> None:
    del fake_bybit
    adapter = _adapter()
    folders = await adapter.list_children("markets")
    rows = await adapter.list_children("markets:linear")
    path = await adapter.path_to("markets:linear:BTCUSDT-27NOV26")
    start = await adapter.live_start("markets:inverse:BTCUSD", None)

    assert [node.id for node in folders] == [
        "markets:spot",
        "markets:linear",
        "markets:inverse",
    ]
    assert [node.name for node in rows] == ["BTCPERP", "BTCUSDT", "BTCUSDT-27NOV26"]
    assert rows[0].kind == "feed"
    assert [node.id for node in path] == [
        "markets",
        "markets:linear",
        "markets:linear:BTCUSDT-27NOV26",
    ]
    assert start.interval == "1m"


def test_the_type_says_it_searches_and_is_measured() -> None:
    codes = {
        one.code
        for one in capabilities_of(get_adapter_type("bybit"))
        if one.code is not None
    }

    assert {"search", "metrics"} <= codes
