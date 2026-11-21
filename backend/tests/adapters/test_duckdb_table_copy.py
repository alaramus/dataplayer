"""DuckDB tables copied with their structure, between files and inside one (D182, D400).

The fixture's `items` has a check, a default, a unique key, a link to `labels`,
an index and a comment; `kinds` holds a value of every kind DuckDB has. What
arrives must read back exactly as the original does.
"""

from pathlib import Path

import duckdb
import pytest

from app.adapters.duckdb.adapter import DuckdbAdapter
from app.adapters.duckdb.options import DuckdbOptions
from app.adapters.fetch import FetchRequest
from app.adapters.protocol import SupportsTableCopy
from app.adapters.table_copy import (
    CopyLoad,
    LinkDecision,
    TableCopyRequest,
    TableCopyTarget,
)
from tests.adapters.duckdb_fixture import FILE, build

COPIES = "data/copies.duckdb"
ITEMS = "main.items"
LABELS = "main.labels"
KINDS = "main.kinds"


@pytest.fixture
def home(tmp_path: Path) -> Path:
    build(tmp_path)
    return tmp_path


@pytest.fixture
def source(home: Path) -> DuckdbAdapter:
    return DuckdbAdapter(DuckdbOptions(path=FILE), home)


@pytest.fixture
def copies(home: Path) -> DuckdbAdapter:
    return DuckdbAdapter(DuckdbOptions(path=COPIES, create=True), home)


def _run(home: Path, file: str, statement: str) -> list[tuple[object, ...]]:
    connection = duckdb.connect(str(home / file))
    try:
        return list(connection.execute(statement).fetchall())
    finally:
        connection.close()


