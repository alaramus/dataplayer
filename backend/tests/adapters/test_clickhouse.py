"""A ClickHouse server as a source type (D267–D269)."""

import uuid
from collections.abc import AsyncIterator

import pytest
from pydantic import SecretStr

from app.adapters import registry
from app.adapters.clickhouse.adapter import ClickhouseAdapter
from app.adapters.clickhouse.options import ClickhouseUserPassword
from app.adapters.clickhouse.session import options_from_url, quoted_name, read_profile
from app.adapters.clickhouse.types import build_column_type, enum_labels, read_cell
from app.adapters.content import ContentRequest, SqlContent
from app.adapters.database_ids import database_id, parse, relation_id
from app.adapters.fetch import FetchRequest, InFilter, NullFilter, ScalarFilter, Sort
from app.adapters.protocol import (
    DataAdapter,
    NodeNotFound,
    SupportsCatalog,
    SupportsContent,
    SupportsFetch,
    SupportsNodePath,
    SupportsNodeSummary,
    SupportsRelationModel,
    SupportsUpdate,
)
from app.adapters.query import SupportsQuery
from app.adapters.relation import CheckConstraint, RelationModelsRequest
from app.adapters.resources import Pooling, ResourceStore
from app.adapters.summary import RelationContents
from tests.adapters.clickhouse_fixture import (
    DATABASE,
    ODD,
    adapter,
    build,
    options,
    run,
    tear_down,
)
from tests.utils.services import CLICKHOUSE

ITEMS = relation_id(DATABASE, "items")


@pytest.fixture(scope="module")
async def server() -> AsyncIterator[None]:
    CLICKHOUSE.require()
    await build()
    yield
    await tear_down()


def _unreachable() -> ClickhouseAdapter:
    return ClickhouseAdapter(
        ClickhouseUserPassword(
            host="127.0.0.1", port=1, user="default", password=SecretStr("secret-password")
        )
    )


# --- What the type is ----------------------------------------------------


def test_the_type_is_registered_as_sql() -> None:
    kind = registry.get("clickhouse")

    assert kind.adapter_class is ClickhouseAdapter
    assert kind.category == "sql"


def test_it_claims_only_what_it_does() -> None:
    source = _unreachable()
    for capability in (
        DataAdapter,
        SupportsCatalog,
        SupportsNodePath,
        SupportsFetch,
        SupportsRelationModel,
        SupportsNodeSummary,
        SupportsContent,
    ):
        assert isinstance(source, capability)
    assert isinstance(source, SupportsQuery)
    assert isinstance(source, SupportsUpdate)


def test_a_server_is_read_as_its_number() -> None:
    assert read_profile("25.8.33.6").text == "25.8.33.6"
    assert read_profile("23.8.1.1").supported
    # Below the floor, said by the check rather than half working (D267).
    assert not read_profile("23.3.22.3").supported
    assert not read_profile("22.12.1").supported


# --- Addresses -------------------------------------------------------------


def test_a_connection_string_fills_the_form() -> None:
    assert options_from_url("clickhouse://ann%40corp:p%2Fw@ch.example.com:8443/sales?secure=true") == {
        "host": "ch.example.com",
        "secure": True,
        "port": 8443,
        "user": "ann@corp",
        "database": "sales",
        "auth_method": "user_password",
        "password": "p/w",
    }
    # The HTTP interface's own address is one as well.
    assert options_from_url("https://default@ch.example.com:8443/?database=logs") == {
        "host": "ch.example.com",
        "secure": True,
        "port": 8443,
        "user": "default",
        "database": "logs",
        "auth_method": "no_password",
    }


@pytest.mark.parametrize(
    "url", ["postgresql://a@b/c", "clickhouse:///nohost", "clickhouse://h:notaport/d"]
)
def test_what_is_not_a_clickhouse_address_is_refused(url: str) -> None:
    with pytest.raises(ValueError):
        options_from_url(url)


