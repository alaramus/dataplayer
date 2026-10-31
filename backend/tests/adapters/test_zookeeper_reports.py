"""The server's reports and metrics, finding znodes, and exporting children (D301)."""

from collections.abc import AsyncIterator

import pytest

from app.adapters.catalog import ReportNode, ZnodeNode
from app.adapters.export import ExportRequest
from app.adapters.fetch import FetchRequest, Sort
from app.adapters.search import NodeSearchRequest, SearchBounds
from app.adapters.zookeeper.adapter import ZookeeperAdapter
from app.adapters.zookeeper.metrics import samples_of
from app.adapters.zookeeper.reports import (
    REPORTS,
    SECTION_ID,
    _connections,
    _watches,
    refused,
)
from tests.adapters.zookeeper_fixture import (
    CHILDREN,
    adapter,
    build_tree,
    digest_options,
    new_root,
    on_server,
    remove_tree,
)


@pytest.fixture(scope="module")
async def root() -> AsyncIterator[str]:
    path = new_root()
    await on_server(lambda client: build_tree(client, path))
    yield path
    await on_server(lambda client: remove_tree(client, path))


# --- reports -----------------------------------------------------------------


async def test_the_servers_section_comes_first_at_the_top() -> None:
    top = await adapter().list_children(None)
    assert isinstance(top[0], ReportNode) and top[0].id == SECTION_ID
    reports = await adapter().list_children(SECTION_ID)
    assert [node.id for node in reports] == [report.node_id for report in REPORTS]
    # Not a level of znodes: confined to a root path, the section is still there.
    assert (await adapter(chroot="/zookeeper").list_children(None))[0].id == SECTION_ID


async def test_srvr_is_read_as_settings_and_values() -> None:
    page = await adapter().fetch(FetchRequest(node_id=f"{SECTION_ID}/srvr", limit=100))
    rows = {row[0]: row[1] for row in page.rows}
    assert rows["Mode"] == "standalone"
    assert int(rows["Node count"] or 0) > 0
    assert not page.update_supported and not page.record_supported


async def test_mntr_and_conf_are_read_whole() -> None:
    source = adapter()
    mntr = await source.fetch(FetchRequest(node_id=f"{SECTION_ID}/mntr", limit=1000))
    assert "zk_znode_count" in {row[0] for row in mntr.rows}
    conf = await source.fetch(FetchRequest(node_id=f"{SECTION_ID}/conf", limit=1000))
    assert {row[0]: row[1] for row in conf.rows}["clientPort"] == "2181"


def test_a_word_the_whitelist_leaves_out_is_said_as_such() -> None:
    assert refused("mntr is not executed because it is not in the whitelist.\n")
    assert not refused("zk_version\t3.9.6\n")


def test_connections_and_watches_are_split_where_the_server_writes_them() -> None:
    cons = _connections(" /10.0.0.1:4242[1](queued=0,recved=3,sent=3)\n\n")
    assert cons == [("/10.0.0.1:4242", "[1](queued=0,recved=3,sent=3)")]
    assert _watches("2 connections watching 5 paths\nTotal watches:7\n") == [
        ("2 connections watching 5 paths", ""),
        ("Total watches", "7"),
    ]


async def test_a_report_offers_no_actions() -> None:
    assert await adapter().available(f"{SECTION_ID}/srvr") == []


# --- metrics -----------------------------------------------------------------


async def test_metrics_are_read_from_mntr() -> None:
    samples = await adapter().metric_samples()
    by_key = {(one.metric, one.field): one for one in samples}
    assert by_key[("znodes", "count")].value > 0
    assert by_key[("packets", "received")].counter
    assert by_key[("latency", "avg")].unit == "ms"


def test_a_value_that_is_not_a_number_is_left_out() -> None:
    samples = samples_of("zk_znode_count\tmany\nzk_watch_count\t3\n")
    assert [(one.metric, one.field, one.value) for one in samples] == [("watches", "count", 3.0)]


# --- search ------------------------------------------------------------------


async def test_a_znode_is_found_by_name_with_the_levels_above_it(root: str) -> None:
    result = await adapter().search_nodes(NodeSearchRequest(node_id=root, query="item 07"))
    # `secret` may not be listed anonymously, and the answer says so.
    assert not result.complete and result.notice is not None
    signed_in = await ZookeeperAdapter(digest_options()).search_nodes(
        NodeSearchRequest(node_id=root, query="item 07")
    )
    assert signed_in.complete
    [match] = [one for one in result.matches if one.node.id == f"{root}/services/item-07"]
    assert isinstance(match.node, ZnodeNode)
    assert match.parent_id == f"{root}/services"
    assert match.ancestors is not None
    assert [one.node_id for one in match.ancestors] == [root, f"{root}/services"]


async def test_a_search_says_when_more_matched_than_it_kept(root: str) -> None:
    result = await adapter().search_nodes(NodeSearchRequest(node_id=root, query="item", limit=5))
    assert len(result.matches) == 5
    assert not result.complete and result.notice is not None


async def test_a_search_below_a_level_that_is_gone_is_not_found(root: str) -> None:
    from app.adapters.protocol import NodeNotFound

    with pytest.raises(NodeNotFound):
        await adapter().search_nodes(NodeSearchRequest(node_id=f"{root}/gone", query="x"))


async def test_every_name_is_read_for_a_kept_list(root: str) -> None:
    names: list[str] = []
    async for batch in adapter(chroot=root).enumerate_names(10_000, SearchBounds.within(60)):
        names.extend(one.node.id for one in batch.names)
    assert "/services/item-24" in names and "/config" in names
    assert len([one for one in names if one.startswith("/services/")]) == CHILDREN + 1


# --- export ------------------------------------------------------------------


async def test_every_child_is_exported_in_the_columns_asked_for(root: str) -> None:
    rows: list[list[str | None]] = []
    async for batch in adapter().export_rows(
        ExportRequest(node_id=f"{root}/services", columns=["name", "data"])
    ):
        rows.extend(batch.rows)
    assert len(rows) == CHILDREN
    assert rows[0] == ["item-00", "value 0"]


async def test_an_export_asked_to_sort_is_refused(root: str) -> None:
    with pytest.raises(ValueError):
        async for _ in adapter().export_rows(
            ExportRequest(node_id=root, columns=["name"], sort=[Sort(column="name")])
        ):
            pass


async def test_a_report_is_exported_too() -> None:
    rows: list[list[str | None]] = []
    async for batch in adapter().export_rows(
        ExportRequest(node_id=f"{SECTION_ID}/conf", columns=["Setting", "Value"])
    ):
        rows.extend(batch.rows)
    assert ["clientPort", "2181"] in rows
