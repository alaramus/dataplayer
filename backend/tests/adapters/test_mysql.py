"""A MySQL or MariaDB server as a source type (D228–D231).

Every test that needs a server runs against both: one source type speaks to
both, and they differ exactly where the catalog looks.
"""

import uuid
from collections.abc import AsyncIterator

import pytest
from pydantic import SecretStr

from app.adapters import registry
from app.adapters.content import ContentRequest, SqlContent
from app.adapters.fetch import FetchRequest, InFilter, NullFilter, ScalarFilter, Sort
from app.adapters.mysql import ids
from app.adapters.mysql.adapter import MysqlAdapter
from app.adapters.mysql.options import MysqlNoPassword, MysqlUserPassword
from app.adapters.mysql.session import options_from_url, read_profile
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
from app.adapters.relation import (
    CheckConstraint,
    ForeignKey,
    PrimaryKey,
    UniqueConstraint,
)
from app.adapters.resources import Pooling, ResourceStore
from app.adapters.summary import RelationContents
from tests.adapters.mysql_fixture import (
    DATABASE,
    OTHER,
    TARGETS,
    Target,
    build,
    run,
    tear_down,
)

ITEMS = ids.relation_id(DATABASE, "items")


@pytest.fixture(params=TARGETS, ids=lambda target: target.flavour, scope="module")
async def target(request: pytest.FixtureRequest) -> AsyncIterator[Target]:
    chosen: Target = request.param
    chosen.server.require()
    await build(chosen)
    yield chosen
    await tear_down(chosen)


def _unreachable() -> MysqlAdapter:
    return MysqlAdapter(
        MysqlUserPassword(
            host="127.0.0.1", port=1, user="root", password=SecretStr("secret-password")
        )
    )


# --- What the type is ----------------------------------------------------


def test_the_type_is_registered_as_sql() -> None:
    kind = registry.get("mysql")

    assert kind.adapter_class is MysqlAdapter
    assert kind.category == "sql"


def test_it_claims_only_what_it_does() -> None:
    adapter = _unreachable()
    for capability in (
        DataAdapter,
        SupportsCatalog,
        SupportsNodePath,
        SupportsFetch,
        SupportsRelationModel,
        SupportsNodeSummary,
        SupportsContent,
    ):
        assert isinstance(adapter, capability)
    # Not yet: rows are read, and nothing writes or runs a console.
    assert not isinstance(adapter, SupportsUpdate)
    assert not isinstance(adapter, SupportsQuery)


def test_a_server_is_read_as_its_flavour_and_number() -> None:
    mysql = read_profile("8.4.11")
    mariadb = read_profile("11.4.13-MariaDB-ubu2404")

    assert (mysql.flavour, mysql.text, mysql.supported) == ("mysql", "8.4.11", True)
    assert (mariadb.flavour, mariadb.text, mariadb.supported) == ("mariadb", "11.4.13", True)
    # Below the floor, said by the check rather than half working (D228).
    assert not read_profile("5.7.44-log").supported
    assert not read_profile("8.0.15").supported
    assert read_profile("8.0.16").supported
    assert not read_profile("10.5.27-MariaDB").supported


# --- Addresses -------------------------------------------------------------


def test_a_connection_string_fills_the_form() -> None:
    assert options_from_url("mysql://ann%40corp:p%2Fw@db.example.com:3310/sales") == {
        "host": "db.example.com",
        "port": 3310,
        "user": "ann@corp",
        "database": "sales",
        "auth_method": "user_password",
        "password": "p/w",
    }
    # One source type for both, so MariaDB's own scheme is read too.
    assert options_from_url("mariadb://root@localhost")["auth_method"] == "no_password"


@pytest.mark.parametrize(
    "url", ["postgresql://a@b/c", "mysql:///nohost", "mysql://h:notaport/d"]
)
def test_what_is_not_a_mysql_address_is_refused(url: str) -> None:
    with pytest.raises(ValueError):
        options_from_url(url)


def test_the_address_is_composed_without_the_password() -> None:
    adapter = MysqlAdapter(
        MysqlUserPassword(
            host="db", port=3306, user="ann@corp", database="a/b", password=SecretStr("pw")
        )
    )

    assert adapter.connection_string() == "mysql://ann%40corp@db:3306/a%2Fb"
    assert MysqlAdapter.connection_url_with_password(
        {"host": "db", "port": "3306", "user": "u", "password": "p@ss"}
    ) == "mysql://u:p%40ss@db:3306"
    assert MysqlAdapter.draft_connection_string({"host": "db", "port": "33"}) == "mysql://db:33"


