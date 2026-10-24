"""SQLite's reports, search, export and catalog actions (D257, D258).

Every test writes its own file under a temporary home.
"""

import sqlite3
from pathlib import Path

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
from app.adapters.catalog import ReportNode, TableNode
from app.adapters.content import ContentRequest, SqlContent
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
from app.adapters.sqlite.adapter import SqliteAdapter
from app.adapters.sqlite.options import SqliteOptions
from app.adapters.sqlite.reports import SECTION_ID
from tests.adapters.sqlite_fixture import FILE, build
from tests.utils.word_cases import CASES


@pytest.fixture
def home(tmp_path: Path) -> Path:
    build(tmp_path)
    return tmp_path


@pytest.fixture
def adapter(home: Path) -> SqliteAdapter:
    return SqliteAdapter(SqliteOptions(path=FILE), home)


def _run(home: Path, statement: str) -> list[tuple[object, ...]]:
    connection = sqlite3.connect(home / FILE)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        rows = list(connection.execute(statement).fetchall())
        connection.commit()
        return rows
    finally:
        connection.close()


def _script(home: Path, script: str) -> None:
    connection = sqlite3.connect(home / FILE)
    try:
        connection.executescript(script)
    finally:
        connection.close()


async def _names(adapter: SqliteAdapter) -> set[str]:
    return {node.name for node in await adapter.list_children("main")}


async def _perform(adapter: SqliteAdapter, name: str, node_id: str, params: dict[str, object]) -> None:
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


def test_the_type_claims_search_and_export(adapter: SqliteAdapter) -> None:
    for capability in (SupportsExport, SupportsNodeSearch, SearchesColumns, EnumeratesNames):
        assert isinstance(adapter, capability)


# --- Reports (D257) ---------------------------------------------------------------


async def test_the_reports_sit_after_main(adapter: SqliteAdapter) -> None:
    root = await adapter.list_children(None)
    reports = await adapter.list_children(SECTION_ID)

    assert [node.id for node in root] == ["main", SECTION_ID]
    assert all(isinstance(node, ReportNode) for node in reports)
    assert [node.id for node in reports][:3] == [f"{SECTION_ID}/file", f"{SECTION_ID}/integrity", f"{SECTION_ID}/broken_keys"]
    path = await adapter.path_to(f"{SECTION_ID}/functions")
    assert [node.id for node in path] == [SECTION_ID, f"{SECTION_ID}/functions"]


async def test_a_report_is_read_like_a_table_and_changes_nothing(adapter: SqliteAdapter) -> None:
    file = await adapter.fetch(FetchRequest(node_id=f"{SECTION_ID}/file", limit=50))
    integrity = await adapter.fetch(FetchRequest(node_id=f"{SECTION_ID}/integrity"))
    functions = await adapter.fetch(
        FetchRequest(
            node_id=f"{SECTION_ID}/functions",
            filters=[ScalarFilter(column="name", op="eq", value="upper")],
            sort=[Sort(column="arguments")],
        )
    )
    statement = await adapter.read_content(
        ContentRequest(node_id=f"{SECTION_ID}/triggers", representation="sql")
    )

    settings = {row[0]: row[1] for row in file.rows}
    assert settings["encoding"] == "UTF-8"
    assert int(settings["page_size"] or 0) > 0
    assert integrity.rows == [["ok"]]
    assert functions.rows and all(row[0] == "upper" for row in functions.rows)
    assert file.update_supported is False and file.record_supported is False
    assert "create_relation" not in file.page_commands
    assert isinstance(statement, SqlContent) and "sqlite_schema" in statement.text


async def test_broken_keys_are_reported(adapter: SqliteAdapter, home: Path) -> None:
    # Written behind SQLite's back: foreign keys are off for this connection.
    _script(home, "INSERT INTO items (name, label_id) VALUES ('stray', 77);")

    broken = await adapter.fetch(FetchRequest(node_id=f"{SECTION_ID}/broken_keys"))

    assert [(row[0], row[2]) for row in broken.rows] == [("items", "labels")]


