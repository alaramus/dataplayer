"""A MongoDB server as a source type (D283–D285)."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from bson import Decimal128, Int64, ObjectId
from bson.binary import Binary
from pydantic import SecretStr

from app.adapters import registry
from app.adapters.catalog import TableNode, ViewNode
from app.adapters.content import ContentRequest, JsonContent, JsonObject
from app.adapters.database_ids import database_id, relation_id
from app.adapters.fetch import FetchRequest, InFilter, NullFilter, ScalarFilter, Sort
from app.adapters.mongodb.adapter import MongodbAdapter
from app.adapters.mongodb.options import MongodbNoPassword, MongodbUserPassword
from app.adapters.mongodb.session import (
    compose_url_with_password,
    options_from_url,
    read_profile,
)
from app.adapters.mongodb.values import (
    FieldSample,
    capabilities,
    parsed_value,
    read_cell,
    schema_fields,
)
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
from app.adapters.relation import PrimaryKey, RelationModelsRequest
from app.adapters.resources import Pooling, ResourceStore
from app.adapters.summary import RelationContents
from tests.adapters.mongodb_fixture import (
    DATABASE,
    DOTTED,
    PEOPLE_IDS,
    UID,
    adapter,
    build,
    options,
    raw_client,
    tear_down,
)
from tests.utils.services import MONGODB

PEOPLE = relation_id(DATABASE, "people")
NUMBERS = relation_id(DATABASE, "numbers")


@pytest.fixture(scope="module")
async def server() -> AsyncIterator[None]:
    MONGODB.require()
    await build()
    yield
    await tear_down()


def _unreachable() -> MongodbAdapter:
    return MongodbAdapter(
        MongodbUserPassword(
            host="127.0.0.1", port=1, user="root", password=SecretStr("secret-password")
        )
    )


# --- What the type is ----------------------------------------------------


def test_the_type_is_registered_as_a_document_database() -> None:
    kind = registry.get("mongodb")

    assert kind.adapter_class is MongodbAdapter
    assert kind.category == "document"


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
    assert not isinstance(source, SupportsQuery)
    assert isinstance(source, SupportsUpdate)


def test_a_server_is_read_as_its_number() -> None:
    assert read_profile("8.0.15").text == "8.0.15"
    assert read_profile("5.0.0").supported
    assert not read_profile("4.4.29").supported


# --- Addresses -------------------------------------------------------------


def test_a_connection_string_fills_the_form() -> None:
    assert options_from_url(
        "mongodb://ann%40corp:p%2Fw@db.example.com:27019/shop?authSource=users&tls=true"
    ) == {
        "host": "db.example.com",
        "port": 27019,
        "tls": True,
        "database": "shop",
        "auth_method": "user_password",
        "user": "ann@corp",
        "password": "p/w",
        "auth_source": "users",
    }
    assert options_from_url("mongodb://localhost") == {
        "host": "localhost",
        "tls": False,
        "auth_method": "no_password",
    }
    # Without authSource the user is looked for where the address points.
    assert options_from_url("mongodb://ann:x@h/shop")["auth_source"] == "shop"
    assert options_from_url("mongodb://ann:x@h")["auth_source"] == "admin"


@pytest.mark.parametrize(
    "url",
    [
        "postgres://h/db",
        "mongodb+srv://cluster0.example.net/",
        "mongodb://a:27017,b:27017/?replicaSet=rs0",
        "mongodb://h:notaport/",
    ],
)
def test_what_this_source_cannot_reach_is_refused(url: str) -> None:
    with pytest.raises(ValueError):
        options_from_url(url)


def test_the_address_is_composed_without_the_password() -> None:
    source = MongodbAdapter(
        MongodbUserPassword(
            host="db.example.com",
            user="ann@corp",
            password=SecretStr("secret"),
            database="shop",
            tls=True,
        )
    )
    assert (
        source.connection_string()
        == "mongodb://ann%40corp@db.example.com:27017/shop?authSource=admin&tls=true"
    )
    assert "secret" not in source.connection_string()
    assert (
        compose_url_with_password(host="h", user="u", password="p/w")
        == "mongodb://u:p%2Fw@h/"
    )
    assert MongodbAdapter.draft_connection_string(
        {"host": "h", "port": "27", "auth_method": "no_password", "user": "ignored"}
    ) == "mongodb://h:27/"


def test_a_node_id_survives_dots_in_a_collection() -> None:
    assert relation_id(DATABASE, DOTTED) == f"{DATABASE}.{DOTTED}"


# --- Values --------------------------------------------------------------


def test_a_value_crosses_as_its_text() -> None:
    assert read_cell(None) is None
    assert read_cell(True) == "true"
    assert read_cell(Int64(9007199254740993)) == "9007199254740993"
    assert read_cell(0.1) == "0.1"
    assert read_cell(float("nan")) == "NaN"
    assert read_cell(Decimal128("1.10")) == "1.10"
    assert read_cell(ObjectId("650000000000000000000001")) == "650000000000000000000001"
    assert read_cell(datetime(2026, 1, 2, 3, 4, 5, 678000, tzinfo=UTC)) == "2026-01-02T03:04:05.678Z"
    assert read_cell(UID) == str(UID)
    assert read_cell(b"\x01\xff") == "0x01FF"
    # What has no plain spelling is relaxed Extended JSON, numbers unrounded.
    assert read_cell({"a": [1, Int64(9007199254740993)]}) == '{"a":[1,9007199254740993]}'
    assert read_cell({"when": datetime(2026, 1, 2, tzinfo=UTC)}) == '{"when":{"$date":"2026-01-02T00:00:00Z"}}'
    assert read_cell(Binary(b"x", 5)) == '{"$binary":{"base64":"eA==","subType":"05"}}'


def test_fields_are_learned_from_the_validator_and_the_documents() -> None:
    sample = FieldSample()
    for name, tag, required in schema_fields(
        {"$jsonSchema": {"required": ["a"], "properties": {"a": {"bsonType": ["int", "null"]}}}}
    ):
        sample.declare(name, tag, required)
    sample.read([{"_id": 1, "b": 1}, {"_id": 2, "b": 2.5, "c": "x"}, {"_id": 3, "b": "y"}])
    fields = {field.name: field for field in sample.ordered()}

    assert [field.name for field in sample.ordered()][0] == "_id"
    assert (fields["a"].tag, fields["a"].everywhere) == ("int", True)
    assert fields["b"].tag == "mixed"
    assert fields["b"].everywhere
    assert (fields["c"].tag, fields["c"].everywhere) == ("string", False)


def test_numbers_of_different_widths_are_one_number() -> None:
    sample = FieldSample()
    sample.read([{"n": 1}, {"n": 2.5}, {"n": Int64(3)}])

    assert sample.ordered()[0].tag == "number"


def test_a_name_no_query_can_address_offers_nothing() -> None:
    assert capabilities("string", "a.b") == (False, [])
    assert capabilities("string", "$x") == (False, [])
    sortable, operators = capabilities("string", "name")
    assert sortable
    assert "contains" in operators


def test_a_value_typed_in_is_read_as_the_field_holds_it() -> None:
    assert parsed_value("3", "number") == 3
    assert parsed_value("2.5", "int") == 2.5
    assert isinstance(parsed_value("3", "long"), Int64)
    assert parsed_value("1.10", "decimal") == Decimal128("1.10")
    assert parsed_value("2026-01-02", "date") == datetime(2026, 1, 2, tzinfo=UTC)
    assert parsed_value("2026-01-02T03:00:00+03:00", "date") == datetime(2026, 1, 2, tzinfo=UTC)
    assert parsed_value("650000000000000000000001", "objectId") == PEOPLE_IDS[0]
    assert parsed_value("TRUE", "bool") is True
    for text, tag in [("x", "number"), ("NaN", "double"), ("zz", "objectId"), ("maybe", "bool")]:
        with pytest.raises(ValueError):
            parsed_value(text, tag)  # type: ignore[arg-type]  # each tag is a Tag


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
    assert features.server_version.startswith("MongoDB ")


@pytest.mark.usefixtures("server")
async def test_a_wrong_password_is_an_authentication_failure() -> None:
    result = await adapter(password=SecretStr("not-it")).check_connection()

    assert (result.ok, result.error_kind) == (False, "auth")
    assert "not-it" not in result.message


@pytest.mark.usefixtures("server")
async def test_no_password_on_a_server_that_asks_for_one_is_said() -> None:
    chosen = options()
    result = await MongodbAdapter(
        MongodbNoPassword(host=chosen.host, port=chosen.port)
    ).check_connection()

    assert (result.ok, result.error_kind) == (False, "auth")


@pytest.mark.usefixtures("server")
async def test_a_password_outside_latin1_signs_in() -> None:
    user = f"dp_{uuid.uuid4().hex[:8]}"
    client = raw_client()
    try:
        await client[DATABASE].command(
            "createUser", user, pwd="пароль-ü", roles=[{"role": "read", "db": DATABASE}]
        )
        result = await adapter(
            user=user, password=SecretStr("пароль-ü"), auth_source=DATABASE
        ).check_connection()
        # A user who may read one database sees that one and no other.
        names = [
            node.name
            for node in await adapter(
                user=user, password=SecretStr("пароль-ü"), auth_source=DATABASE
            ).list_children(None)
            if node.kind == "schema"
        ]
    finally:
        await client[DATABASE].command("dropUser", user)
        await client.close()

    assert result.ok, result.message
    assert names == [DATABASE]


@pytest.mark.usefixtures("server")
async def test_a_kept_client_is_reused() -> None:
    store = ResourceStore(max_entries=4, max_idle_seconds=60)
    pooling = Pooling(store=store, connector_id=uuid.uuid4())
    try:
        source = MongodbAdapter(options(), pooling)
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

    assert nodes[0].name == DATABASE
    assert nodes[0].kind == "schema"
    assert by_name["admin"].kind == "schema"
    assert getattr(by_name["admin"], "is_system", False)
    assert not getattr(nodes[0], "is_system", True)


@pytest.mark.usefixtures("server")
async def test_a_database_not_made_yet_is_listed_when_the_connection_names_it() -> None:
    nodes = await adapter(database="dp_not_yet").list_children(None)

    assert nodes[0].name == "dp_not_yet"
    assert await adapter(database="dp_not_yet").list_children(database_id("dp_not_yet")) == []


@pytest.mark.usefixtures("server")
async def test_a_database_lists_collections_and_views() -> None:
    nodes = await adapter().list_children(database_id(DATABASE))
    by_name = {node.name: node for node in nodes}

    assert {"people", "numbers", "books", DOTTED, "adults", "empty"} <= set(by_name)
    people = by_name["people"]
    assert isinstance(people, TableNode)
    assert people.term == "collection"
    assert people.row_count_estimate == 3
    assert people.describable and people.summarizable
    assert [item.kind for item in people.representations] == ["table", "documents", "tree"]
    assert isinstance(by_name["adults"], ViewNode)
    assert by_name[DOTTED].id == relation_id(DATABASE, DOTTED)


@pytest.mark.usefixtures("server")
async def test_a_missing_database_lists_nothing_and_says_so() -> None:
    with pytest.raises(Exception, match="does not exist"):
        await adapter().list_children(database_id("dp_no_such_database"))


@pytest.mark.usefixtures("server")
async def test_path_to_confirms_every_step() -> None:
    path = await adapter().path_to(relation_id(DATABASE, DOTTED))

    assert [node.name for node in path] == [DATABASE, DOTTED]
    with pytest.raises(NodeNotFound):
        await adapter().path_to(relation_id(DATABASE, "nope"))
    with pytest.raises(NodeNotFound):
        await adapter().path_to(database_id("dp_no_such_database"))


# --- What a collection is ------------------------------------------------


@pytest.mark.usefixtures("server")
async def test_the_model_is_the_fields_the_documents_have() -> None:
    model = await adapter().relation_model(PEOPLE)
    columns = {column.name: column for column in model.columns}

    assert model.columns[0].name == "_id"
    assert (columns["_id"].type.sql, columns["_id"].nullable) == ("objectId", False)
    assert (columns["name"].type.category, columns["name"].nullable) == ("string", False)
    assert (columns["age"].type.sql, columns["age"].nullable) == ("number", True)
    assert columns["born"].type.category == "datetime"
    assert columns["tags"].type.sql == "array"
    assert columns["address"].type.category == "json"
    assert columns["uid"].type.category == "uuid"
    assert model.kind == "table"
    assert model.schema_name == DATABASE
    assert model.row_estimate == 3
    assert model.constraints == [PrimaryKey(name="_id_", columns=["_id"])]
    named = {index.name: index for index in model.indexes}
    assert named["_id_"].primary
    assert named["people_name"].unique
    assert named["people_name"].columns == ["name"]


@pytest.mark.usefixtures("server")
async def test_a_validator_declares_fields_no_document_has_yet() -> None:
    model = await adapter().relation_model(relation_id(DATABASE, "books"))
    columns = {column.name: column for column in model.columns}

    assert columns["title"].type.sql == "string"
    assert not columns["title"].nullable
    assert columns["pages"].type.sql == "int"


@pytest.mark.usefixtures("server")
async def test_an_empty_collection_still_has_its_id() -> None:
    model = await adapter().relation_model(relation_id(DATABASE, "empty"))

    assert [column.name for column in model.columns] == ["_id"]


@pytest.mark.usefixtures("server")
async def test_a_view_is_described_as_one() -> None:
    model = await adapter().relation_model(relation_id(DATABASE, "adults"))

    assert model.kind == "view"
    assert model.constraints == []
    assert model.indexes == []


@pytest.mark.usefixtures("server")
async def test_several_collections_are_described_together() -> None:
    models = await adapter().relation_models_for_nodes(
        RelationModelsRequest(node_ids=[PEOPLE, NUMBERS, relation_id(DATABASE, "nope")])
    )

    assert {model.name for model in models} == {"people", "numbers"}


@pytest.mark.usefixtures("server")
async def test_a_missing_collection_is_not_found() -> None:
    with pytest.raises(NodeNotFound):
        await adapter().relation_model(relation_id(DATABASE, "nope"))
    with pytest.raises(NodeNotFound):
        await adapter().fetch(FetchRequest(node_id=relation_id(DATABASE, "nope")))


# --- Pages ---------------------------------------------------------------


@pytest.mark.usefixtures("server")
async def test_every_value_crosses_as_its_canonical_text() -> None:
    page = await adapter().fetch(FetchRequest(node_id=PEOPLE))
    names = [column.name for column in page.columns]
    ann = dict(zip(names, page.rows[0], strict=True))

    assert ann["_id"] == "650000000000000000000001"
    assert ann["born"] == "1994-03-01T12:30:00.000Z"
    assert ann["tags"] == '["a","b"]'
    assert ann["price"] == "1.10"
    assert ann["big"] == "9007199254740993"
    assert ann["uid"] == str(UID)
    assert ann["active"] == "true"
    assert ann["address"] is None


@pytest.mark.usefixtures("server")
async def test_a_field_no_query_can_name_is_shown_and_offers_nothing() -> None:
    page = await adapter().fetch(FetchRequest(node_id=PEOPLE))
    columns = {column.name: column for column in page.columns}

    assert columns["odd.field"].filter_operators == []
    assert not columns["odd.field"].sortable
    with pytest.raises(ValueError):
        await adapter().fetch(
            FetchRequest(node_id=PEOPLE, filters=[NullFilter(column="odd.field", op="is_null")])
        )


@pytest.mark.usefixtures("server")
async def test_pages_follow_the_id_when_nothing_else_orders_them() -> None:
    first = await adapter().fetch(FetchRequest(node_id=NUMBERS, limit=100))
    third = await adapter().fetch(FetchRequest(node_id=NUMBERS, limit=100, offset=200))

    assert [row[0] for row in first.rows] == [str(index) for index in range(100)]
    assert first.has_more
    assert [row[0] for row in third.rows] == [str(index) for index in range(200, 250)]
    assert not third.has_more


@pytest.mark.usefixtures("server")
async def test_sorting_and_filtering_happen_on_the_server() -> None:
    source = adapter()

    sorted_page = await source.fetch(
        FetchRequest(node_id=NUMBERS, limit=5, sort=[Sort(column="n", descending=True)])
    )
    # Ties are broken by _id, so the order is the same every time.
    assert [row[0] for row in sorted_page.rows] == ["6", "13", "20", "27", "34"]

    compared = await source.fetch(
        FetchRequest(
            node_id=NUMBERS,
            limit=1000,
            filters=[ScalarFilter(column="n", op="gte", value="5"), ScalarFilter(column="n", op="lt", value="6")],
        )
    )
    assert {row[1] for row in compared.rows} == {"5"}
    assert len(compared.rows) == 35

    within = await source.fetch(
        FetchRequest(node_id=NUMBERS, filters=[InFilter(column="_id", op="in", values=["3", "249"])])
    )
    assert [row[0] for row in within.rows] == ["3", "249"]

    # A pattern's own characters are characters.
    contained = await source.fetch(
        FetchRequest(node_id=NUMBERS, filters=[ScalarFilter(column="label", op="contains", value="w 01")])
    )
    assert [row[2] for row in contained.rows][:2] == ["row 010", "row 011"]
    dotted = await source.fetch(
        FetchRequest(node_id=NUMBERS, filters=[ScalarFilter(column="label", op="contains", value=".")])
    )
    assert dotted.rows == []

    started = await source.fetch(
        FetchRequest(node_id=PEOPLE, filters=[ScalarFilter(column="name", op="starts_with", value="B")])
    )
    assert [row[1] for row in started.rows] == ["Bob"]

    by_id = await source.fetch(
        FetchRequest(node_id=PEOPLE, filters=[ScalarFilter(column="_id", op="eq", value=str(PEOPLE_IDS[1]))])
    )
    assert [row[1] for row in by_id.rows] == ["Bob"]

    born = await source.fetch(
        FetchRequest(node_id=PEOPLE, filters=[ScalarFilter(column="born", op="gt", value="1990-01-01")])
    )
    assert [row[1] for row in born.rows] == ["Ann"]

    # Null and absent alike.
    empty = await source.fetch(FetchRequest(node_id=PEOPLE, filters=[NullFilter(column="age", op="is_null")]))
    assert [row[1] for row in empty.rows] == ["Cy"]


@pytest.mark.usefixtures("server")
async def test_a_column_or_value_from_the_client_is_checked_first() -> None:
    source = adapter()

    with pytest.raises(ValueError, match="no column"):
        await source.fetch(FetchRequest(node_id=PEOPLE, filters=[NullFilter(column="$where", op="is_null")]))
    with pytest.raises(ValueError, match="Invalid value"):
        await source.fetch(FetchRequest(node_id=PEOPLE, filters=[ScalarFilter(column="_id", op="eq", value="{'$ne': 1}")]))
    with pytest.raises(ValueError, match="Cannot filter"):
        await source.fetch(FetchRequest(node_id=PEOPLE, filters=[ScalarFilter(column="age", op="contains", value="1")]))
    with pytest.raises(ValueError, match="Cannot sort"):
        await source.fetch(FetchRequest(node_id=PEOPLE, sort=[Sort(column="tags")]))
    # Text that looks like an operator is only text.
    looked = await source.fetch(
        FetchRequest(node_id=PEOPLE, filters=[ScalarFilter(column="name", op="eq", value='{"$ne": null}')])
    )
    assert looked.rows == []


@pytest.mark.usefixtures("server")
async def test_a_view_is_read_through_its_pipeline() -> None:
    page = await adapter().fetch(FetchRequest(node_id=relation_id(DATABASE, "adults")))

    assert [row[1] for row in page.rows] == ["Ann"]


# --- Summary and definition ----------------------------------------------


@pytest.mark.usefixtures("server")
async def test_the_summary_counts_the_model() -> None:
    summary = await adapter().node_summary(PEOPLE)

    assert summary.kind == "table"
    assert isinstance(summary.contents, RelationContents)
    assert summary.contents.schema_name == DATABASE
    assert summary.contents.indexes == 2
    assert summary.contents.row_estimate == 3


@pytest.mark.usefixtures("server")
async def test_the_definition_is_what_the_server_keeps() -> None:
    content = await adapter().read_content(
        ContentRequest(node_id=relation_id(DATABASE, "books"), representation="tree")
    )

    assert isinstance(content, JsonContent)
    assert isinstance(content.value, JsonObject)
    entries = {entry.name for entry in content.value.entries}
    assert entries == {"name", "type", "options", "indexes"}
    with pytest.raises(ValueError):
        await adapter().read_content(ContentRequest(node_id=PEOPLE, representation="sql"))
