"""A Cassandra or ScyllaDB cluster as a source type (D340–D342).

Every test that needs a server runs against both: one source type speaks to
both, and they differ where the catalog looks and in what a filter accepts.
"""

import uuid
from collections.abc import AsyncIterator

import pytest
from pydantic import SecretStr

from app.adapters import registry
from app.adapters.cassandra import session as cql_session
from app.adapters.cassandra.adapter import CassandraAdapter
from app.adapters.cassandra.options import CassandraNoPassword, CassandraUserPassword
from app.adapters.cassandra.session import (
    PageStates,
    compose_url_with_password,
    options_from_url,
    read_profile,
)
from app.adapters.cassandra.types import duration_text
from app.adapters.catalog import SchemaNode, TableNode, ViewNode
from app.adapters.content import ContentRequest, SqlContent
from app.adapters.fetch import FetchRequest, InFilter, ScalarFilter, Sort
from app.adapters.protocol import (
    DataAdapter,
    NodeNotFound,
    SupportsCatalog,
    SupportsContent,
    SupportsFetch,
    SupportsNodePath,
    SupportsNodeSummary,
    SupportsRelationModel,
    SupportsRelationModelBatch,
    SupportsUpdate,
)
from app.adapters.query import SupportsQuery
from app.adapters.relation import PrimaryKey, RelationModelsRequest
from app.adapters.resources import Pooling, ResourceStore
from app.adapters.summary import RelationContents
from tests.adapters.cassandra_fixture import (
    KEYSPACE,
    MANY_ROWS,
    ODD,
    TARGETS,
    Target,
    build,
    tear_down,
)

ITEMS = f"{KEYSPACE}.items"
MANY = f"{KEYSPACE}.many"
VIEW = f"{KEYSPACE}.items_by_ok"


@pytest.fixture(params=TARGETS, ids=lambda target: target.flavour, scope="module")
async def target(request: pytest.FixtureRequest) -> AsyncIterator[Target]:
    chosen: Target = request.param
    chosen.server.require()
    await build(chosen)
    yield chosen
    await tear_down(chosen)


def _unreachable() -> CassandraAdapter:
    return CassandraAdapter(
        CassandraUserPassword(
            host="127.0.0.1",
            port=1,
            user="cassandra",
            password=SecretStr("secret-password"),
        )
    )


# --- What the type is ----------------------------------------------------


def test_the_type_is_registered_with_a_card_for_each_product() -> None:
    kind = registry.get("cassandra")

    assert kind.adapter_class is CassandraAdapter
    assert [(face.key, face.title) for face in kind.faces] == [
        ("cassandra", "Apache Cassandra"),
        ("scylladb", "ScyllaDB"),
    ]


def test_it_claims_only_what_it_does() -> None:
    adapter = _unreachable()
    for capability in (
        DataAdapter,
        SupportsCatalog,
        SupportsNodePath,
        SupportsFetch,
        SupportsRelationModel,
        SupportsRelationModelBatch,
        SupportsNodeSummary,
        SupportsContent,
    ):
        assert isinstance(adapter, capability)
    assert isinstance(adapter, SupportsQuery)
    assert isinstance(adapter, SupportsUpdate)


def test_a_server_is_read_as_its_product_and_number() -> None:
    cassandra = read_profile("5.0.9", None)
    scylla = read_profile("3.0.8", "2026.3.5-0.20261103.76a3b0773cfe")

    assert (cassandra.product, cassandra.text, cassandra.supported) == (
        "Cassandra",
        "5.0.9",
        True,
    )
    # ScyllaDB's release_version is a compatibility number; its own is elsewhere.
    assert (scylla.product, scylla.text, scylla.supported) == (
        "ScyllaDB",
        "2026.3.5",
        True,
    )
    assert not read_profile("3.11.17", None).supported
    assert read_profile("4.0.0", None).supported
    assert not read_profile("3.0.8", "5.2.9").supported


# --- Addresses -------------------------------------------------------------