def test_the_address_is_composed_without_the_password() -> None:
    source = ClickhouseAdapter(
        ClickhouseUserPassword(
            host="ch", port=8123, user="ann@corp", database="a/b", password=SecretStr("pw")
        )
    )

    assert source.connection_string() == "clickhouse://ann%40corp@ch:8123/a%2Fb"
    assert ClickhouseAdapter.connection_url_with_password(
        {"host": "ch", "port": "8443", "user": "u", "password": "p@ss", "secure": True}
    ) == "clickhouse://u:p%40ss@ch:8443?secure=true"
    assert ClickhouseAdapter.draft_connection_string({"host": "ch", "port": "81"}) == (
        "clickhouse://ch:81"
    )


def test_a_node_id_survives_a_dot_in_the_database() -> None:
    assert parse(relation_id("a.b\\c", "t.u")) == ("a.b\\c", "t.u")
    assert parse(database_id("a.b")) == ("a.b", None)


def test_a_name_is_quoted_against_backslashes_and_backticks() -> None:
    assert quoted_name("db", "a`b\\c") == "`db`.`a\\`b\\\\c`"


# --- Types and values ------------------------------------------------------


def test_a_type_is_read_through_its_wrappers() -> None:
    nullable = build_column_type("LowCardinality(Nullable(String))")
    decimal = build_column_type("Nullable(Decimal(38, 10))")
    array = build_column_type("Array(Nullable(UInt8))")

    assert nullable.category == "string"
    assert (decimal.category, decimal.precision, decimal.scale) == ("number", 38, 10)
    assert build_column_type("Decimal64(4)").precision == 18
    assert array.category == "array"
    assert array.element is not None and array.element.category == "number"
    assert build_column_type("FixedString(16)").length == 16
    assert build_column_type("DateTime64(3, 'UTC')").category == "datetime"
    assert build_column_type("Map(String, UInt8)").category == "composite"
    assert build_column_type("AggregateFunction(uniq, UInt64)").category == "other"
    assert enum_labels("Enum8('a' = 1, 'it\\'s = big' = 2)") == ["a", "it's = big"]


def test_a_value_crosses_as_the_server_wrote_it() -> None:
    from app.adapters.clickhouse.types import decode_line

    row = decode_line('[12345678901234567890.0123456789, 1e300, [1.10,{"a":null}], true, null]')

    assert [read_cell(value) for value in row] == [
        "12345678901234567890.0123456789",
        "1e300",
        '[1.10,{"a":null}]',
        "true",
        None,
    ]


# --- Reaching a server ---------------------------------------------------


async def test_an_unreachable_server_is_said_and_the_password_is_not() -> None:
    result = await _unreachable().check_connection()

    assert not result.ok
    assert result.error_kind == "network"
    assert "secret-password" not in result.message


@pytest.mark.usefixtures("server")
async def test_the_server_answers() -> None:
    result = await adapter().check_connection()
    features = await adapter().source_features()

    assert result.ok, result.message
    assert features.server_version is not None
    assert features.server_version.startswith("ClickHouse ")


@pytest.mark.usefixtures("server")
async def test_a_wrong_password_is_an_authentication_failure() -> None:
    result = await adapter(password=SecretStr("not-it")).check_connection()

    assert (result.ok, result.error_kind) == (False, "auth")
    assert "not-it" not in result.message


@pytest.mark.usefixtures("server")
async def test_a_missing_database_is_said() -> None:
    result = await adapter(database="dp_no_such_database").check_connection()

    assert (result.ok, result.error_kind) == (False, "config")


@pytest.mark.usefixtures("server")
async def test_a_password_outside_latin1_signs_in() -> None:
    user = f"dp_{uuid.uuid4().hex[:8]}"
    await run(f"CREATE USER {user} IDENTIFIED WITH plaintext_password BY 'пароль-ü'")
    try:
        result = await adapter(user=user, password=SecretStr("пароль-ü")).check_connection()
    finally:
        await run(f"DROP USER {user}")

    assert result.ok, result.message


@pytest.mark.usefixtures("server")
async def test_a_kept_client_is_reused() -> None:
    store = ResourceStore(max_entries=4, max_idle_seconds=60)
    pooling = Pooling(store=store, connector_id=uuid.uuid4())
    try:
        source = ClickhouseAdapter(options(), pooling)
        await source.list_children(None)
        await source.list_children(database_id(DATABASE))

        assert await store.size() == 1
    finally:
        await store.aclose()


