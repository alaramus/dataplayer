"""A SQLite file of a person's storage as a source type (D247–D251).

No server is needed: every test writes its own file under a temporary home.
"""

import asyncio
import os
import sqlite3
import time
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.adapters import registry
from app.adapters.catalog import TableNode
from app.adapters.content import ContentRequest, SqlContent
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
from app.adapters.query import SupportsQuery
from app.adapters.relation import (
    CheckConstraint,
    ForeignKey,
    PrimaryKey,
    RelationModelsRequest,
    UniqueConstraint,
)
from app.adapters.sqlite.adapter import SqliteAdapter
from app.adapters.sqlite.options import SqliteOptions
from app.adapters.sqlite.session import Reading, SqliteSession
from app.adapters.summary import RelationContents
from app.core.translation import current_language
from tests.adapters.sqlite_fixture import FILE, add_ghost, analyze, build


@pytest.fixture
def home(tmp_path: Path) -> Path:
    build(tmp_path)
    return tmp_path


def _adapter(home: Path, path: str = FILE, *, create: bool = False) -> SqliteAdapter:
    return SqliteAdapter(SqliteOptions(path=path, create=create), home)


def _session(home: Path) -> SqliteSession:
    return SqliteSession(SqliteOptions(path=FILE), home)


async def _rows(
    adapter: SqliteAdapter, node_id: str, **request: object
) -> list[list[str | None]]:
    result = await adapter.fetch(FetchRequest(node_id=node_id, **request))  # type: ignore[arg-type]  # the request's own fields, by name
    return result.rows


# --- What the type is ----------------------------------------------------


def test_the_type_is_registered_as_sql() -> None:
    kind = registry.get("sqlite")

    assert kind.adapter_class is SqliteAdapter
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
    assert isinstance(adapter, SupportsQuery)
    assert isinstance(adapter, SupportsUpdate)


# --- The file -------------------------------------------------------------


@pytest.mark.parametrize("path", ["../elsewhere.db", "data/../../x.db", "C:/x.db", "", "/"])
def test_a_path_that_leaves_the_home_or_names_nothing_is_refused(path: str) -> None:
    with pytest.raises(ValidationError):
        SqliteOptions(path=path)


def test_a_path_is_stored_below_the_home_without_its_slash() -> None:
    assert SqliteOptions(path="/data/shop.db").path == "data/shop.db"


async def test_the_file_is_checked(home: Path) -> None:
    result = await _adapter(home).check_connection()

    assert result.ok, result


async def test_a_missing_file_fails_the_check_and_is_not_made(home: Path) -> None:
    result = await _adapter(home, "data/missing.db").check_connection()

    assert not result.ok
    assert result.error_kind == "config"
    assert result.message == "The database file does not exist"
    assert not (home / "data" / "missing.db").exists()


async def test_a_refusal_made_in_the_worker_thread_is_in_the_requests_language(
    home: Path,
) -> None:
    token = current_language.set("ru")
    try:
        result = await _adapter(home, "data/missing.db").check_connection()
    finally:
        current_language.reset(token)

    assert result.message == "Файл базы данных не существует"


async def test_a_missing_file_is_made_when_asked(home: Path) -> None:
    result = await _adapter(home, "data/new.db", create=True).check_connection()

    assert result.ok, result
    assert (home / "data" / "new.db").is_file()


async def test_a_file_is_not_made_in_a_folder_that_is_not_there(home: Path) -> None:
    result = await _adapter(home, "nowhere/new.db", create=True).check_connection()

    assert not result.ok
    assert result.message == "The folder for the database file does not exist"


async def test_a_folder_is_not_a_database(home: Path) -> None:
    result = await _adapter(home, "data").check_connection()

    assert not result.ok
    assert result.message == "The path names a folder, not a file"


async def test_a_file_that_is_not_a_database_says_so(home: Path) -> None:
    (home / "notes.db").write_text("this is a plain text file, not a database at all " * 10)

    result = await _adapter(home, "notes.db").check_connection()

    assert not result.ok
    assert result.error_kind == "config"
    assert result.message == "The file is not a SQLite database"