def test_a_connection_string_fills_the_form() -> None:
    assert options_from_url(
        "cassandra://ann%40corp:p%2Fw@db.example.com:9142/sales?ssl=true&consistency=local_quorum"
    ) == {
        "host": "db.example.com",
        "port": 9142,
        "secure": True,
        "keyspace": "sales",
        "consistency": "LOCAL_QUORUM",
        "auth_method": "user_password",
        "user": "ann@corp",
        "password": "p/w",
    }
    assert options_from_url("scylla://node1")["auth_method"] == "no_password"
    with pytest.raises(ValueError):
        options_from_url("mysql://db.example.com")


def test_the_address_shown_carries_no_password() -> None:
    adapter = CassandraAdapter(
        CassandraUserPassword(
            host="db.example.com", user="ann", password=SecretStr("secret-password")
        )
    )

    assert adapter.connection_string() == "cassandra://ann@db.example.com:9042"
    assert "secret-password" not in adapter.connection_string()
    assert (
        compose_url_with_password(
            host="db.example.com", port=9042, user="ann", password="p/w"
        )
        == "cassandra://ann:p%2Fw@db.example.com:9042"
    )


def test_a_draft_names_its_address_before_it_is_saved() -> None:
    assert (
        CassandraAdapter.draft_connection_string(
            {"auth_method": "no_password", "host": "h", "port": "9043", "keyspace": "k"}
        )
        == "cassandra://h:9043/k"
    )


# --- Durations and page states, without a server ------------------------------


def test_a_duration_is_written_in_cql_units() -> None:
    from cassandra.util import Duration

    assert duration_text(Duration(14, 2, 3_723_004_005_006)) == "1y2mo2d1h2m3s4ms5us6ns"
    assert duration_text(Duration(0, 0, 0)) == "0s"
    assert duration_text(Duration(0, -1, 0)) == "-1d"


def test_page_states_go_on_from_the_nearest_one_before() -> None:
    states = PageStates(max_reads=2, max_positions=2)
    states.keep("a", 100, b"x")
    states.keep("a", 200, b"y")

    assert states.nearest("a", 250) == (200, b"y")
    assert states.nearest("a", 150) == (100, b"x")
    assert states.nearest("a", 50) == (0, None)
    states.keep("a", 300, b"z")
    # The oldest position goes first.
    assert states.nearest("a", 150) == (0, None)
    states.keep("b", 1, b"1")
    states.keep("c", 1, b"1")
    assert states.nearest("a", 300) == (0, None)


# --- Connecting -----------------------------------------------------------


async def test_the_check_says_the_server_answers(target: Target) -> None:
    result = await target.adapter().check_connection()

    assert result.ok, result.message
    assert result.latency_ms is not None


async def test_a_wrong_password_is_said_without_it(target: Target) -> None:
    result = await target.adapter(
        password=SecretStr("not-the-password")
    ).check_connection()

    assert (result.ok, result.error_kind) == (False, "auth")
    assert "not-the-password" not in result.message


async def test_a_missing_password_is_asked_for(target: Target) -> None:
    options = target.options()
    adapter = CassandraAdapter(
        CassandraNoPassword(host=options.host, port=options.port)
    )

    result = await adapter.check_connection()

    assert (result.ok, result.error_kind) == (False, "auth")


async def test_a_missing_keyspace_is_said(target: Target) -> None:
    result = await target.adapter(keyspace="no_such_keyspace").check_connection()

    assert (result.ok, result.error_kind) == (False, "config")


async def test_an_unreachable_node_is_a_network_failure() -> None:
    result = await _unreachable().check_connection()

    assert (result.ok, result.error_kind) == (False, "network")
    assert "secret-password" not in result.message


async def test_the_server_says_which_product_it_is(target: Target) -> None:
    version = (await target.adapter().source_features()).server_version

    assert version is not None
    assert version.startswith("ScyllaDB " if target.scylla else "Cassandra ")


# --- The catalog -----------------------------------------------------------