async def _request(
    source: DuckdbAdapter,
    names: dict[str, str],
    links: LinkDecision,
    *,
    place: str = "main",
    same: bool = False,
    rows: bool = True,
) -> TableCopyRequest:
    described = await source.describe_for_copy(list(names))
    return TableCopyRequest(
        dialect="duckdb",
        place_node_id=place,
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


async def _carry(source: DuckdbAdapter, destination: DuckdbAdapter, request: TableCopyRequest) -> dict[str, int]:
    counted: dict[str, int] = {}

    async def arrived(load: CopyLoad, count: int, _size: int) -> None:
        counted[load.name] = count

    async with source.reading_tables() as tables:
        await destination.carry_table_copy(request, lambda load: tables.rows(load.node_id, load.columns), arrived)
    return counted


async def _rows(adapter: DuckdbAdapter, node_id: str) -> list[list[str | None]]:
    return (await adapter.fetch(FetchRequest(node_id=node_id, limit=50))).rows


async def test_a_table_is_described_from_the_catalog(source: DuckdbAdapter) -> None:
    assert isinstance(source, SupportsTableCopy)

    [items] = await source.describe_for_copy([ITEMS])

    by_name = {column.name: column for column in items.columns}
    assert by_name["name"].not_null is True and by_name["price"].default == "0"
    assert by_name["name"].type_sql == "VARCHAR"
    assert sorted((constraint.kind, constraint.definition) for constraint in items.constraints) == [
        ("check", 'CHECK ((length("name") > 0))'),
        ("primary_key", 'PRIMARY KEY ("id")'),
        ("unique", 'UNIQUE ("name", "price")'),
    ]
    assert [(index.name, index.body) for index in items.indexes] == [("items_price", "(price)")]
    assert [(link.target_node_id, link.columns) for link in items.links] == [(LABELS, ["label_id"])]
    assert items.comment == "What the shop sells"
    [labels] = await source.describe_for_copy([LABELS])
    assert labels.referenced_by == [ITEMS]


async def test_what_cannot_be_copied_is_refused_with_a_reason(source: DuckdbAdapter, home: Path) -> None:
    _run(home, FILE, "CREATE TABLE odd_kind (u UNION(n INTEGER, s VARCHAR))")

    view, union = await source.describe_for_copy(["main.cheap", "main.odd_kind"])

    assert view.refusal == "only tables are copied with their structure"
    assert union.refusal is not None and union.refusal.startswith("u is a union")


async def test_tables_arrive_whole_in_another_file_parents_first(
    source: DuckdbAdapter, copies: DuckdbAdapter, home: Path
) -> None:
    # Asked for child first: the copy still makes labels before items.
    request = await _request(source, {ITEMS: "items", LABELS: "labels"}, "copy")
    plan = await copies.plan_table_copy(request)

    counted = await _carry(source, copies, request)

    assert plan.problems == [] and plan.warnings == []
    titles = [statement.title for statement in plan.statements]
    assert titles.index("Create table main.labels") < titles.index("Create table main.items")
    assert counted == {"labels": 2, "items": 4}
    assert await _rows(copies, ITEMS) == await _rows(source, ITEMS)
    model = await copies.relation_model(ITEMS)
    assert [getattr(c, "target_node_id", None) for c in model.constraints if c.kind == "foreign_key"] == [LABELS]
    assert [index.name for index in model.indexes if not index.primary] == ["items_price"]
    assert _run(home, COPIES, "SELECT comment FROM duckdb_tables() WHERE table_name = 'items'") == [
        ("What the shop sells",)
    ]


async def test_every_kind_of_value_survives_the_copy(source: DuckdbAdapter, copies: DuckdbAdapter) -> None:
    await _carry(source, copies, await _request(source, {KINDS: "kinds"}, "drop"))

    assert await _rows(copies, KINDS) == await _rows(source, KINDS)


async def test_an_identity_arrives_as_a_sequence_of_its_own(
    source: DuckdbAdapter, copies: DuckdbAdapter, home: Path
) -> None:
    _run(
        home,
        FILE,
        "CREATE SEQUENCE counter START 5; "
        "CREATE TABLE counted (id BIGINT DEFAULT nextval('counter') PRIMARY KEY, "
        "twice BIGINT GENERATED ALWAYS AS (id * 2) VIRTUAL, note VARCHAR); "
        "INSERT INTO counted (note) VALUES ('a'), ('b')",
    )

    [counted] = await source.describe_for_copy(["main.counted"])
    await _carry(source, copies, await _request(source, {"main.counted": "counted"}, "drop"))
    _run(home, COPIES, "INSERT INTO counted (note) VALUES ('c')")

    identity = counted.columns[0]
    assert (identity.identity, identity.identity_start, identity.identity_increment) == ("by_default", 7, 1)
    assert _run(home, COPIES, "SELECT id, twice, note FROM counted ORDER BY id") == [
        (5, 10, "a"), (6, 12, "b"), (7, 14, "c"),
    ]
    assert _run(home, COPIES, "SELECT sequence_name FROM duckdb_sequences()") == [("counted_id_seq",)]


async def test_a_copy_inside_one_file_is_named_free_and_may_keep_its_links(source: DuckdbAdapter) -> None:
    [name] = await source.free_table_names("main", ["items"])
    request = await _request(source, {ITEMS: name}, "original", same=True)

    plan = await source.plan_table_copy(request)
    await _carry(source, source, request)

    assert name == "items_copy"
    assert "items_copy_price" in [statement.title.split()[-1] for statement in plan.statements]
    assert await _rows(source, f"main.{name}") == await _rows(source, ITEMS)
    model = await source.relation_model(f"main.{name}")
    assert [getattr(c, "target_node_id", None) for c in model.constraints if c.kind == "foreign_key"] == [LABELS]


async def test_a_link_into_another_schema_is_left_out_with_a_warning(source: DuckdbAdapter) -> None:
    request = await _request(source, {ITEMS: "items"}, "original", place="sales\\.eu", same=True)

    plan = await source.plan_table_copy(request)

    assert plan.problems == []
    assert any("cannot point into another schema" in warning for warning in plan.warnings)


async def test_a_taken_name_is_a_conflict_and_nothing_is_made(source: DuckdbAdapter) -> None:
    request = await _request(source, {ITEMS: "items"}, "drop", same=True)

    plan = await source.plan_table_copy(request)

    assert [problem.kind for problem in plan.problems] == ["conflict"]
    with pytest.raises(ValueError, match="already there"):
        await _carry(source, source, request)


async def test_a_refused_row_leaves_nothing_behind(source: DuckdbAdapter, copies: DuckdbAdapter, home: Path) -> None:
    # A link copied without the table it points at: every item's label is missing.
    request = await _request(source, {ITEMS: "items"}, "drop")
    request.tables[0].table.constraints.append(
        request.tables[0].table.constraints[0].model_copy(update={"kind": "check", "definition": "CHECK (price < 2)"})
    )

    with pytest.raises(ValueError, match="Rows of main.items"):
        await _carry(source, copies, request)

    assert _run(home, COPIES, "SELECT count(*) FROM duckdb_tables()") == [(0,)]


async def test_structure_alone_is_copied_without_rows(source: DuckdbAdapter, copies: DuckdbAdapter) -> None:
    request = await _request(source, {LABELS: "labels"}, "drop", rows=False)

    plan = await copies.plan_table_copy(request)
    await _carry(source, copies, request)

    assert plan.loads == []
    assert await _rows(copies, LABELS) == []