def test_a_node_id_survives_a_dot_in_the_database() -> None:
    assert ids.parse(ids.relation_id("a.b\\c", "t.u")) == ("a.b\\c", "t.u")
    assert ids.parse(ids.database_id("a.b")) == ("a.b", None)


# --- Reaching a server ---------------------------------------------------


async def test_an_unreachable_server_is_said_and_the_password_is_not() -> None:
    result = await _unreachable().check_connection()

    assert not result.ok
    assert result.error_kind == "network"
    assert "secret-password" not in result.message


async def test_the_server_answers(target: Target) -> None:
    result = await target.adapter().check_connection()
    features = await target.adapter().source_features()

    assert result.ok, result.message
    assert features.server_version is not None
    assert features.server_version.startswith("MariaDB" if target.flavour == "mariadb" else "MySQL")


async def test_a_wrong_password_is_an_authentication_failure(target: Target) -> None:
    result = await target.adapter(password=SecretStr("not-it")).check_connection()

    assert (result.ok, result.error_kind) == (False, "auth")
    assert "not-it" not in result.message


async def test_a_missing_database_is_said(target: Target) -> None:
    result = await target.adapter(database="dp_no_such_database").check_connection()

    assert (result.ok, result.error_kind) == (False, "config")


async def test_a_password_outside_latin1_signs_in(target: Target) -> None:
    """The driver encodes a password as Latin-1; the server compares UTF-8."""
    user = f"dp_{uuid.uuid4().hex[:8]}"
    await run(target, f"CREATE USER '{user}'@'%' IDENTIFIED BY 'пароль-ü'")
    try:
        result = await target.adapter(user=user, password=SecretStr("пароль-ü")).check_connection()
    finally:
        await run(target, f"DROP USER '{user}'@'%'")

    assert result.ok, result.message


async def test_a_user_without_a_password_signs_in(target: Target) -> None:
    user = f"dp_{uuid.uuid4().hex[:8]}"
    await run(target, f"CREATE USER '{user}'@'%'")
    try:
        options = target.options()
        result = await MysqlAdapter(
            MysqlNoPassword(host=options.host, port=options.port, user=user)
        ).check_connection()
    finally:
        await run(target, f"DROP USER '{user}'@'%'")

    assert result.ok, result.message


async def test_a_pooled_connection_is_kept_and_reused(target: Target) -> None:
    store = ResourceStore(max_entries=4, max_idle_seconds=60)
    pooling = Pooling(store=store, connector_id=uuid.uuid4())
    try:
        adapter = MysqlAdapter(target.options(), pooling)
        await adapter.list_children(None)
        await adapter.list_children(ids.database_id(DATABASE))

        assert await store.size() == 1
    finally:
        await store.aclose()


# --- The catalog ---------------------------------------------------------


async def test_databases_are_listed_with_the_server_s_own_marked(target: Target) -> None:
    nodes = await target.adapter(database=DATABASE).list_children(None)
    by_name = {node.name: node for node in nodes}

    # The connection's own database first (D229).
    assert nodes[0].name == DATABASE
    assert nodes[0].id == ids.database_id(DATABASE)
    assert by_name["mysql"].kind == "schema"
    assert by_name["mysql"].is_system  # type: ignore[union-attr]  # a schema node, asserted above
    assert not by_name[OTHER].is_system  # type: ignore[union-attr]  # the same


async def test_a_database_lists_tables_and_views_once_each(target: Target) -> None:
    nodes = await target.adapter().list_children(ids.database_id(DATABASE))

    assert [(node.name, node.kind) for node in nodes] == [
        ("heap", "table"),
        ("item_labels", "view"),
        ("items", "table"),
        ("keyless", "table"),
    ]
    items = next(node for node in nodes if node.name == "items")
    assert items.describable and items.summarizable
    assert [item.kind for item in items.representations] == ["table", "sql"]


async def test_a_missing_database_lists_nothing_and_says_so(target: Target) -> None:
    with pytest.raises(Exception, match="does not exist"):
        await target.adapter().list_children(ids.database_id("dp_no_such_database"))