async def test_keyspaces_are_listed_with_the_servers_own_last(target: Target) -> None:
    roots = await target.adapter().list_children(None)

    names = [node.name for node in roots]
    assert KEYSPACE in names
    keyspaces = [node for node in roots if isinstance(node, SchemaNode)]
    assert keyspaces and all(node.term == "keyspace" for node in keyspaces)
    # The Cluster section of reports comes after them (D349).
    assert roots[-1].id == "\\cluster"
    system = [node.is_system for node in keyspaces]
    assert system == sorted(system)
    assert next(node for node in roots if node.name == "system_schema").is_system
    if target.scylla:
        # ScyllaDB makes `audit` itself.
        audit = [node for node in roots if node.name == "audit"]
        assert all(node.is_system for node in audit if isinstance(node, SchemaNode))
    else:
        # Cassandra's virtual tables are a keyspace of their own.
        assert "system_views" in names


async def test_the_connections_own_keyspace_comes_first(target: Target) -> None:
    roots = await target.adapter(keyspace=KEYSPACE).list_children(None)

    assert roots[0].name == KEYSPACE


async def test_a_keyspace_lists_its_tables_and_views(target: Target) -> None:
    nodes = await target.adapter().list_children(KEYSPACE)

    kinds = {node.name: type(node) for node in nodes}
    assert kinds == {
        "items": TableNode,
        "items_by_ok": ViewNode,
        "many": TableNode,
        ODD: TableNode,
    }
    view = next(node for node in nodes if isinstance(node, ViewNode))
    assert view.is_materialized


async def test_a_path_is_confirmed_on_the_server(target: Target) -> None:
    adapter = target.adapter()

    path = await adapter.path_to(f"{KEYSPACE}.{ODD}")

    assert [node.name for node in path] == [KEYSPACE, ODD]
    with pytest.raises(NodeNotFound):
        await adapter.path_to(f"{KEYSPACE}.nothing")
    with pytest.raises(NodeNotFound):
        await adapter.path_to("no_such_keyspace")


# --- The relation model ------------------------------------------------------


async def test_the_key_is_the_partition_key_then_the_clustering_columns(
    target: Target,
) -> None:
    model = await target.adapter().relation_model(ITEMS)

    assert model.kind == "table"
    assert model.comment == "Things"
    assert [column.name for column in model.columns[:3]] == ["shop", "id", "at"]
    assert model.constraints == [
        PrimaryKey(name="PRIMARY KEY", columns=["shop", "id", "at"])
    ]
    by_name = {column.name: column for column in model.columns}
    assert by_name["shop"].comment == "Partition key"
    assert by_name["at"].comment == "Clustering column, DESC"
    assert by_name["note"].comment == "Static: one value for the whole partition"
    assert not by_name["id"].nullable and by_name["label"].nullable
    assert by_name["tags"].type.category == "array"
    assert by_name["attrs"].type.category == "json"
    assert by_name["home"].type.category == "composite"
    assert by_name["amount"].type.category == "number"
    assert [index.name for index in model.indexes] == ["items_label"]
    assert model.indexes[0].columns == ["label"]


async def test_a_materialized_view_is_described(target: Target) -> None:
    model = await target.adapter().relation_model(VIEW)

    assert model.kind == "materialized_view"
    assert model.constraints == [
        PrimaryKey(name="PRIMARY KEY", columns=["ok", "shop", "id", "at"])
    ]


async def test_models_are_read_for_several_relations_at_once(target: Target) -> None:
    models = await target.adapter().relation_models_for_nodes(
        RelationModelsRequest(node_ids=[ITEMS, MANY, f"{KEYSPACE}.nothing"])
    )

    assert sorted(model.name for model in models) == ["items", "many"]


async def test_a_missing_relation_is_not_found(target: Target) -> None:
    with pytest.raises(NodeNotFound):
        await target.adapter().relation_model(f"{KEYSPACE}.nothing")


# --- Values ------------------------------------------------------------------


async def test_every_value_crosses_as_text(target: Target) -> None:
    page = await target.adapter().fetch(
        FetchRequest.model_validate(
            {"node_id": ITEMS, "filters": [{"column": "id", "op": "eq", "value": "1"}]}
        )
    )

    row = dict(zip([column.name for column in page.columns], page.rows[0], strict=True))
    assert row == {
        "shop": "north",
        "id": "1",
        "at": "2024-01-02T03:04:05.120000+00:00",
        "label": "alpha",
        "amount": "12345678901234567890.0123456789",
        "big": "123456789012345678901234567890",
        "ratio": "0.1",
        "small": "1.5",
        "ok": "true",
        "uid": "00000000-0000-0000-0000-000000000001",
        "tid": "50554d6e-29bb-11e5-b345-feff819cdc9f",
        "addr": "10.0.0.1",
        "day": "2024-02-03",
        "clock": "12:30:00.000000001",
        "span": "1mo2d3h4m5s6ms7us8ns",
        "data": "0x00FF",
        "tags": '["a","b\\"c"]',
        "uniq": "[1,3]",
        "attrs": '{"k":1}',
        "counts": '[[2,"two"]]',
        "pair": '[1,"x"]',
        "home": '{"street":"Main","zip":10}',
        "note": "North shop",
    }


