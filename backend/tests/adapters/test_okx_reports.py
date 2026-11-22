"""OKX's Exchange section, metrics, search and Markets folder (D436, D365)."""

import pytest

from app.adapters.fetch import FetchRequest
from app.adapters.okx.adapter import OkxAdapter
from app.adapters.okx.options import OkxEea, OkxMain
from app.adapters.okx.session import OkxSession
from app.adapters.registry import capabilities_of
from app.adapters.registry import get as get_adapter_type
from app.adapters.resources import Pooling, ResourceStore
from app.adapters.search import NodeSearchRequest, SearchBounds
from tests.adapters.okx_fixture import FakeOkx, install


@pytest.fixture
def fake_okx(monkeypatch: pytest.MonkeyPatch) -> FakeOkx:
    return install(monkeypatch)


def _adapter() -> OkxAdapter:
    return OkxAdapter(OkxSession(OkxMain(), None))


def _kept_adapter() -> OkxAdapter:
    store = ResourceStore(max_entries=4, max_idle_seconds=60)
    return OkxAdapter(OkxSession(OkxMain(), Pooling(store, "okx-reports")))


async def _report(adapter: OkxAdapter, key: str) -> dict[str, str]:
    page = await adapter.fetch(FetchRequest(node_id=f"report:{key}"))
    return {str(row[0]): str(row[1]) for row in page.rows}


async def test_the_exchange_section_holds_four_reports(fake_okx: FakeOkx) -> None:
    del fake_okx
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


async def test_the_status_names_the_endpoint_and_okx_maintenance(
    fake_okx: FakeOkx,
) -> None:
    rows = await _report(OkxAdapter(OkxSession(OkxEea(), None)), "status")

    assert rows["Endpoint"] == "OKX Europe"
    assert rows["System status"] == "normal"
    assert rows["Spot"] == rows["Inverse futures"] == "reached"

    fake_okx.maintenance = True
    rows = await _report(_adapter(), "status")
    assert rows["System status"] == "maintenance"


async def test_the_rate_limit_is_said_a_path_at_a_time(fake_okx: FakeOkx) -> None:
    del fake_okx
    adapter = _kept_adapter()
    await adapter.fetch(FetchRequest(node_id="spot:tickers"))
    rows = await _report(adapter, "rate-limit")

    assert rows["market/tickers: limit in 2 s"] == "20"
    assert rows["market/tickers: this connection stops at"] == "8"
    assert rows["public/time: limit in 2 s"] == "10"
    assert int(rows["public/time: used in these 2 s"]) >= 3
    assert rows["public/instruments?SPOT: requests held"] == "no"
    assert not any(key.startswith("Spot:") for key in rows)


async def test_the_markets_count_their_live_symbols(fake_okx: FakeOkx) -> None:
    del fake_okx
    rows = await _report(_adapter(), "markets")

    assert rows["Spot: symbols trading"] == "3"
    assert rows["USDT and USDC futures: symbols trading"] == "3"
    assert rows["USDT and USDC futures: quote assets"] == "2"
    assert rows["Inverse futures: symbols trading"] == "2"


async def test_the_clock_reads_each_markets_time(fake_okx: FakeOkx) -> None:
    rows = await _report(_adapter(), "clock")

    assert "Spot: server time" in rows
    assert rows["Inverse futures: ahead of this server"].endswith("ms")
    time_asked = [one for one in fake_okx.asked if one.path == "/api/v5/public/time"]
    assert len(time_asked) == 3


async def test_metrics_say_each_paths_budget_and_each_markets_reach(
    fake_okx: FakeOkx,
) -> None:
    del fake_okx
    adapter = _kept_adapter()
    await adapter.fetch(FetchRequest(node_id="spot:tickers"))
    samples = await adapter.metric_samples()

    weights = [one for one in samples if one.metric == "weight"]
    assert {"market/tickers", "public/time"} <= {one.label for one in weights}
    reachable = [one for one in samples if one.metric == "reachable"]
    assert {one.label for one in reachable} == {"spot", "linear", "inverse"}
    assert all(one.value == 1.0 for one in reachable)
    assert [one.key for one in OkxAdapter.metric_presets()] == ["okx-connection"]


async def test_a_market_that_does_not_answer_is_measured_as_down(
    fake_okx: FakeOkx,
) -> None:
    fake_okx.refuse = (503, {"code": "50001", "msg": "Service unavailable"})
    samples = await _adapter().metric_samples()

    assert [one.value for one in samples if one.metric == "reachable"] == [0.0] * 3


async def test_a_search_finds_a_symbol_by_its_name_before_its_assets(
    fake_okx: FakeOkx,
) -> None:
    del fake_okx
    found = await _adapter().search_nodes(
        NodeSearchRequest(query="eth", limit=10), SearchBounds.within(10)
    )

    ids = [match.node.id for match in found.matches]
    assert ids[0] == "spot:symbol:ETH-BTC"
    assert "spot:symbol:ETH-USDT" in ids
    assert found.matches[0].location == "Spot / BTC"


async def test_a_search_keeps_to_the_market_it_starts_in(fake_okx: FakeOkx) -> None:
    del fake_okx
    found = await _adapter().search_nodes(
        NodeSearchRequest(query="btc", limit=10, node_id="inverse"),
        SearchBounds.within(10),
    )

    assert {match.node.id for match in found.matches} == {
        "inverse:symbol:BTC-USD-SWAP",
        "inverse:symbol:BTC-USD-261225",
    }


async def test_every_live_symbol_is_a_name_to_keep(fake_okx: FakeOkx) -> None:
    del fake_okx
    names = [
        name
        async for batch in _adapter().enumerate_names(100, SearchBounds.within(10))
        for name in batch.names
    ]

    assert len(names) == 8
    assert {name.scope for name in names} == {"spot", "linear", "inverse"}


async def test_the_markets_folder_lists_each_markets_symbols_as_their_views(
    fake_okx: FakeOkx,
) -> None:
    del fake_okx
    adapter = _adapter()
    folders = await adapter.list_children("markets")
    rows = await adapter.list_children("markets:linear")
    path = await adapter.path_to("markets:linear:BTC-USDT-261225")

    assert [node.id for node in folders] == [
        "markets:spot",
        "markets:linear",
        "markets:inverse",
    ]
    assert [node.name for node in rows] == [
        "BTC-USDC-SWAP",
        "BTC-USDT-261225",
        "BTC-USDT-SWAP",
    ]
    assert rows[0].kind == "feed"
    assert [node.id for node in path] == [
        "markets",
        "markets:linear",
        "markets:linear:BTC-USDT-261225",
    ]


def test_the_type_says_it_searches_and_is_measured() -> None:
    codes = {
        one.code
        for one in capabilities_of(get_adapter_type("okx"))
        if one.code is not None
    }

    assert {"search", "metrics"} <= codes