async def test_path_to_confirms_every_step(target: Target) -> None:
    adapter = target.adapter()

    path = await adapter.path_to(ITEMS)

    assert [node.name for node in path] == [DATABASE, "items"]
    with pytest.raises(NodeNotFound):
        await adapter.path_to(ids.relation_id(DATABASE, "gone"))
    with pytest.raises(NodeNotFound):
        await adapter.path_to(ids.database_id("dp_no_such_database"))


# --- The relation model --------------------------------------------------


async def test_the_relation_model_reads_columns_as_the_server_states_them(target: Target) -> None:
    model = await target.adapter().relation_model(ITEMS)
    columns = {column.name: column for column in model.columns}

    assert (model.schema_name, model.name, model.kind) == (DATABASE, "items", "table")
    assert model.comment == "Things"
    assert columns["id"].identity == "by_default"
    assert columns["id"].type.category == "number"
    assert "unsigned" in columns["id"].type.sql
    assert columns["label"].default == "'it''s'"
    assert columns["made"].default is not None
    assert columns["made"].default.lower().startswith("current_timestamp")
    assert columns["seen"].default is None
    assert columns["doubled"].generated is not None
    assert columns["amount"].type.precision == 30
    assert columns["amount"].type.scale == 10
    assert columns["label"].type.length == 40
    assert columns["kind"].type.enum_values == ["small", "it's big"]
    # MariaDB's JSON is LONGTEXT with a check of its own; it is still JSON.
    assert columns["payload"].type.category == "json"
    assert columns["place"].type.category == "geometric"
    assert columns["raw"].type.category == "binary"


async def test_the_relation_model_reads_keys_checks_and_indexes(target: Target) -> None:
    model = await target.adapter().relation_model(ITEMS)
    constraints = {constraint.name: constraint for constraint in model.constraints}

    assert isinstance(constraints["PRIMARY"], PrimaryKey)
    assert isinstance(constraints["items_label"], UniqueConstraint)
    foreign = constraints["items_owner"]
    assert isinstance(foreign, ForeignKey)
    # Into another database: the target's schema is read, not assumed.
    assert foreign.target_node_id == ids.relation_id(OTHER, "owners")
    assert foreign.on_delete == "set_null"
    check = constraints["items_amount"]
    assert isinstance(check, CheckConstraint)
    assert "amount" in check.expression
    # The JSON check MariaDB keeps for a column is the type, not a constraint.
    assert not any(name == "payload" for name in constraints)

    indexes = {index.name: index for index in model.indexes}
    assert indexes["PRIMARY"].primary
    assert indexes["items_label"].unique
    assert "`label`(4)" in indexes["items_prefix"].definition
    assert {key.name for key in model.candidate_keys} == {"PRIMARY", "items_label"}
    assert not model.column_changes_supported
    assert model.column_changes_reason


async def test_a_view_is_described_as_a_view(target: Target) -> None:
    model = await target.adapter().relation_model(ids.relation_id(DATABASE, "item_labels"))

    assert model.kind == "view"
    assert model.comment is None
    assert [column.name for column in model.columns] == ["id", "label"]


async def test_a_missing_relation_is_not_found(target: Target) -> None:
    with pytest.raises(NodeNotFound):
        await target.adapter().relation_model(ids.relation_id(DATABASE, "gone"))
    with pytest.raises(ValueError):
        await target.adapter().relation_model(ids.database_id(DATABASE))


# --- Rows ------------------------------------------------------------------


async def test_every_value_crosses_as_its_canonical_text(target: Target) -> None:
    result = await target.adapter().fetch(FetchRequest(node_id=ITEMS))
    names = [column.name for column in result.columns]
    first = dict(zip(names, result.rows[0], strict=True))
    second = dict(zip(names, result.rows[1], strict=True))

    assert first["amount"] == "12345678901234567890.0123456789"
    assert first["big"] == "18446744073709551615"
    assert first["flags"] == "5"
    assert first["kind"] == "it's big"
    assert first["payload"] == '{"a":[1,2]}'
    assert first["place"] == "POINT(1 2)"
    assert first["raw"] == "0x00FF"
    # TIMESTAMP is read in UTC and says so; DATETIME carries no zone (D230).
    assert first["seen"] == "2024-01-02T03:04:05+00:00"
    assert first["day"] == "2024-02-03"
    assert first["spent"] == "-12:30:00"
    assert second["spent"] == "100:00:01"
    assert first["doubled"] == "10"
    assert second["100%"] is None
    assert not result.update_supported and result.update_reason
    assert not result.delete_supported