async def test_nan_and_null_are_told_apart(target: Target) -> None:
    page = await target.adapter().fetch(
        FetchRequest.model_validate(
            {"node_id": ITEMS, "filters": [{"column": "id", "op": "eq", "value": "3"}]}
        )
    )

    row = dict(zip([column.name for column in page.columns], page.rows[0], strict=True))
    assert row["ratio"] == "NaN"
    assert row["amount"] is None


# --- Pages -------------------------------------------------------------------


async def test_pages_by_offset_cover_every_row_once(target: Target) -> None:
    store = ResourceStore(max_entries=4, max_idle_seconds=600)
    adapter = CassandraAdapter(
        target.options(), Pooling(store=store, connector_id=uuid.uuid4())
    )
    try:
        seen: list[str | None] = []
        offset = 0
        while True:
            page = await adapter.fetch(
                FetchRequest(node_id=MANY, limit=100, offset=offset)
            )
            seen.extend(row[0] for row in page.rows)
            offset += 100
            if not page.has_more:
                break
        assert len(seen) == MANY_ROWS
        assert len(set(seen)) == MANY_ROWS
        # A jump to a page read before goes on from its kept state.
        again = await adapter.fetch(FetchRequest(node_id=MANY, limit=100, offset=100))
        assert [row[0] for row in again.rows] == seen[100:200]
    finally:
        await store.aclose()


async def test_an_offset_no_state_is_near_is_reached_by_reading(target: Target) -> None:
    adapter = target.adapter()

    whole = await adapter.fetch(FetchRequest(node_id=MANY, limit=1000))
    middle = await adapter.fetch(FetchRequest(node_id=MANY, limit=7, offset=123))

    assert not whole.has_more
    assert [row[0] for row in middle.rows] == [row[0] for row in whole.rows[123:130]]


async def test_no_column_can_be_sorted(target: Target) -> None:
    adapter = target.adapter()
    page = await adapter.fetch(FetchRequest(node_id=MANY, limit=1))

    assert not any(column.sortable for column in page.columns)
    with pytest.raises(ValueError):
        await adapter.fetch(FetchRequest(node_id=MANY, sort=[Sort(column="v")]))


# --- Filters -----------------------------------------------------------------


async def test_a_filter_outside_the_key_reads_with_allow_filtering(
    target: Target,
) -> None:
    adapter = target.adapter()

    page = await adapter.fetch(
        FetchRequest(
            node_id=MANY,
            limit=1000,
            filters=[
                ScalarFilter(column="v", op="eq", value="3"),
                ScalarFilter(column="p", op="lt", value="100"),
            ],
        )
    )

    assert sorted(int(row[0] or 0) for row in page.rows) == list(range(3, 100, 10))


async def test_a_filtered_read_pages_without_losing_rows(target: Target) -> None:
    adapter = target.adapter()
    seen: list[str | None] = []
    offset = 0
    while True:
        page = await adapter.fetch(
            FetchRequest(
                node_id=MANY,
                limit=7,
                offset=offset,
                filters=[InFilter(column="v", op="in", values=["1", "2"])],
            )
        )
        seen.extend(row[0] for row in page.rows)
        offset += 7
        if not page.has_more:
            break

    assert sorted(int(value or 0) for value in seen) == sorted(
        value for value in range(MANY_ROWS) if value % 10 in (1, 2)
    )


async def test_a_value_the_column_cannot_hold_is_refused(target: Target) -> None:
    with pytest.raises(ValueError, match='Invalid value for column "v"'):
        await target.adapter().fetch(
            FetchRequest(
                node_id=MANY, filters=[ScalarFilter(column="v", op="eq", value="x")]
            )
        )


