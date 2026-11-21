"""DuckDB's reports, search, export and catalog actions (D398, D399).

Every test writes its own file under a temporary home.
"""

from pathlib import Path

import duckdb
import pytest

from app.adapters.actions import (
    ActionDownload,
    ActionRefused,
    Previews,
    ProducesDownload,
    TakesFile,
    TakesNodeSet,
    TakesParams,
)
from app.adapters.catalog import ReportNode, SchemaNode, TableNode
from app.adapters.content import ContentRequest, SqlContent
from app.adapters.duckdb.adapter import DuckdbAdapter
from app.adapters.duckdb.options import DuckdbOptions
from app.adapters.duckdb.reports import SECTION_ID
from app.adapters.export import ExportRequest
from app.adapters.fetch import FetchRequest, ScalarFilter, Sort
from app.adapters.protocol import (
    EnumeratesNames,
    SearchesColumns,
    SupportsExport,
    SupportsNodeSearch,
)
from app.adapters.search import (
    NodeSearchRequest,
    SearchBounds,
    class_of_name,
    class_rank,
    words_of,
)
from tests.adapters.duckdb_fixture import FILE, build
from tests.utils.word_cases import CASES


@pytest.fixture
def home(tmp_path: Path) -> Path:
    build(tmp_path)
    return tmp_path


@pytest.fixture
def adapter(home: Path) -> DuckdbAdapter:
    return DuckdbAdapter(DuckdbOptions(path=FILE), home)


def _run(home: Path, statement: str) -> list[tuple[object, ...]]:
    connection = duckdb.connect(str(home / FILE))
    try:
        return list(connection.execute(statement).fetchall())
    finally:
        connection.close()


async def _names(adapter: DuckdbAdapter, schema: str = "main") -> set[str]:
    return {node.name for node in await adapter.list_children(schema)}


async def _perform(adapter: DuckdbAdapter, name: str, node_id: str | None, params: dict[str, object]) -> None:
    action = adapter.action(name)
    assert isinstance(action, TakesParams)
    await action.perform(node_id, params)


class Upload:
    """The smallest thing that satisfies FilePayload."""

    def __init__(self, body: bytes, filename: str | None = "codes.csv") -> None:
        self.filename = filename
        self._body = body

    async def read(self, size: int) -> bytes:
        chunk, self._body = self._body[:size], self._body[size:]
        return chunk


def test_the_type_claims_search_and_export(adapter: DuckdbAdapter) -> None:
    for capability in (SupportsExport, SupportsNodeSearch, SearchesColumns, EnumeratesNames):
        assert isinstance(adapter, capability)


# --- Reports (D398) -------------------------------------------------------------


async def test_the_reports_sit_after_the_schemas(adapter: DuckdbAdapter) -> None:
    root = await adapter.list_children(None)
    reports = await adapter.list_children(SECTION_ID)

    assert [node.id for node in root] == ["main", "sales\\.eu", SECTION_ID]
    assert all(isinstance(node, ReportNode) for node in reports)
    assert [node.id.split("/")[1] for node in reports] == [
        "database", "sequences", "types", "macros", "functions",
    ]
    path = await adapter.path_to(f"{SECTION_ID}/types")
    assert [node.id for node in path] == [SECTION_ID, f"{SECTION_ID}/types"]


async def test_a_report_is_read_like_a_table_and_changes_nothing(adapter: DuckdbAdapter, home: Path) -> None:
    _run(home, "CREATE SEQUENCE counter START 7; CREATE MACRO twice(x) AS x * 2")

    database = await adapter.fetch(FetchRequest(node_id=f"{SECTION_ID}/database", limit=50))
    types = await adapter.fetch(FetchRequest(node_id=f"{SECTION_ID}/types"))
    sequences = await adapter.fetch(FetchRequest(node_id=f"{SECTION_ID}/sequences"))
    macros = await adapter.fetch(FetchRequest(node_id=f"{SECTION_ID}/macros"))
    functions = await adapter.fetch(
        FetchRequest(
            node_id=f"{SECTION_ID}/functions",
            filters=[ScalarFilter(column="name", op="starts_with", value="upper")],
            sort=[Sort(column="kind")],
        )
    )
    statement = await adapter.read_content(
        ContentRequest(node_id=f"{SECTION_ID}/sequences", representation="sql")
    )

    settings = {row[0]: row[1] for row in database.rows}
    assert settings["version"] == "v" + duckdb.__version__
    assert int(settings["block_size"] or 0) > 0
    assert "memory_limit" not in settings
    assert [row[:3] for row in types.rows] == [["main", "mood", "ENUM"]]
    assert [(row[1], row[2]) for row in sequences.rows] == [("counter", "7")]
    assert [(row[1], row[3], row[4]) for row in macros.rows] == [("twice", "x", "(x * 2)")]
    assert functions.rows and all((row[0] or "").startswith("upper") for row in functions.rows)
    assert database.update_supported is False and database.record_supported is False
    assert database.row_handles == [None] * len(database.rows)
    assert "create_relation" not in database.page_commands
    assert isinstance(statement, SqlContent) and "duckdb_sequences()" in statement.text