async def test_pages_follow_the_key_and_say_when_there_is_more(target: Target) -> None:
    adapter = target.adapter()

    first = await adapter.fetch(FetchRequest(node_id=ITEMS, limit=2))
    rest = await adapter.fetch(FetchRequest(node_id=ITEMS, limit=2, offset=2))

    assert [row[0] for row in first.rows] == ["1", "2"]
    assert first.has_more
    assert [row[0] for row in rest.rows] == ["3"]
    assert not rest.has_more


async def test_a_table_without_a_primary_key_pages_by_its_unique_key(target: Target) -> None:
    """InnoDB keeps such a table in that key's order, and so do pages (D231)."""
    result = await target.adapter().fetch(
        FetchRequest(node_id=ids.relation_id(DATABASE, "keyless"))
    )

    assert [row[0] for row in result.rows] == ["1", "2", "3"]


async def test_sorting_and_filtering_happen_on_the_server(target: Target) -> None:
    adapter = target.adapter()

    by_label = await adapter.fetch(
        FetchRequest(node_id=ITEMS, sort=[Sort(column="label", descending=True)])
    )
    assert [row[1] for row in by_label.rows] == ["under_score", "alpha", "50% off"]

    async def labels(*filters: object) -> list[str | None]:
        result = await adapter.fetch(FetchRequest(node_id=ITEMS, filters=list(filters)))  # type: ignore[arg-type]  # the filters are built right here
        return [row[1] for row in result.rows]

    # A LIKE wildcard typed by the reader is a character, not a wildcard.
    assert await labels(ScalarFilter(column="label", op="contains", value="%")) == ["50% off"]
    assert await labels(ScalarFilter(column="label", op="contains", value="_")) == ["under_score"]
    assert await labels(ScalarFilter(column="label", op="starts_with", value="AL")) == ["alpha"]
    assert await labels(ScalarFilter(column="amount", op="gt", value="0.5")) == ["alpha", "under_score"]
    assert await labels(InFilter(column="id", op="in", values=["1", "3"])) == ["alpha", "under_score"]
    assert await labels(NullFilter(column="100%", op="is_null")) == ["50% off"]
    assert await labels(ScalarFilter(column="100%", op="eq", value="5")) == ["alpha"]
    assert await labels(
        ScalarFilter(column="seen", op="eq", value="2024-01-02T03:04:05+00:00")
    ) == ["alpha"]
    assert await labels(ScalarFilter(column="spent", op="lt", value="-01:00:00")) == ["alpha"]


async def test_a_column_or_value_from_the_client_is_checked_first(target: Target) -> None:
    adapter = target.adapter()

    with pytest.raises(ValueError, match="no column"):
        await adapter.fetch(
            FetchRequest(node_id=ITEMS, sort=[Sort(column="id`; DROP TABLE items; --")])
        )
    with pytest.raises(ValueError, match="Invalid value"):
        await adapter.fetch(
            FetchRequest(node_id=ITEMS, filters=[ScalarFilter(column="id", op="eq", value="x")])
        )
    with pytest.raises(ValueError, match="Cannot filter"):
        await adapter.fetch(
            FetchRequest(
                node_id=ITEMS, filters=[ScalarFilter(column="raw", op="contains", value="x")]
            )
        )


# --- What it is, and its DDL ---------------------------------------------


async def test_the_summary_counts_the_model_and_states_its_times(target: Target) -> None:
    summary = await target.adapter().node_summary(ITEMS)

    assert summary.kind == "table"
    assert isinstance(summary.contents, RelationContents)
    assert summary.contents.schema_name == DATABASE
    assert summary.contents.columns == 16
    assert summary.contents.constraints == 4
    assert summary.created_at is not None
    assert summary.created_at.tzinfo is not None


async def test_the_ddl_is_the_server_s_own(target: Target) -> None:
    content = await target.adapter().read_content(
        ContentRequest(node_id=ITEMS, representation="sql")
    )

    assert isinstance(content, SqlContent)
    assert content.text.startswith("CREATE TABLE `items`")
    assert "AUTO_INCREMENT" in content.text
    assert content.text.endswith(";")