# --- Export ------------------------------------------------------------------------


async def test_every_matching_row_is_exported_in_the_pages_order(adapter: SqliteAdapter) -> None:
    batches = [
        batch
        async for batch in adapter.export_rows(
            ExportRequest(
                node_id="main.items",
                columns=["name", "picture"],
                filters=[ScalarFilter(column="price", op="gte", value="2")],
                sort=[Sort(column="price", descending=True)],
            )
        )
    ]

    rows = [row for batch in batches for row in batch.rows]
    assert rows == [["under_score", None], ["100% pure", None], ["two", None]]


async def test_an_unknown_export_column_is_refused(adapter: SqliteAdapter) -> None:
    with pytest.raises(ValueError):
        async for _ in adapter.export_rows(ExportRequest(node_id="main.items", columns=["nothing"])):
            pass


# --- Search ----------------------------------------------------------------------


@pytest.fixture
def words(tmp_path: Path) -> SqliteAdapter:
    """A view per name of the word table, one of each name SQLite tells apart."""
    seen: set[str] = set()
    names: list[str] = []
    for name in sorted({name for _, name, _ in CASES} | {"aaa_xorders", "zzz_orders"}):
        if name.lower() not in seen:
            seen.add(name.lower())
            names.append(name)
    path = tmp_path / "words.db"
    connection = sqlite3.connect(path)
    for name in names:
        connection.execute(f'CREATE VIEW "{name}" AS SELECT 1 AS one')
    connection.execute("CREATE TABLE buyers (id INTEGER, customer_email TEXT)")
    connection.close()
    return SqliteAdapter(SqliteOptions(path="words.db"), tmp_path)


async def _find(adapter: SqliteAdapter, query: str, *, node_id: str | None = None, limit: int = 100) -> list[str]:
    found = await adapter.search_nodes(
        NodeSearchRequest(query=query, node_id=node_id, limit=limit), SearchBounds.within(10)
    )
    return [match.node.name for match in found.matches]


@pytest.mark.parametrize("typed", sorted({typed for typed, _, _ in CASES}))
async def test_names_are_found_and_ordered_by_the_word_table(words: SqliteAdapter, typed: str) -> None:
    names = await _find(words, typed)

    classes = [class_of_name(words_of(typed), name) for name in names]
    assert None not in classes
    ranks = [class_rank(one) for one in classes if one is not None]
    assert ranks == sorted(ranks)


async def test_a_word_survives_the_limit_ahead_of_names_that_merely_hold_it(words: SqliteAdapter) -> None:
    # Five names hold the word here: SQLite tells "Orders" and "orders" apart
    # by nothing, so the file has one of them.
    found = await words.search_nodes(NodeSearchRequest(query="orders", limit=4), SearchBounds.within(10))

    assert "aaa_xorders" not in [match.node.name for match in found.matches]
    assert found.complete is False


async def test_a_relation_is_found_by_its_column_and_says_which(words: SqliteAdapter) -> None:
    found = await words.search_columns(NodeSearchRequest(query="email"), SearchBounds.within(10))

    [match] = found.matches
    assert (match.node.name, match.excerpt, match.parent_id) == ("buyers", "customer_email", "main")


async def test_the_reports_are_found_by_their_titles(adapter: SqliteAdapter) -> None:
    found = await adapter.search_nodes(NodeSearchRequest(query="integ", node_id=SECTION_ID))

    assert [match.node.id for match in found.matches] == [f"{SECTION_ID}/integrity"]


async def test_names_are_enumerated_for_a_kept_list(adapter: SqliteAdapter) -> None:
    batches = [batch async for batch in adapter.enumerate_names(1000, SearchBounds.within(10))]

    names = [name.node.id for batch in batches for name in batch.names]
    assert names[0] == "main" and "main.items" in names


