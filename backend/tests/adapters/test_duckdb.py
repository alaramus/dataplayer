"""A DuckDB file of a person's storage as a source type (D387–D391).

No server is needed: every test writes its own file under a temporary home.
"""

import asyncio
import time
from pathlib import Path

import duckdb
import pytest
from pydantic import ValidationError

from app.adapters import registry
from app.adapters.catalog import SchemaNode, TableNode, ViewNode
from app.adapters.content import ContentRequest, SqlContent
from app.adapters.duckdb.adapter import DuckdbAdapter
from app.adapters.duckdb.options import DuckdbOptions
from app.adapters.duckdb.session import DuckdbSession, Reading
from app.adapters.fetch import FetchRequest, InFilter, NullFilter, ScalarFilter, Sort
from app.adapters.protocol import (
    AdapterError,
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
from app.adapters.relation import (
    CheckConstraint,
    ForeignKey,
    PrimaryKey,
    RelationModelsRequest,
    UniqueConstraint,
)
from app.adapters.summary import RelationContents
from app.core.translation import current_language
from tests.adapters.duckdb_fixture import FILE, add_reaching_view, build


@pytest.fixture
def home(tmp_path: Path) -> Path:
    build(tmp_path)
    return tmp_path


def _adapter(home: Path, path: str = FILE, *, create: bool = False) -> DuckdbAdapter:
    return DuckdbAdapter(DuckdbOptions(path=path, create=create), home)


def _session(home: Path) -> DuckdbSession:
    return DuckdbSession(DuckdbOptions(path=FILE), home)


async def _rows(adapter: DuckdbAdapter, node_id: str, **request: object) -> list[list[str | None]]:
    result = await adapter.fetch(FetchRequest(node_id=node_id, **request))  # type: ignore[arg-type]  # the request's own fields, by name
    return result.rows


def _tree(home: Path) -> set[Path]:
    return set(home.rglob("*"))


# --- What the type is ----------------------------------------------------


def test_the_type_is_registered_as_sql() -> None:
    kind = registry.get("duckdb")

    assert kind.adapter_class is DuckdbAdapter
    assert kind.category == "sql"


def test_it_claims_only_what_it_does(home: Path) -> None:
    adapter = _adapter(home)
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
    assert isinstance(adapter, SupportsUpdate)


# --- The file -------------------------------------------------------------


@pytest.mark.parametrize("path", ["../elsewhere.duckdb", "data/../../x.duckdb", "C:/x.duckdb", "", "/"])
def test_a_path_that_leaves_the_home_or_names_nothing_is_refused(path: str) -> None:
    with pytest.raises(ValidationError):
        DuckdbOptions(path=path)


async def test_the_file_is_checked(home: Path) -> None:
    result = await _adapter(home).check_connection()

    assert result.ok, result


async def test_a_missing_file_fails_the_check_and_is_not_made(home: Path) -> None:
    result = await _adapter(home, "data/missing.duckdb").check_connection()

    assert not result.ok
    assert result.error_kind == "config"
    assert result.message == "The database file does not exist"
    assert not (home / "data" / "missing.duckdb").exists()


async def test_a_missing_file_is_made_when_asked(home: Path) -> None:
    result = await _adapter(home, "data/new.duckdb", create=True).check_connection()

    assert result.ok, result
    assert (home / "data" / "new.duckdb").is_file()


async def test_a_file_that_is_not_a_database_says_so_in_the_requests_language(
    home: Path,
) -> None:
    (home / "data" / "notes.duckdb").write_bytes(b"not a database at all" * 500)

    token = current_language.set("ru")
    try:
        result = await _adapter(home, "data/notes.duckdb").check_connection()
    finally:
        current_language.reset(token)

    assert not result.ok
    assert result.error_kind == "config"
    assert result.message == "Файл не является базой данных DuckDB, которую может прочитать этот сервер"


async def test_a_csv_is_not_taken_for_an_empty_database(home: Path) -> None:
    # Handed a .csv, DuckDB opens an empty database in memory (D387).
    (home / "data" / "sales.csv").write_text("a\n1\n")

    result = await _adapter(home, "data/sales.csv").check_connection()

    assert not result.ok
    assert result.message == "The file is not a DuckDB database this server can read"


async def test_a_sqlite_file_says_what_it_is_not_where_the_server_keeps_extensions(
    home: Path,
) -> None:
    (home / "data" / "shop.db").write_bytes(b"SQLite format 3\x00" + b"\x00" * 4096)

    result = await _adapter(home, "data/shop.db").check_connection()

    assert not result.ok
    assert result.message == "The file is not a DuckDB database this server can read"


async def test_a_file_another_program_holds_is_in_use(home: Path) -> None:
    # Another process's lock is the same refusal as a different
    # configuration in this one: the file is held elsewhere.
    held = duckdb.connect(str(home / FILE), read_only=True)
    try:
        result = await _adapter(home).check_connection()
    finally:
        held.close()

    assert not result.ok
    assert result.error_kind == "locked"
    assert result.message == "The database file is in use by another program"


async def test_the_file_is_not_held_between_calls(home: Path) -> None:
    await _adapter(home).list_children(None)

    # Opened for writing by anybody else, which a held file would refuse.
    other = duckdb.connect(str(home / FILE))
    other.close()


# --- The engine's own containment (D388) ---------------------------------


async def test_a_file_of_the_home_is_read_through_the_tilde(home: Path) -> None:
    (home / "data" / "sales.csv").write_text("amount\n5\n")

    def read(reading: Reading) -> object:
        return reading.value("SELECT sum(amount) FROM '~/data/sales.csv'")

    assert await _session(home).read(read) == 5


@pytest.mark.parametrize(
    "statement",
    [
        "SELECT * FROM read_csv('{outside}')",
        "SELECT * FROM '~/../{outside_name}'",
        "SELECT * FROM read_csv('https://example.com/x.csv')",
        "INSTALL spatial",
        "FORCE INSTALL json",
        "INSTALL spatial FROM '~'",
        "LOAD spatial",
        "SET enable_external_access = true",
        "SET allowed_directories = ['/']",
        "SET home_directory = '/'",
    ],
)
async def test_nothing_reaches_past_the_home(
    home: Path, tmp_path_factory: pytest.TempPathFactory, statement: str
) -> None:
    outside = tmp_path_factory.mktemp("elsewhere") / "secret.csv"
    outside.write_text("x\n1\n")
    text = statement.format(
        outside=outside.as_posix(), outside_name=f"{outside.parent.name}/secret.csv"
    )

    before = _tree(home)

    with pytest.raises(AdapterError) as refused:
        await _session(home).read(lambda reading: reading.rows(text))

    assert str(outside.parent) not in refused.value.message
    # INSTALL would otherwise download into ~/.duckdb, the home itself.
    assert _tree(home) == before


async def test_a_view_reaching_past_the_home_is_refused_when_read(
    home: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    outside = tmp_path_factory.mktemp("elsewhere") / "secret.csv"
    outside.write_text("x\n1\n")
    add_reaching_view(home / FILE, outside)

    with pytest.raises(AdapterError) as refused:
        await _rows(_adapter(home), "main.reaching")

    assert refused.value.error_kind == "config"
    assert refused.value.message == (
        "The database reaches past your personal storage, which is refused"
    )


async def test_a_sort_too_big_for_memory_does_not_spill_into_the_home(home: Path) -> None:
    before = _tree(home)

    def read(reading: Reading) -> object:
        return reading.value(
            "SELECT count(*) FROM (SELECT repeat('x', 200) || i AS s FROM range(8000000) t(i) ORDER BY s)"
        )

    with pytest.raises(AdapterError):
        await _session(home).read(read)

    assert _tree(home) == before


async def test_a_request_that_goes_away_stops_its_statement(home: Path) -> None:
    def forever(reading: Reading) -> object:
        return reading.value("SELECT count(*) FROM range(1000000000000) a")

    task = asyncio.create_task(_session(home).read(forever))
    await asyncio.sleep(0.3)
    started = time.monotonic()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert time.monotonic() - started < 5


async def test_a_read_past_its_clock_is_stopped(home: Path) -> None:
    def forever(reading: Reading) -> object:
        return reading.value("SELECT count(*) FROM range(1000000000000) a")

    with pytest.raises(AdapterError) as refused:
        await _session(home).read(forever, seconds=0.3)

    assert refused.value.error_kind == "timeout"


# --- The catalog (D389) --------------------------------------------------


async def test_the_catalog_lists_the_files_schemas(home: Path) -> None:
    # The file's reports come after its schemas (D398).
    schemas = (await _adapter(home).list_children(None))[:-1]

    assert [node.id for node in schemas] == ["main", "sales\\.eu"]
    assert all(isinstance(node, SchemaNode) for node in schemas)
    assert [node.name for node in schemas] == ["main", "sales.eu"]


async def test_a_schema_lists_its_tables_and_views(home: Path) -> None:
    adapter = _adapter(home)

    relations = {node.name: node for node in await adapter.list_children("main")}
    dotted = await adapter.list_children("sales\\.eu")

    assert set(relations) == {"labels", "items", "events", "kinds", 'odd, "name"', "cheap"}
    assert isinstance(relations["items"], TableNode)
    assert isinstance(relations["cheap"], ViewNode)
    assert relations["items"].id == "main.items"
    assert [node.id for node in dotted] == ["sales\\.eu.orders"]


async def test_a_path_is_confirmed_in_the_file(home: Path) -> None:
    adapter = _adapter(home)

    path = await adapter.path_to("sales\\.eu.orders")

    assert [node.name for node in path] == ["sales.eu", "orders"]
    for missing in ("nowhere", "main.nothing", "nowhere.items"):
        with pytest.raises(NodeNotFound):
            await adapter.path_to(missing)
    with pytest.raises(NodeNotFound):
        await adapter.list_children("nowhere")


async def test_a_table_is_described_from_the_catalog(home: Path) -> None:
    model = await _adapter(home).relation_model("main.items")

    assert model.kind == "table"
    assert model.schema_name == "main"
    assert model.comment == "What the shop sells"
    assert [column.name for column in model.columns] == ["id", "name", "price", "label_id"]
    price = model.columns[2]
    assert price.type.category == "number"
    assert (price.type.precision, price.type.scale) == (10, 2)
    assert price.default == "0"
    assert model.columns[1].nullable is False
    kinds = {type(constraint) for constraint in model.constraints}
    assert kinds == {PrimaryKey, UniqueConstraint, ForeignKey, CheckConstraint}
    foreign = next(c for c in model.constraints if isinstance(c, ForeignKey))
    assert foreign.target_node_id == "main.labels"
    assert foreign.target_columns == ["id"]
    check = next(c for c in model.constraints if isinstance(c, CheckConstraint))
    assert "length" in check.expression
    assert [index.name for index in model.indexes] == ["items_price"]
    assert model.indexes[0].definition.startswith("CREATE INDEX items_price")


async def test_types_are_read_as_what_they_are(home: Path) -> None:
    model = await _adapter(home).relation_model("main.kinds")
    types = {column.name: column.type for column in model.columns}

    assert types["huge"].category == "number"
    assert types["moment"].category == "datetime"
    assert types["ident"].category == "uuid"
    assert types["feeling"].category == "enum"
    assert types["feeling"].enum_values == ["sad", "ok", "it's"]
    assert types["tags"].category == "array"
    assert types["tags"].element is not None and types["tags"].element.category == "string"
    assert types["point"].category == "composite"
    assert types["counts"].category == "composite"
    assert types["doc"].category == "json"
    assert types["picture"].category == "binary"
    assert types["span"].category == "other"


async def test_several_relations_are_described_on_one_connection(home: Path) -> None:
    models = await _adapter(home).relation_models_for_nodes(
        RelationModelsRequest(node_ids=["main.items", "sales\\.eu.orders", "main.nothing"])
    )

    assert [model.name for model in models] == ["items", "orders"]


async def test_a_summary_counts_the_model(home: Path) -> None:
    summary = await _adapter(home).node_summary("main.items")

    assert isinstance(summary.contents, RelationContents)
    assert summary.contents.columns == 4
    assert summary.contents.indexes == 1
    assert summary.contents.schema_name == "main"


async def test_the_ddl_is_the_files_own_with_its_indexes(home: Path) -> None:
    content = await _adapter(home).read_content(
        ContentRequest(node_id="main.items", representation="sql")
    )

    assert isinstance(content, SqlContent)
    assert content.text.startswith("CREATE TABLE items(")
    assert "CREATE INDEX items_price ON items" in content.text


# --- Values and pages (D390, D391) ---------------------------------------


async def test_a_page_follows_the_primary_key(home: Path) -> None:
    rows = await _rows(_adapter(home), "main.items", limit=2)

    assert [row[0] for row in rows] == ["1", "2"]


async def test_a_table_without_a_key_follows_the_rowid(home: Path) -> None:
    rows = await _rows(_adapter(home), "main.events", sort=[Sort(column="kind")])

    assert rows == [["a", "1"], ["a", "2"], ["b", "1"], ["c", "1"]]


async def test_a_column_called_rowid_leaves_a_table_without_a_tiebreak(home: Path) -> None:
    rows = await _rows(_adapter(home), 'main.odd, "name"')

    assert rows == [["x", "7"]]


async def test_values_cross_as_duckdbs_own_text(home: Path) -> None:
    result = await _adapter(home).fetch(FetchRequest(node_id="main.kinds"))
    names = [column.name for column in result.columns]
    first = dict(zip(names, result.rows[0], strict=True))

    assert first["huge"] == "170141183460469231731687303715884105727"
    assert first["exact"] == "12345678901234567890.0123456789"
    assert first["ratio"] == "0.1"
    assert first["picture"] == "0xAA00"
    assert first["active"] == "true"
    assert first["day"] == "2026-01-02"
    assert first["moment"] == "2026-01-02 00:04:05+00"
    assert first["span"] == "1 year 2 days 03:00:00"
    assert first["feeling"] == "it's"
    assert first["tags"] == '["a",null]'
    assert first["point"] == '{"x":1,"the label":"p"}'
    assert first["counts"] == '{"1":"one"}'
    assert first["doc"] == '{"k": [1, 2.50]}'
    assert all(value is None for value in result.rows[1][1:])
    assert result.update_supported is True


async def test_a_nested_column_does_not_sort(home: Path) -> None:
    adapter = _adapter(home)
    result = await adapter.fetch(FetchRequest(node_id="main.kinds"))
    sortable = {column.name: column.sortable for column in result.columns}

    assert sortable["tags"] is False
    assert sortable["point"] is False
    assert sortable["huge"] is True
    with pytest.raises(ValueError, match="cannot be sorted"):
        await _rows(adapter, "main.kinds", sort=[Sort(column="tags")])


async def test_filters_are_read_by_duckdb_as_the_columns_type(home: Path) -> None:
    adapter = _adapter(home)

    async def ids(*filters: object) -> list[str | None]:
        return [row[0] for row in await _rows(adapter, "main.kinds", filters=list(filters))]

    assert await ids(ScalarFilter(column="day", op="eq", value="2026-01-02")) == ["1"]
    assert await ids(ScalarFilter(column="moment", op="eq", value="2026-01-02 00:04:05Z")) == ["1"]
    assert await ids(
        ScalarFilter(column="exact", op="eq", value="12345678901234567890.0123456789")
    ) == ["1"]
    assert await ids(
        ScalarFilter(column="ident", op="eq", value="a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")
    ) == ["1"]
    assert await ids(InFilter(column="feeling", op="in", values=["it's", "sad"])) == ["1"]
    assert await ids(ScalarFilter(column="active", op="eq", value="true")) == ["1"]
    assert await ids(ScalarFilter(column="point", op="contains", value="THE LABEL")) == ["1"]
    assert await ids(NullFilter(column="tags", op="is_null")) == ["2"]


async def test_a_value_duckdb_cannot_read_is_the_readers_mistake(home: Path) -> None:
    with pytest.raises(ValueError, match="does not fit"):
        await _rows(
            _adapter(home),
            "main.kinds",
            filters=[ScalarFilter(column="day", op="eq", value="yesterday")],
        )


async def test_like_escapes_its_own_characters(home: Path) -> None:
    adapter = _adapter(home)

    async def names(value: str) -> list[str | None]:
        rows = await _rows(
            adapter, "main.items", filters=[ScalarFilter(column="name", op="contains", value=value)]
        )
        return [row[1] for row in rows]

    assert await names("%") == ["100% pure"]
    assert await names("_") == ["under_score"]
    assert await names("ONE") == ["one"]


@pytest.mark.parametrize(
    "request_",
    [
        {"sort": [Sort(column="nope")]},
        {"filters": [ScalarFilter(column="nope", op="eq", value="1")]},
        {"filters": [ScalarFilter(column="picture", op="eq", value="1")]},
        {"filters": [ScalarFilter(column="active", op="eq", value="yes")]},
    ],
)
async def test_a_request_the_relation_cannot_answer_is_refused(
    home: Path, request_: dict[str, object]
) -> None:
    with pytest.raises(ValueError):
        await _rows(_adapter(home), "main.kinds", **request_)


async def test_a_view_and_another_schema_are_read(home: Path) -> None:
    adapter = _adapter(home)

    assert await _rows(adapter, "main.cheap", sort=[Sort(column="id")]) == [
        ["1", "one", "1.50"],
        ["2", "two", "2.00"],
    ]
    assert await _rows(adapter, "sales\\.eu.orders") == [["10", "1"]]


async def test_a_missing_relation_is_not_found(home: Path) -> None:
    with pytest.raises(NodeNotFound):
        await _rows(_adapter(home), "main.nothing")
    with pytest.raises(ValueError):
        await _rows(_adapter(home), "main")
