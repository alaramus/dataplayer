"""SQLite tables copied with their structure, between files and inside one (D182, D259).

The fixture's `items` has AUTOINCREMENT, a collation, a generated column, an
inline link, named and unnamed checks, a partial index and a trigger: what
arrives must read back exactly as the original does.
"""

import sqlite3
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from app.adapters.fetch import FetchRequest
from app.adapters.protocol import SupportsTableCopy
from app.adapters.sqlite.adapter import SqliteAdapter
from app.adapters.sqlite.options import SqliteOptions
from app.adapters.table_copy import (
    CopyLoad,
    LinkDecision,
    TableCopyRequest,
    TableCopyTarget,
)
from tests.adapters.sqlite_fixture import FILE, build

COPIES = "data/copies.db"
ITEMS = "main.items"
LABELS = "main.labels"


@pytest.fixture
def home(tmp_path: Path) -> Path:
    build(tmp_path)
    return tmp_path


@pytest.fixture
def source(home: Path) -> SqliteAdapter:
    return SqliteAdapter(SqliteOptions(path=FILE), home)


@pytest.fixture
def copies(home: Path) -> SqliteAdapter:
    return SqliteAdapter(SqliteOptions(path=COPIES, create=True), home)


def _run(home: Path, file: str, statement: str) -> list[tuple[object, ...]]:
    connection = sqlite3.connect(home / file)
    try:
        rows = list(connection.execute(statement).fetchall())
        connection.commit()
        return rows
    finally:
        connection.close()


async def _request(
    source: SqliteAdapter,
    names: dict[str, str],
    links: LinkDecision,
    *,
    same: bool = False,
    rows: bool = True,
) -> TableCopyRequest:
    described = await source.describe_for_copy(list(names))
    return TableCopyRequest(
        dialect="sqlite",
        place_node_id="main",
        same_database=same,
        rows=rows,
        tables=[
            TableCopyTarget(
                table=table,
                name=names[table.node_id],
                links={link.name: links for link in table.links},
            )
            for table in described
        ],
    )


async def _carry(
    source: SqliteAdapter, destination: SqliteAdapter, request: TableCopyRequest
) -> dict[str, int]:
    counted: dict[str, int] = {}

    async def arrived(load: CopyLoad, count: int, _size: int) -> None:
        counted[load.name] = count

    async with source.reading_tables() as tables:
        await destination.carry_table_copy(
            request, lambda load: tables.rows(load.node_id, load.columns), arrived
        )
    return counted


async def _rows(adapter: SqliteAdapter, node_id: str) -> list[list[str | None]]:
    page = await adapter.fetch(FetchRequest(node_id=node_id, limit=50))
    return page.rows


async def test_a_table_is_described_in_the_words_of_its_own_text(
    source: SqliteAdapter,
) -> None:
    assert isinstance(source, SupportsTableCopy)

    items, pairs = await source.describe_for_copy([ITEMS, "main.pairs"])

    by_name = {column.name: column for column in items.columns}
    assert by_name["id"].identity == "by_default"
    assert by_name["id"].definition == "INTEGER PRIMARY KEY AUTOINCREMENT"
    assert (
        by_name["name"].definition
        == "TEXT NOT NULL COLLATE NOCASE CHECK (length(name) > 0)"
    )
    assert by_name["doubled"].generated is not None
    # The inline link travels as a link, not inside the column.
    assert by_name["label_id"].definition == "INT"
    assert by_name["loose"].definition == ""
    assert [(constraint.kind, constraint.name) for constraint in items.constraints] == [
        ("check", "positive"),
        ("unique", 'UNIQUE ("name", "price")'),
    ]
    assert [index.name for index in items.indexes] == ["items_expensive"]
    assert items.indexes[0].body == "(price DESC) WHERE price > 5"
    assert [
        (link.name, link.target_node_id, link.on_delete) for link in items.links
    ] == [("to_label", LABELS, "cascade")]
    assert items.left_behind == ["1 trigger"]
    assert items.options is None
    assert pairs.options == "WITHOUT ROWID"


async def test_what_is_not_a_table_is_refused_with_a_reason(
    source: SqliteAdapter,
) -> None:
    view, virtual, system = await source.describe_for_copy(
        ["main.cheap", "main.notes", "main.sqlite_sequence"]
    )

    assert view.refusal == "only tables are copied with their structure"
    assert virtual.refusal == "only tables are copied with their structure"
    assert system.refusal == '"sqlite_sequence" belongs to SQLite'