async def test_a_collection_and_an_unknown_column_are_not_filtered(
    target: Target,
) -> None:
    adapter = target.adapter()
    page = await adapter.fetch(FetchRequest(node_id=ITEMS, limit=1))
    operators = {column.name: column.filter_operators for column in page.columns}

    assert operators["tags"] == []
    assert operators["data"] == []
    assert "ne" not in operators["label"] and "is_null" not in operators["label"]
    with pytest.raises(ValueError):
        await adapter.fetch(
            FetchRequest(
                node_id=ITEMS, filters=[ScalarFilter(column="tags", op="eq", value="a")]
            )
        )
    with pytest.raises(ValueError):
        await adapter.fetch(
            FetchRequest(
                node_id=ITEMS, filters=[ScalarFilter(column="nope", op="eq", value="a")]
            )
        )


async def test_only_scylladb_looks_inside_text(target: Target) -> None:
    adapter = target.adapter()
    page = await adapter.fetch(FetchRequest(node_id=MANY, limit=1))
    word = next(column for column in page.columns if column.name == "word")

    if not target.scylla:
        assert "contains" not in word.filter_operators
        return
    assert {"contains", "starts_with"} <= set(word.filter_operators)
    found = await adapter.fetch(
        FetchRequest(
            node_id=MANY,
            limit=1000,
            filters=[ScalarFilter(column="word", op="starts_with", value="w24")],
        )
    )
    assert sorted(row[2] or "" for row in found.rows) == [
        "w24",
        "w240",
        "w241",
        "w242",
        "w243",
        "w244",
        "w245",
        "w246",
        "w247",
        "w248",
        "w249",
    ]
    with pytest.raises(ValueError):
        await adapter.fetch(
            FetchRequest(
                node_id=MANY,
                filters=[ScalarFilter(column="word", op="contains", value="5%")],
            )
        )


async def test_a_quoted_name_is_read(target: Target) -> None:
    page = await target.adapter().fetch(FetchRequest(node_id=f"{KEYSPACE}.{ODD}"))

    assert [column.name for column in page.columns] == ["x y"]
    assert page.rows == [["7"]]


async def test_a_view_is_read_like_a_table(target: Target) -> None:
    page = await target.adapter().fetch(FetchRequest(node_id=VIEW, limit=10))

    assert sorted(row[0] or "" for row in page.rows) == ["false", "true"]


async def test_a_system_table_is_read(target: Target) -> None:
    page = await target.adapter().fetch(FetchRequest(node_id="system.local", limit=5))

    assert len(page.rows) == 1


async def test_a_virtual_table_is_read(target: Target) -> None:
    if target.scylla:
        pytest.skip("ScyllaDB keeps no virtual keyspace")
    page = await target.adapter().fetch(
        FetchRequest(node_id="system_views.settings", limit=5)
    )

    assert len(page.rows) == 5


# --- Contents ------------------------------------------------------------------


async def test_the_ddl_is_the_servers_own(target: Target) -> None:
    content = await target.adapter().read_content(
        ContentRequest(node_id=ITEMS, representation="sql")
    )

    assert isinstance(content, SqlContent)
    assert "CREATE TABLE dp_test_cql.items" in content.text
    assert "PRIMARY KEY (shop, id, at)" in content.text
    assert "items_label" in content.text


async def test_a_views_ddl_is_its_own(target: Target) -> None:
    content = await target.adapter().read_content(
        ContentRequest(node_id=VIEW, representation="sql")
    )

    assert isinstance(content, SqlContent)
    assert "CREATE MATERIALIZED VIEW dp_test_cql.items_by_ok" in content.text


async def test_the_summary_counts_the_model(target: Target) -> None:
    summary = await target.adapter().node_summary(ITEMS)

    assert isinstance(summary.contents, RelationContents)
    assert summary.contents.columns == 23
    assert summary.contents.constraints == 1
    assert summary.contents.indexes == 1
    assert summary.contents.partitioned_by == "shop"


def test_the_session_module_names_no_other_driver() -> None:
    assert "psycopg" not in vars(cql_session)