async def test_no_report_names_a_path_of_the_server(adapter: DuckdbAdapter, home: Path) -> None:
    for report in await adapter.list_children(SECTION_ID):
        page = await adapter.fetch(FetchRequest(node_id=report.id, limit=500))
        text = repr(page.rows)
        assert str(home) not in text and home.as_posix() not in text


async def test_an_unknown_report_is_refused(adapter: DuckdbAdapter) -> None:
    with pytest.raises(ValueError, match="not a report"):
        await adapter.fetch(FetchRequest(node_id=f"{SECTION_ID}/settings"))


# --- Export -------------------------------------------------------------------------


async def test_every_matching_row_is_exported_in_the_pages_order(adapter: DuckdbAdapter) -> None:
    batches = [
        batch
        async for batch in adapter.export_rows(
            ExportRequest(
                node_id="main.items",
                columns=["name", "price"],
                filters=[ScalarFilter(column="price", op="gte", value="2")],
                sort=[Sort(column="price", descending=True)],
            )
        )
    ]

    rows = [row for batch in batches for row in batch.rows]
    assert rows == [["under_score", "12.00"], ["100% pure", "9.00"], ["two", "2.00"]]


async def test_nested_values_are_exported_as_the_page_shows_them(adapter: DuckdbAdapter) -> None:
    page = await adapter.fetch(FetchRequest(node_id="main.kinds", limit=1))
    exported = [
        row
        async for batch in adapter.export_rows(ExportRequest(node_id="main.kinds", columns=[c.name for c in page.columns]))
        for row in batch.rows
    ]

    assert exported[0] == page.rows[0]


async def test_an_unknown_export_column_is_refused(adapter: DuckdbAdapter) -> None:
    with pytest.raises(ValueError):
        async for _ in adapter.export_rows(ExportRequest(node_id="main.items", columns=["nothing"])):
            pass


async def test_a_report_is_exported(adapter: DuckdbAdapter) -> None:
    rows = [
        row
        async for batch in adapter.export_rows(
            ExportRequest(node_id=f"{SECTION_ID}/types", columns=["name", "kind"])
        )
        for row in batch.rows
    ]

    assert rows == [["mood", "ENUM"]]


# --- Search -------------------------------------------------------------------------


@pytest.fixture
def words(tmp_path: Path) -> DuckdbAdapter:
    """A view per name of the word table, one of each name DuckDB tells apart."""
    seen: set[str] = set()
    names: list[str] = []
    for name in sorted({name for _, name, _ in CASES} | {"aaa_xorders", "zzz_orders"}):
        if name.lower() not in seen:
            seen.add(name.lower())
            names.append(name)
    connection = duckdb.connect(str(tmp_path / "words.duckdb"))
    for name in names:
        quoted = name.replace('"', '""')
        connection.execute(f'CREATE VIEW "{quoted}" AS SELECT 1 AS one')  # noqa: S608 — the test's own names
    connection.execute("CREATE SCHEMA crm; CREATE TABLE crm.buyers (id INTEGER, customer_email VARCHAR)")
    connection.close()
    return DuckdbAdapter(DuckdbOptions(path="words.duckdb"), tmp_path)


async def _find(adapter: DuckdbAdapter, query: str, *, node_id: str | None = None, limit: int = 100) -> list[str]:
    found = await adapter.search_nodes(
        NodeSearchRequest(query=query, node_id=node_id, limit=limit), SearchBounds.within(10)
    )
    return [match.node.name for match in found.matches]


@pytest.mark.parametrize("typed", sorted({typed for typed, _, _ in CASES}))
async def test_names_are_found_and_ordered_by_the_word_table(words: DuckdbAdapter, typed: str) -> None:
    names = await _find(words, typed)

    classes = [class_of_name(words_of(typed), name) for name in names]
    assert None not in classes
    ranks = [class_rank(one) for one in classes if one is not None]
    assert ranks == sorted(ranks)