# --- The catalog ---------------------------------------------------------


@pytest.mark.usefixtures("server")
async def test_databases_are_listed_with_the_server_s_own_marked() -> None:
    nodes = await adapter(database=DATABASE).list_children(None)
    by_name = {node.name: node for node in nodes}

    # The connection's own database first.
    assert nodes[0].name == DATABASE
    assert nodes[0].id == database_id(DATABASE)
    assert by_name["system"].kind == "schema"
    assert by_name["system"].is_system
    assert not by_name["default"].is_system  # type: ignore[union-attr]  # a schema node, as "system" is


@pytest.mark.usefixtures("server")
async def test_a_database_lists_tables_and_views_once_each() -> None:
    nodes = await adapter().list_children(database_id(DATABASE))

    assert [(node.name, node.kind) for node in nodes] == [
        ("dupes", "table"),
        ("item_ids", "view"),
        ("item_labels", "view"),
        ("items", "table"),
        ("journal", "table"),
        (ODD, "table"),
    ]
    by_name = {node.name: node for node in nodes}
    assert by_name["item_ids"].is_materialized  # type: ignore[union-attr]  # a view node, asserted above
    items = by_name["items"]
    assert items.describable and items.summarizable
    assert items.row_count_estimate == 3  # type: ignore[union-attr]  # a table node, asserted above
    assert [item.kind for item in items.representations] == ["table", "sql"]


@pytest.mark.usefixtures("server")
async def test_a_missing_database_lists_nothing_and_says_so() -> None:
    with pytest.raises(Exception, match="does not exist"):
        await adapter().list_children(database_id("dp_no_such_database"))


@pytest.mark.usefixtures("server")
async def test_path_to_confirms_every_step() -> None:
    source = adapter()

    path = await source.path_to(ITEMS)

    assert [node.name for node in path] == [DATABASE, "items"]
    with pytest.raises(NodeNotFound):
        await source.path_to(relation_id(DATABASE, "gone"))
    with pytest.raises(NodeNotFound):
        await source.path_to(database_id("dp_no_such_database"))


# --- The relation model --------------------------------------------------


@pytest.mark.usefixtures("server")
async def test_the_relation_model_reads_columns_as_the_server_states_them() -> None:
    model = await adapter().relation_model(ITEMS)
    columns = {column.name: column for column in model.columns}

    assert (model.schema_name, model.name, model.kind) == (DATABASE, "items", "table")
    assert model.comment == "Things"
    assert columns["label"].default == "'it\\'s'"
    assert columns["label"].type.sql == "LowCardinality(String)"
    assert columns["100%"].nullable and not columns["id"].nullable
    assert columns["doubled"].generated is not None
    assert columns["amount"].type.precision == 38
    assert columns["kind"].type.enum_values == ["small", "it's big"]
    assert columns["tags"].type.category == "array"
    assert columns["made"].type.category == "datetime"
    assert columns["uid"].type.category == "uuid"


@pytest.mark.usefixtures("server")
async def test_the_relation_model_reads_checks_and_indexes() -> None:
    model = await adapter().relation_model(ITEMS)

    # No key of ClickHouse is unique, so none is a constraint (D269).
    assert [type(constraint) for constraint in model.constraints] == [CheckConstraint]
    assert model.constraints[0].name == "items_amount"
    assert "amount" in model.constraints[0].expression  # type: ignore[union-attr]  # a check, asserted above
    indexes = {index.name: index for index in model.indexes}
    assert indexes["PRIMARY KEY"].primary and not indexes["PRIMARY KEY"].unique
    assert indexes["PRIMARY KEY"].columns == ["id", "label"]
    assert indexes["items_label"].method == "bloom_filter"
    assert model.candidate_keys == []
    assert not model.column_changes_supported
    assert model.column_changes_reason