@pytest.mark.skipif(os.name != "posix", reason="Windows refuses a symlink without privileges")
async def test_a_link_out_of_the_home_is_refused(home: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    outside = tmp_path_factory.mktemp("outside") / "secret.db"
    sqlite3.connect(outside).close()
    (home / "link.db").symlink_to(outside)

    result = await _adapter(home, "link.db").check_connection()

    assert not result.ok
    assert result.message == "The path must stay inside your personal storage"


# --- What a connection cannot do (D247) -------------------------------------


@pytest.mark.parametrize(
    "statement",
    [
        "ATTACH DATABASE '{other}' AS other",
        "ATTACH DATABASE ':memory:' AS other",
        "DETACH DATABASE main",
        "VACUUM INTO '{other}'",
        "SELECT load_extension('anything')",
        "SELECT fts3_tokenizer('simple')",
        "PRAGMA temp_store_directory = '{folder}'",
        "INSERT INTO labels (name) VALUES ('blue')",
    ],
)
async def test_a_statement_reaching_past_the_file_or_writing_is_refused(
    home: Path, tmp_path_factory: pytest.TempPathFactory, statement: str
) -> None:
    folder = tmp_path_factory.mktemp("other")
    other = folder / "other.db"

    with pytest.raises(AdapterError):
        await _session(home).read(
            lambda reading: reading.rows(statement.format(other=other, folder=folder))
        )
    assert not other.exists()


async def test_a_request_that_goes_away_stops_its_statement(home: Path) -> None:
    endless = (
        "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n) "
        "SELECT count(*) FROM n"
    )
    task = asyncio.create_task(_session(home).read(lambda reading: reading.value(endless)))
    await asyncio.sleep(0.2)
    started = time.monotonic()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert time.monotonic() - started < 2


async def test_a_read_past_its_clock_is_stopped(home: Path) -> None:
    endless = (
        "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n) "
        "SELECT count(*) FROM n"
    )

    def work(reading: Reading) -> object:
        return reading.value(endless)

    with pytest.raises(AdapterError) as failure:
        await _session(home).read(work, seconds=0.2)
    assert failure.value.error_kind == "timeout"


# --- The catalog (D248) -----------------------------------------------------


async def test_the_catalog_has_one_schema(home: Path) -> None:
    nodes = await _adapter(home).list_children(None)

    assert [(node.id, node.kind) for node in nodes] == [("main", "schema")]


async def test_the_schema_lists_tables_views_and_virtual_tables(home: Path) -> None:
    nodes = await _adapter(home).list_children("main")
    by_name = {node.name: node for node in nodes}

    assert {"items", "labels", "events", 'odd, "name"', "pairs", "cheap", "notes"} <= set(by_name)
    assert by_name["cheap"].kind == "view"
    assert by_name["items"].kind == "table"
    assert by_name["items"].id == "main.items"
    # The library's own tables and FTS5's shadow tables are marked (D248).
    for system in ("sqlite_schema", "sqlite_sequence", "notes_data", "notes_config"):
        node = by_name[system]
        assert isinstance(node, TableNode) and node.is_system, system
    items = by_name["items"]
    assert isinstance(items, TableNode) and not items.is_system


async def test_estimates_come_only_from_analyze(home: Path) -> None:
    before = {node.name: node for node in await _adapter(home).list_children("main")}
    analyze(home / FILE)
    after = {node.name: node for node in await _adapter(home).list_children("main")}

    assert isinstance(before["items"], TableNode)
    assert isinstance(after["items"], TableNode)
    assert before["items"].row_count_estimate is None
    assert after["items"].row_count_estimate == 4


async def test_a_path_is_confirmed_in_the_file(home: Path) -> None:
    adapter = _adapter(home)

    path = await adapter.path_to("main.items")

    assert [node.id for node in path] == ["main", "main.items"]
    for missing in ("main.nothing", "temp.items", "other"):
        with pytest.raises(NodeNotFound):
            await adapter.path_to(missing)


async def test_a_virtual_table_whose_module_is_missing_is_listed_and_explained(
    home: Path,
) -> None:
    add_ghost(home / FILE)
    adapter = _adapter(home)

    names = {node.name for node in await adapter.list_children("main")}
    with pytest.raises(AdapterError) as failure:
        await adapter.relation_model("main.ghost")

    assert "ghost" in names
    assert failure.value.error_kind == "config"
    assert "needs a module" in failure.value.message


# --- The relation model (D249) ----------------------------------------------


async def test_a_table_is_described_from_its_pragmas_and_its_text(home: Path) -> None:
    model = await _adapter(home).relation_model("main.items")
    columns = {column.name: column for column in model.columns}

    assert [column.name for column in model.columns][:3] == ["id", "name", "price"]
    assert columns["id"].identity == "by_default"
    assert columns["id"].nullable is False
    assert columns["name"].collation == "NOCASE"
    assert columns["doubled"].generated == "price * 2"
    assert columns["price"].default == "0"
    assert columns["price"].type.precision == 10
    assert columns["price"].type.scale == 2
    categories = {name: column.type.category for name, column in columns.items()}
    assert categories == {
        "id": "number",
        "name": "string",
        "price": "number",
        "doubled": "number",
        "label_id": "number",
        "picture": "binary",
        "loose": "other",
        "active": "boolean",
        "made_at": "datetime",
    }


async def test_constraints_carry_the_names_they_were_given(home: Path) -> None:
    model = await _adapter(home).relation_model("main.items")
    by_kind: dict[str, list[object]] = {}
    for constraint in model.constraints:
        by_kind.setdefault(constraint.kind, []).append(constraint)

    primary = by_kind["primary_key"][0]
    assert isinstance(primary, PrimaryKey)
    assert (primary.name, primary.columns) == ("PRIMARY KEY", ["id"])
    unique = by_kind["unique"][0]
    assert isinstance(unique, UniqueConstraint)
    assert (unique.name, unique.columns) == ('UNIQUE ("name", "price")', ["name", "price"])
    foreign = by_kind["foreign_key"][0]
    assert isinstance(foreign, ForeignKey)
    # A key naming no columns points at the target's primary key.
    assert (foreign.name, foreign.target_node_id, foreign.target_columns, foreign.on_delete) == (
        "to_label",
        "main.labels",
        ["id"],
        "cascade",
    )
    checks = [check for check in by_kind["check"] if isinstance(check, CheckConstraint)]
    assert [(check.name, check.expression) for check in checks] == [
        ("CHECK 1", "length(name) > 0"),
        ("positive", "price >= 0"),
    ]


async def test_indexes_carry_their_text_and_condition(home: Path) -> None:
    model = await _adapter(home).relation_model("main.items")
    indexes = {index.name: index for index in model.indexes}

    expensive = indexes["items_expensive"]
    assert expensive.predicate == "price > 5"
    assert expensive.definition.startswith("CREATE INDEX items_expensive")
    made = next(index for index in model.indexes if index.name.startswith("sqlite_autoindex"))
    assert made.unique and made.definition == 'UNIQUE ("name", "price")'


async def test_odd_names_and_a_table_without_rowid_are_described(home: Path) -> None:
    adapter = _adapter(home)

    odd = await adapter.relation_model('main.odd, "name"')
    pairs = await adapter.relation_model("main.pairs")

    assert [column.name for column in odd.columns] == ["a b", "c", "d"]
    primary = next(c for c in pairs.constraints if isinstance(c, PrimaryKey))
    assert primary.columns == ["left_id", "right_id"]
    foreign = next(c for c in pairs.constraints if isinstance(c, ForeignKey))
    assert (foreign.name, foreign.target_columns) == ('FOREIGN KEY ("left_id")', ["id"])


async def test_several_relations_are_described_on_one_connection(home: Path) -> None:
    adapter = _adapter(home)

    models = await adapter.relation_models_for_nodes(
        RelationModelsRequest(node_ids=["main.items", "main.nothing", "main.cheap"])
    )

    assert sorted(model.node_id for model in models) == ["main.cheap", "main.items"]


async def test_a_summary_counts_the_model(home: Path) -> None:
    summary = await _adapter(home).node_summary("main.items")

    assert isinstance(summary.contents, RelationContents)
    assert summary.contents.schema_name == "main"
    assert summary.contents.columns == 9
    assert summary.contents.constraints == 5


async def test_the_ddl_is_the_files_own_with_its_indexes_and_triggers(home: Path) -> None:
    content = await _adapter(home).read_content(
        ContentRequest(node_id="main.items", representation="sql")
    )

    assert isinstance(content, SqlContent)
    assert content.text.startswith('CREATE TABLE "items"')
    assert "CREATE INDEX items_expensive" in content.text
    assert "CREATE TRIGGER items_named" in content.text


# --- Pages (D250, D251) -------------------------------------------------------


async def test_a_page_follows_the_primary_key(home: Path) -> None:
    result = await _adapter(home).fetch(FetchRequest(node_id="main.items", limit=2))

    assert [row[0] for row in result.rows] == ["1", "2"]
    assert result.has_more is True
    assert result.update_supported is True
    assert all(result.row_handles)
    assert [reference.name for reference in result.references] == ["to_label"]


async def test_a_table_without_a_key_follows_the_rowid(home: Path) -> None:
    rows = await _rows(_adapter(home), "main.events", sort=[Sort(column="at")], limit=3)

    # Ties on `at` come in the order the rows were written.
    assert [row[0] for row in rows] == ["b", "a", "c"]


async def test_values_are_written_by_what_they_are(home: Path) -> None:
    adapter = _adapter(home)
    items = await _rows(adapter, "main.items")
    events = await _rows(adapter, "main.events")

    one = items[0]
    assert one[5] == "0x00FF"
    assert one[2] == "1.5"
    assert one[3] == "3.0"
    assert one[7] == "true"
    assert items[1][7] == "false"
    # A column with no type keeps each value's own class.
    assert [row[6] for row in items] == ["10", "ten", "3.25", None]
    assert [row[0] for row in events][4:] == ["0xFFFE", "big"]
    assert events[5][1] == "9007199254740993"


async def test_filters_bind_numbers_as_numbers_and_escape_like(home: Path) -> None:
    adapter = _adapter(home)

    priced = await _rows(
        adapter, "main.items", filters=[ScalarFilter(column="price", op="gte", value="9")]
    )
    pure = await _rows(
        adapter, "main.items", filters=[ScalarFilter(column="name", op="contains", value="0%")]
    )
    underscore = await _rows(
        adapter, "main.items", filters=[ScalarFilter(column="name", op="contains", value="r_s")]
    )
    loose = await _rows(
        adapter, "main.items", filters=[InFilter(column="loose", op="in", values=["10", "ten"])]
    )
    empty = await _rows(
        adapter, "main.items", filters=[NullFilter(column="label_id", op="is_null")]
    )
    active = await _rows(
        adapter, "main.items", filters=[ScalarFilter(column="active", op="eq", value="false")]
    )

    assert [row[1] for row in priced] == ["100% pure", "under_score"]
    assert [row[1] for row in pure] == ["100% pure"]
    assert [row[1] for row in underscore] == ["under_score"]
    assert [row[1] for row in loose] == ["one", "two"]
    assert [row[1] for row in empty] == ["100% pure", "under_score"]
    assert [row[1] for row in active] == ["two"]


@pytest.mark.parametrize(
    "request_fields",
    [
        {"filters": [ScalarFilter(column="nothing", op="eq", value="1")]},
        {"sort": [Sort(column="nothing")]},
        {"filters": [ScalarFilter(column="price", op="eq", value="cheap")]},
        {"filters": [ScalarFilter(column="picture", op="eq", value="0x00")]},
    ],
)
async def test_a_request_the_relation_cannot_answer_is_refused(
    home: Path, request_fields: dict[str, object]
) -> None:
    with pytest.raises(ValueError):
        await _rows(_adapter(home), "main.items", **request_fields)


async def test_a_view_and_a_virtual_table_are_read(home: Path) -> None:
    adapter = _adapter(home)

    cheap = await _rows(adapter, "main.cheap")
    notes = await _rows(adapter, "main.notes")

    assert [row[1] for row in cheap] == ["one", "two"]
    assert notes == [["hello world"]]


async def test_a_missing_relation_is_not_found(home: Path) -> None:
    with pytest.raises(NodeNotFound):
        await _rows(_adapter(home), "main.nothing")