async def test_a_relation_is_found_by_its_column_and_says_which(words: DuckdbAdapter) -> None:
    found = await words.search_columns(NodeSearchRequest(query="email"), SearchBounds.within(10))

    [match] = found.matches
    assert (match.node.name, match.excerpt, match.parent_id, match.location) == (
        "buyers", "customer_email", "crm", "crm",
    )


async def test_a_search_is_held_to_its_schema(words: DuckdbAdapter) -> None:
    assert await _find(words, "buyers", node_id="crm") == ["buyers"]
    assert await _find(words, "buyers", node_id="main") == []
    assert await _find(words, "crm") == ["crm"]
    with pytest.raises(ValueError, match="A search starts"):
        await _find(words, "buyers", node_id="crm.buyers")


async def test_the_reports_are_found_by_their_titles(adapter: DuckdbAdapter) -> None:
    found = await adapter.search_nodes(NodeSearchRequest(query="macro", node_id=SECTION_ID))

    assert [match.node.id for match in found.matches] == [f"{SECTION_ID}/macros"]


async def test_names_are_enumerated_for_a_kept_list(adapter: DuckdbAdapter) -> None:
    batches = [batch async for batch in adapter.enumerate_names(1000, SearchBounds.within(10))]

    names = [(name.node.id, name.parent_id) for batch in batches for name in batch.names]
    assert ("main", None) in names and ("sales\\.eu.orders", "sales\\.eu") in names


async def test_a_found_table_is_the_node_its_listing_gives(adapter: DuckdbAdapter) -> None:
    found = await adapter.search_nodes(NodeSearchRequest(query="labels"), SearchBounds.within(10))
    listed = [node for node in await adapter.list_children("main") if node.name == "labels"]

    assert isinstance(found.matches[0].node, TableNode)
    assert found.matches[0].node == listed[0]


# --- Actions (D399) ----------------------------------------------------------------


async def test_what_each_node_offers(adapter: DuckdbAdapter) -> None:
    at_top = [action.name for action in await adapter.available(None)]
    on_main = [action.name for action in await adapter.available("main")]
    on_other = [action.name for action in await adapter.available("sales\\.eu")]
    on_table = [action.name for action in await adapter.available("main.items")]

    assert at_top == ["create_schema"]
    assert on_main == ["load_csv", "create_table", "describe_model"]
    assert on_other == ["load_csv", "create_table", "drop_schema", "describe_model"]
    assert on_table == ["rename_relation", "drop_relation", "describe_model"]
    assert await adapter.available(f"{SECTION_ID}/types") == []


async def test_a_plain_table_is_renamed(adapter: DuckdbAdapter, home: Path) -> None:
    await _perform(adapter, "rename_relation", "main.events", {"new_name": "happenings"})

    assert "happenings" in await _names(adapter)
    assert _run(home, "SELECT count(*) FROM happenings") == [(4,)]


async def test_a_table_with_a_foreign_key_is_not_renamed(adapter: DuckdbAdapter, home: Path) -> None:
    _run(home, "DROP VIEW cheap; DROP INDEX items_price")

    with pytest.raises(ActionRefused, match="foreign key is not renamed"):
        await _perform(adapter, "rename_relation", "main.items", {"new_name": "goods"})
    # What the refusal protects: labels' rows can still be deleted.
    _run(home, "DELETE FROM items; DELETE FROM labels")


async def test_a_table_something_depends_on_is_refused_with_the_reason(adapter: DuckdbAdapter) -> None:
    with pytest.raises(ActionRefused, match="cannot rename a table while"):
        await _perform(adapter, "rename_relation", "main.labels", {"new_name": "tags"})


async def test_a_rename_that_breaks_a_view_is_refused(adapter: DuckdbAdapter, home: Path) -> None:
    _run(home, "CREATE TABLE plain (x INTEGER); CREATE VIEW reader AS SELECT * FROM plain")

    with pytest.raises(ActionRefused, match="reader"):
        await _perform(adapter, "rename_relation", "main.plain", {"new_name": "flat"})
    assert "plain" in await _names(adapter)


async def test_a_view_is_renamed_and_a_taken_name_refused(adapter: DuckdbAdapter, home: Path) -> None:
    await _perform(adapter, "rename_relation", "main.cheap", {"new_name": "bargains"})
    assert _run(home, "SELECT count(*) FROM bargains") == [(2,)]

    with pytest.raises(ActionRefused, match="already has a relation"):
        await _perform(adapter, "rename_relation", "main.bargains", {"new_name": "ITEMS"})