@pytest.mark.usefixtures("server")
async def test_views_are_described_as_what_they_are() -> None:
    source = adapter()

    view = await source.relation_model(relation_id(DATABASE, "item_labels"))
    materialized = await source.relation_model(relation_id(DATABASE, "item_ids"))

    assert view.kind == "view"
    assert [column.name for column in view.columns] == ["id", "label"]
    assert materialized.kind == "materialized_view"


@pytest.mark.usefixtures("server")
async def test_several_relations_are_described_together() -> None:
    models = await adapter().relation_models_for_nodes(
        RelationModelsRequest(
            node_ids=[ITEMS, relation_id(DATABASE, "journal"), relation_id(DATABASE, "gone")]
        )
    )

    assert sorted(model.name for model in models) == ["items", "journal"]


@pytest.mark.usefixtures("server")
async def test_a_missing_relation_is_not_found() -> None:
    with pytest.raises(NodeNotFound):
        await adapter().relation_model(relation_id(DATABASE, "gone"))
    with pytest.raises(ValueError):
        await adapter().relation_model(database_id(DATABASE))


# --- Rows ------------------------------------------------------------------


@pytest.mark.usefixtures("server")
async def test_every_value_crosses_as_its_canonical_text() -> None:
    result = await adapter().fetch(FetchRequest(node_id=ITEMS))
    names = [column.name for column in result.columns]
    first = dict(zip(names, result.rows[0], strict=True))
    second = dict(zip(names, result.rows[1], strict=True))
    third = dict(zip(names, result.rows[2], strict=True))

    assert first["amount"] == "12345678901234567890.0123456789"
    assert second["amount"] == "0.0000000000"
    assert first["big"] == "18446744073709551615"
    assert first["huge"] == "-170141183460469231731687303715884105728"
    assert first["ratio"] == "0.1"
    assert second["ratio"] == "1e300"
    assert third["ratio"] == "nan"
    assert first["kind"] == "it's big"
    assert first["tags"] == '["a","b\\"c"]'
    assert first["attrs"] == '{"k":1}'
    assert first["pair"] == '{"a":1,"b":"x"}'
    # Every moment in UTC, with its Z, whatever zone the column keeps (D268).
    assert first["made"] == "2024-01-02T03:04:05Z"
    assert first["seen"] == "2024-01-02T03:04:05.120Z"
    assert first["day"] == "2024-02-03"
    assert (first["ok"], second["ok"]) == ("true", "false")
    assert first["uid"] == "00000000-0000-0000-0000-000000000001"
    assert first["addr"] == "10.0.0.1"
    assert second["100%"] is None
    # MATERIALIZED is read only when asked for by name, and it is.
    assert first["doubled"] == "10"


@pytest.mark.usefixtures("server")
async def test_pages_are_ordered_by_the_whole_row() -> None:
    """No key is unique, so a page is ordered by every column (D269)."""
    source = adapter()
    dupes = relation_id(DATABASE, "dupes")

    first = await source.fetch(FetchRequest(node_id=dupes, limit=2))
    rest = await source.fetch(FetchRequest(node_id=dupes, limit=2, offset=2))

    assert first.rows == [["0", "z"], ["1", "a"]]
    assert first.has_more
    assert rest.rows == [["1", "b"], ["1", "b"]]
    assert not rest.has_more


@pytest.mark.usefixtures("server")
async def test_a_table_of_an_unordered_engine_is_read_as_it_is() -> None:
    journal = await adapter().fetch(FetchRequest(node_id=relation_id(DATABASE, "journal")))
    endless = await adapter().fetch(
        FetchRequest(node_id=relation_id("system", "numbers"), limit=3)
    )

    assert sorted(row[0] or "" for row in journal.rows) == ["one", "two"]
    # system.numbers never ends; a page of it does.
    assert endless.rows == [["0"], ["1"], ["2"]]
    assert endless.has_more


@pytest.mark.usefixtures("server")
async def test_an_odd_name_is_quoted_and_not_read_as_a_parameter() -> None:
    result = await adapter().fetch(
        FetchRequest(
            node_id=relation_id(DATABASE, ODD),
            filters=[ScalarFilter(column="x{p1:Int8}", op="eq", value="7")],
        )
    )

    assert result.rows == [["7"]]