# --- Actions (D258) ------------------------------------------------------------------


async def test_what_each_node_offers(adapter: SqliteAdapter) -> None:
    on_main = [action.name for action in await adapter.available("main")]
    on_table = [action.name for action in await adapter.available("main.items")]
    on_system = [action.name for action in await adapter.available("main.sqlite_sequence")]

    assert on_main == ["load_csv", "create_table", "describe_model"]
    assert on_table == ["rename_relation", "drop_relation", "describe_model"]
    assert on_system == ["describe_model"]
    assert await adapter.available(f"{SECTION_ID}/file") == []


async def test_a_table_is_renamed_and_what_points_at_it_follows(adapter: SqliteAdapter) -> None:
    await _perform(adapter, "rename_relation", "main.labels", {"new_name": "tags"})

    assert "tags" in await _names(adapter)
    model = await adapter.relation_model("main.items")
    assert any(getattr(c, "target_node_id", None) == "main.tags" for c in model.constraints)


async def test_a_view_is_renamed_from_its_own_text(adapter: SqliteAdapter, home: Path) -> None:
    await _perform(adapter, "rename_relation", "main.cheap", {"new_name": "bargains"})

    assert {"bargains"} <= await _names(adapter)
    assert _run(home, "SELECT count(*) FROM bargains") == [(2,)]
    _script(home, "CREATE VIEW reader AS SELECT * FROM bargains;")
    with pytest.raises(ActionRefused) as refused:
        await _perform(adapter, "rename_relation", "main.bargains", {"new_name": "deals"})
    assert "reader" in refused.value.message


async def test_a_drop_is_rehearsed_and_says_what_it_would_do(adapter: SqliteAdapter) -> None:
    drop = adapter.action("drop_relation")
    assert isinstance(drop, Previews)

    items = await drop.preview("main.items", {})
    labels = await drop.preview("main.labels", {})

    assert items.blocked is False
    assert "Trigger items_named goes with it" in items.items
    assert any("cheap" in line for line in items.items)
    # pairs points at labels without a cascade and holds a row: SQLite refuses.
    assert labels.blocked is True
    assert labels.summary == "Other rows refer to this one"
    assert any("pairs" in line for line in labels.items)
    assert "labels" in await _names(adapter)


async def test_a_set_is_dropped_children_first(adapter: SqliteAdapter) -> None:
    drop = adapter.action("drop_relation")
    assert isinstance(drop, TakesNodeSet)

    await drop.perform_on_set(["main.labels", "main.pairs", "main.items", "main.cheap"], {})

    assert {"labels", "pairs", "items", "cheap"}.isdisjoint(await _names(adapter))


async def test_a_csv_file_becomes_a_table(adapter: SqliteAdapter) -> None:
    action = adapter.action("load_csv")
    assert isinstance(action, TakesFile)

    await action.perform_with_file("main", {}, Upload(b"code,label\nA1,first\nB2,second\n"))
    page = await adapter.fetch(FetchRequest(node_id="main.codes"))

    assert page.rows == [["A1", "first"], ["B2", "second"]]


async def test_the_model_is_written_out(adapter: SqliteAdapter) -> None:
    action = adapter.action("describe_model")
    assert isinstance(action, ProducesDownload)

    download = await action.download(["main"], {"dialect": "dbml"})

    assert isinstance(download, ActionDownload)
    text = b"".join([chunk async for chunk in download.body]).decode()
    assert "main.items" in text and "main.cheap" in text
    assert "sqlite_sequence" not in text


async def test_a_found_table_is_the_node_its_listing_gives(adapter: SqliteAdapter) -> None:
    found = await adapter.search_nodes(NodeSearchRequest(query="labels"), SearchBounds.within(10))
    listed = [node for node in await adapter.list_children("main") if node.name == "labels"]

    assert isinstance(found.matches[0].node, TableNode)
    assert found.matches[0].node == listed[0]