async def test_a_drop_is_rehearsed_and_says_what_it_would_do(adapter: DuckdbAdapter) -> None:
    drop = adapter.action("drop_relation")
    assert isinstance(drop, Previews)

    items = await drop.preview("main.items", {})
    labels = await drop.preview("main.labels", {})

    assert items.blocked is False
    assert items.items == ["View cheap will stop working"]
    assert labels.blocked is True
    assert labels.items == ["items refers to labels through items_label_id_id_fkey"]
    assert {"items", "labels", "cheap"} <= await _names(adapter)


async def test_a_set_is_dropped_children_first(adapter: DuckdbAdapter) -> None:
    drop = adapter.action("drop_relation")
    assert isinstance(drop, TakesNodeSet)

    preview = await drop.preview_on_set(["main.labels", "main.items", "main.cheap"], {})
    await drop.perform_on_set(["main.labels", "main.items", "main.cheap"], {})

    assert preview.blocked is False and preview.items == []
    assert {"labels", "items", "cheap"}.isdisjoint(await _names(adapter))


async def test_a_sequence_only_the_dropped_table_used_goes_with_it(adapter: DuckdbAdapter, home: Path) -> None:
    _run(
        home,
        "CREATE SEQUENCE own; CREATE SEQUENCE shared; "
        "CREATE TABLE counted (id BIGINT DEFAULT nextval('own'), n BIGINT DEFAULT nextval('shared')); "
        "CREATE TABLE other (n BIGINT DEFAULT nextval('shared'))",
    )
    drop = adapter.action("drop_relation")
    assert isinstance(drop, Previews)

    preview = await drop.preview("main.counted", {})
    await _perform(adapter, "drop_relation", "main.counted", {})

    assert preview.items == ["Sequence own goes with it: only what is dropped takes values from it"]
    assert _run(home, "SELECT sequence_name FROM duckdb_sequences() ORDER BY 1") == [("shared",)]


async def test_a_dropped_table_out_of_a_set_refuses_while_a_key_points_at_it(adapter: DuckdbAdapter) -> None:
    drop = adapter.action("drop_relation")
    assert isinstance(drop, TakesNodeSet)

    with pytest.raises(ActionRefused, match="items refers to labels"):
        await drop.perform_on_set(["main.labels"], {})


async def test_a_schema_is_made_and_dropped_with_what_it_holds(adapter: DuckdbAdapter, home: Path) -> None:
    await _perform(adapter, "create_schema", None, {"name": "staging"})
    assert "staging" in {node.name for node in await adapter.list_children(None)}
    with pytest.raises(ActionRefused, match="already exists"):
        await _perform(adapter, "create_schema", None, {"name": "Staging"})

    _run(home, "CREATE VIEW main.reads_orders AS SELECT * FROM \"sales.eu\".orders")
    drop = adapter.action("drop_schema")
    assert isinstance(drop, Previews)
    refused = await drop.preview("sales\\.eu", {})
    told = await drop.preview("sales\\.eu", {"cascade": True})

    assert refused.blocked is True and refused.items == ["1 tables and their rows"]
    assert told.blocked is False
    assert told.items == ["Drop 1 tables and their rows", "View reads_orders will stop working"]
    await _perform(adapter, "drop_schema", "sales\\.eu", {"cascade": True})
    assert "sales.eu" not in {node.name for node in await adapter.list_children(None)}


async def test_main_is_not_dropped(adapter: DuckdbAdapter) -> None:
    with pytest.raises(ActionRefused, match="keeps the schema main"):
        await _perform(adapter, "drop_schema", "main", {"cascade": True})


async def test_a_csv_file_becomes_a_table(adapter: DuckdbAdapter) -> None:
    action = adapter.action("load_csv")
    assert isinstance(action, TakesFile)

    await action.perform_with_file("sales\\.eu", {}, Upload(b"code,label\nA1,first\nB2,second\n"))
    page = await adapter.fetch(FetchRequest(node_id="sales\\.eu.codes"))

    assert [column.type.category for column in page.columns] == ["string", "string"]
    assert sorted(page.rows) == [["A1", "first"], ["B2", "second"]]


async def test_the_model_is_written_out(adapter: DuckdbAdapter) -> None:
    action = adapter.action("describe_model")
    assert isinstance(action, ProducesDownload)

    download = await action.download(["main"], {"dialect": "dbml"})

    assert isinstance(download, ActionDownload)
    text = b"".join([chunk async for chunk in download.body]).decode()
    assert "main.items" in text and "main.cheap" in text


async def test_a_created_schema_is_a_schema_node(adapter: DuckdbAdapter) -> None:
    await _perform(adapter, "create_schema", None, {"name": "x.y"})

    [node] = [node for node in await adapter.list_children(None) if node.name == "x.y"]
    assert isinstance(node, SchemaNode) and node.id == "x\\.y"