@pytest.mark.usefixtures("server")
async def test_sorting_and_filtering_happen_on_the_server() -> None:
    source = adapter()

    by_label = await source.fetch(
        FetchRequest(node_id=ITEMS, sort=[Sort(column="label", descending=True)])
    )
    assert [row[1] for row in by_label.rows] == ["under_score", "alpha", "50% off"]

    async def labels(*filters: object) -> list[str | None]:
        result = await source.fetch(FetchRequest(node_id=ITEMS, filters=list(filters)))  # type: ignore[arg-type]  # the filters are built right here
        return [row[1] for row in result.rows]

    # A LIKE wildcard typed by the reader is a character, not a wildcard.
    assert await labels(ScalarFilter(column="label", op="contains", value="%")) == ["50% off"]
    assert await labels(ScalarFilter(column="label", op="contains", value="_")) == ["under_score"]
    assert await labels(ScalarFilter(column="label", op="starts_with", value="al")) == ["alpha"]
    assert await labels(ScalarFilter(column="amount", op="gt", value="0.5")) == [
        "alpha",
        "under_score",
    ]
    assert await labels(InFilter(column="id", op="in", values=["1", "3"])) == [
        "alpha",
        "under_score",
    ]
    assert await labels(NullFilter(column="100%", op="is_null")) == ["50% off"]
    assert await labels(ScalarFilter(column="kind", op="eq", value="it's big")) == ["alpha"]
    assert await labels(ScalarFilter(column="ok", op="eq", value="true")) == ["alpha"]
    assert await labels(
        ScalarFilter(column="uid", op="eq", value="00000000-0000-0000-0000-000000000002")
    ) == ["50% off"]
    # An instant, whatever zone the column keeps and the value is written in.
    assert await labels(ScalarFilter(column="made", op="eq", value="2024-01-02T03:04:05Z")) == [
        "alpha"
    ]
    assert await labels(
        ScalarFilter(column="made", op="eq", value="2024-01-02T12:04:05+09:00")
    ) == ["alpha"]
    assert await labels(ScalarFilter(column="day", op="lt", value="2024-03-01")) == ["alpha"]


@pytest.mark.usefixtures("server")
async def test_a_column_or_value_from_the_client_is_checked_first() -> None:
    source = adapter()

    with pytest.raises(ValueError, match="no column"):
        await source.fetch(
            FetchRequest(node_id=ITEMS, sort=[Sort(column="id`; DROP TABLE items; --")])
        )
    with pytest.raises(ValueError, match="Invalid value"):
        await source.fetch(
            FetchRequest(node_id=ITEMS, filters=[ScalarFilter(column="id", op="eq", value="x")])
        )
    with pytest.raises(ValueError, match="Cannot filter"):
        await source.fetch(
            FetchRequest(
                node_id=ITEMS, filters=[ScalarFilter(column="tags", op="contains", value="x")]
            )
        )
    # A number the column cannot hold is the server's to refuse, and is said.
    with pytest.raises(ValueError, match="does not fit"):
        await source.fetch(
            FetchRequest(node_id=ITEMS, filters=[ScalarFilter(column="id", op="eq", value="-1")])
        )


# --- What it is, and its DDL ---------------------------------------------


@pytest.mark.usefixtures("server")
async def test_the_summary_counts_the_model_and_states_when_it_was_written() -> None:
    summary = await adapter().node_summary(ITEMS)

    assert summary.kind == "table"
    assert isinstance(summary.contents, RelationContents)
    assert summary.contents.schema_name == DATABASE
    assert summary.contents.columns == 18
    assert summary.contents.constraints == 1
    assert summary.contents.partitioned_by == "toYYYYMM(day)"
    assert summary.modified_at is not None
    assert summary.modified_at.tzinfo is not None


@pytest.mark.usefixtures("server")
async def test_the_ddl_is_the_server_s_own() -> None:
    content = await adapter().read_content(ContentRequest(node_id=ITEMS, representation="sql"))

    assert isinstance(content, SqlContent)
    assert content.text.startswith("CREATE TABLE")
    assert "ENGINE = MergeTree" in content.text
    assert content.text.endswith(";")