async def test_tables_arrive_in_another_file_exactly_as_they_were(
    source: SqliteAdapter, copies: SqliteAdapter, home: Path
) -> None:
    request = await _request(
        source,
        {
            LABELS: "labels",
            ITEMS: "items",
            "main.pairs": "pairs",
            "main.events": "events",
        },
        "copy",
    )

    plan = await copies.plan_table_copy(request)
    counted = await _carry(source, copies, request)

    assert plan.problems == []
    assert [statement.stage for statement in plan.statements] == [
        "before",
        "before",
        "after",
        "before",
        "before",
    ]
    created = plan.statements[1].sql
    assert (
        'CONSTRAINT "to_label" FOREIGN KEY ("label_id") REFERENCES "labels" ("id")'
        in created
    )
    assert "ON DELETE CASCADE" in created
    assert plan.statements[3].sql.endswith(") WITHOUT ROWID")
    assert counted == {"labels": 2, "items": 4, "pairs": 2, "events": 6}
    assert await _rows(copies, ITEMS) == await _rows(source, ITEMS)
    assert await _rows(copies, "main.pairs") == await _rows(source, "main.pairs")
    assert await _rows(copies, "main.events") == await _rows(source, "main.events")
    # Each value arrives in the class it was stored in: a blob as a blob, and
    # text in no encoding as text.
    assert _run(home, COPIES, "SELECT typeof(kind), hex(kind) FROM events") == (
        _run(home, FILE, "SELECT typeof(kind), hex(kind) FROM events")
    )
    assert _run(
        home, COPIES, "SELECT typeof(picture), typeof(loose) FROM items ORDER BY id"
    ) == (
        _run(home, FILE, "SELECT typeof(picture), typeof(loose) FROM items ORDER BY id")
    )
    model = await copies.relation_model(ITEMS)
    assert {constraint.kind for constraint in model.constraints} >= {
        "primary_key",
        "unique",
        "check",
        "foreign_key",
    }
    assert _run(
        home,
        COPIES,
        "SELECT name FROM sqlite_schema WHERE type = 'index' AND sql IS NOT NULL",
    ) == [("items_expensive",)]
    # AUTOINCREMENT numbers on from what the rows hold.
    assert _run(
        home, COPIES, "SELECT seq FROM sqlite_sequence WHERE name = 'items'"
    ) == [(4,)]


async def test_a_copy_in_the_same_file_keeps_its_link_and_its_names_free(
    source: SqliteAdapter,
) -> None:
    names = await source.free_table_names("main", ["items", "Items_copy_x"])
    request = await _request(source, {ITEMS: names[0]}, "original", same=True)

    plan = await source.plan_table_copy(request)
    await _carry(source, source, request)

    assert names == ["items_copy", "Items_copy_x"]
    assert plan.problems == []
    assert 'REFERENCES "labels"' in plan.statements[0].sql
    assert plan.statements[1].sql.startswith(
        'CREATE INDEX "main"."items_copy_expensive" ON "items_copy"'
    )
    assert await _rows(source, "main.items_copy") == await _rows(source, ITEMS)


async def test_structure_alone_makes_empty_tables(
    source: SqliteAdapter, copies: SqliteAdapter
) -> None:
    request = await _request(source, {LABELS: "labels"}, "drop", rows=False)

    counted = await _carry(source, copies, request)

    assert counted == {}
    assert await _rows(copies, LABELS) == []


async def test_a_taken_or_reserved_name_is_refused_before_anything_runs(
    source: SqliteAdapter,
) -> None:
    taken = await _request(source, {LABELS: "ITEMS"}, "drop")
    reserved = await _request(source, {LABELS: "sqlite_mine"}, "drop")

    taken_plan = await source.plan_table_copy(taken)
    reserved_plan = await source.plan_table_copy(reserved)

    assert [(problem.kind, problem.message) for problem in taken_plan.problems] == [
        ("conflict", "main.ITEMS is already there")
    ]
    assert (
        reserved_plan.problems[0].message
        == 'A name starting "sqlite_" is SQLite\'s own'
    )
    assert taken_plan.statements == []


async def test_a_link_left_broken_fails_the_commit_and_leaves_nothing(
    source: SqliteAdapter, copies: SqliteAdapter, home: Path
) -> None:
    request = await _request(source, {LABELS: "labels", ITEMS: "items"}, "copy")

    async def arrived(_load: CopyLoad, _count: int, _size: int) -> None:
        return None

    with pytest.raises(
        ValueError,
        match="^Checking the links: Some rows point at rows that were not copied$",
    ):
        async with source.reading_tables() as tables:

            async def without_labels(load: CopyLoad) -> AsyncIterator[bytes]:
                # The labels arrive empty, so the items point at nothing.
                if load.name != "labels":
                    async for chunk in tables.rows(load.node_id, load.columns):
                        yield chunk

            await copies.carry_table_copy(request, without_labels, arrived)

    assert _run(home, COPIES, "SELECT count(*) FROM sqlite_schema") == [(0,)]


async def test_a_copy_stopped_half_way_leaves_nothing(
    source: SqliteAdapter, copies: SqliteAdapter, home: Path
) -> None:
    request = await _request(source, {LABELS: "labels", ITEMS: "items"}, "copy")

    async def broken(_load: CopyLoad) -> AsyncIterator[bytes]:
        yield b'[["i", "1"], ["t", "red"]]\n'
        raise RuntimeError("the source went away")

    async def arrived(_load: CopyLoad, _count: int, _size: int) -> None:
        return None

    with pytest.raises(RuntimeError):
        await copies.carry_table_copy(request, broken, arrived)

    assert _run(home, COPIES, "SELECT count(*) FROM sqlite_schema") == [(0,)]
