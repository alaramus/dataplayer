"""Rows of a SQLite table changed in the grid, and keys followed (D110, D254).

Every test writes its own file under a temporary home.
"""

import sqlite3
from pathlib import Path

import pytest

from app.adapters.fetch import FetchRequest, FetchResult, ScalarFilter
from app.adapters.protocol import (
    SupportsArrivingReferences,
    SupportsDelete,
    SupportsInsert,
    SupportsReferences,
    SupportsUpdate,
)
from app.adapters.references import (
    FollowReferenceRequest,
    NoReferencedRows,
    ReferencedRows,
    ReferenceValue,
)
from app.adapters.sqlite.adapter import SqliteAdapter
from app.adapters.sqlite.options import SqliteOptions
from app.adapters.update import (
    CellEdit,
    CellsRejected,
    CellsUpdated,
    DeleteRowsRequest,
    InsertRowRequest,
    InsertRowsRequest,
    InsertValue,
    RowConflict,
    RowEdit,
    RowsInserted,
    UpdateCellRequest,
    UpdateCellsRequest,
    ValuesRejected,
)
from tests.adapters.sqlite_fixture import FILE, build


@pytest.fixture
def home(tmp_path: Path) -> Path:
    build(tmp_path)
    return tmp_path


@pytest.fixture
def adapter(home: Path) -> SqliteAdapter:
    return SqliteAdapter(SqliteOptions(path=FILE), home)


def _run(home: Path, statement: str) -> None:
    """A change made by another program, behind the source's back."""
    connection = sqlite3.connect(home / FILE)
    try:
        connection.executescript(statement)
    finally:
        connection.close()


async def _page(adapter: SqliteAdapter, node_id: str, **request: object) -> FetchResult:
    return await adapter.fetch(FetchRequest(node_id=node_id, **request))  # type: ignore[arg-type]  # the request's own fields, by name


async def _handle(adapter: SqliteAdapter, node_id: str, position: int = 0) -> str:
    handle = (await _page(adapter, node_id)).row_handles[position]
    assert handle is not None
    return handle


def test_the_type_claims_editing_and_keys(adapter: SqliteAdapter) -> None:
    for capability in (
        SupportsUpdate,
        SupportsInsert,
        SupportsDelete,
        SupportsReferences,
        SupportsArrivingReferences,
    ):
        assert isinstance(adapter, capability)


# --- What may be changed -------------------------------------------------------


async def test_what_cannot_be_changed_says_why(adapter: SqliteAdapter) -> None:
    view = await _page(adapter, "main.cheap")
    virtual = await _page(adapter, "main.notes")
    system = await _page(adapter, "main.sqlite_sequence")
    items = await _page(adapter, "main.items")

    assert (view.update_supported, view.update_reason) == (False, "Only tables can be edited")
    assert virtual.update_supported is False and virtual.insert_supported is False
    assert system.update_reason == '"sqlite_sequence" belongs to SQLite'
    columns = {column.name: column for column in items.columns}
    # A generated column is computed, and the rowid's alias makes its own value.
    assert columns["doubled"].editable is False and columns["doubled"].insertable is False
    assert columns["id"].has_default and not columns["id"].insert_required
    assert columns["name"].insert_required


async def test_a_table_with_no_key_is_named_by_its_rowid(adapter: SqliteAdapter) -> None:
    page = await _page(adapter, "main.events")
    handle = page.row_handles[1]
    assert handle is not None

    result = await adapter.update_cell(
        UpdateCellRequest(node_id="main.events", row_handle=handle, column="kind", value="z")
    )

    assert result.values[0] == "z"
    after = await _page(adapter, "main.events")
    assert [row[0] for row in after.rows][:3] == ["b", "z", "c"]


# --- Changing cells ------------------------------------------------------------


async def test_a_cell_is_written_and_read_back(adapter: SqliteAdapter) -> None:
    handle = await _handle(adapter, "main.items")

    result = await adapter.update_cell(
        UpdateCellRequest(node_id="main.items", row_handle=handle, column="price", value="7.25")
    )

    assert result.values[2] == "7.25"
    # The generated column follows the change, as RETURNING reads it.
    assert result.values[3] == "14.5"
    assert result.row_handle != handle


async def test_values_go_back_as_what_they_were_shown_as(adapter: SqliteAdapter) -> None:
    handle = await _handle(adapter, "main.items", 1)

    result = await adapter.update_cells(
        UpdateCellsRequest(
            node_id="main.items",
            rows=[
                RowEdit(
                    row_handle=handle,
                    cells=[
                        CellEdit(column="picture", value="0xCAFE"),
                        CellEdit(column="active", value="true"),
                        CellEdit(column="loose", value="42"),
                    ],
                )
            ],
        )
    )

    assert isinstance(result, CellsUpdated)
    values = result.rows[0].values
    assert (values[5], values[7], values[6]) == ("0xCAFE", "true", "42")


async def test_a_row_changed_by_somebody_else_is_not_written_over(
    adapter: SqliteAdapter, home: Path
) -> None:
    handle = await _handle(adapter, "main.items")
    _run(home, "UPDATE items SET price = 99 WHERE id = 1")

    with pytest.raises(RowConflict):
        await adapter.update_cell(
            UpdateCellRequest(node_id="main.items", row_handle=handle, column="name", value="x")
        )


async def test_a_change_the_table_refuses_is_named(adapter: SqliteAdapter) -> None:
    handle = await _handle(adapter, "main.items")
    cases = [
        ("name", None, "A required value is missing"),
        ("price", "-1", "The value breaks a check of the table"),
        ("label_id", "99", "The value refers to a row that does not exist"),
        ("name", "two", "Another row already has that value where values must be unique"),
    ]
    for column, value, message in cases:
        if column == "name" and value == "two":
            # Unique over (name, price): the second row's price is 2.
            await adapter.update_cell(
                UpdateCellRequest(
                    node_id="main.items",
                    row_handle=await _handle(adapter, "main.items"),
                    column="price",
                    value="2",
                )
            )
            handle = await _handle(adapter, "main.items")
        with pytest.raises(ValueError) as refused:
            await adapter.update_cell(
                UpdateCellRequest(node_id="main.items", row_handle=handle, column=column, value=value)
            )
        assert str(refused.value) == message


async def test_a_strict_table_names_the_values_it_cannot_hold(
    adapter: SqliteAdapter, home: Path
) -> None:
    _run(home, "CREATE TABLE strict_t (id INTEGER PRIMARY KEY, n INTEGER, t TEXT) STRICT;"
         "INSERT INTO strict_t VALUES (1, 1, 'a'), (2, 2, 'b');")
    page = await _page(adapter, "main.strict_t")
    first, second = page.row_handles
    assert first is not None and second is not None

    rejected = await adapter.update_cells(
        UpdateCellsRequest(
            node_id="main.strict_t",
            rows=[
                RowEdit(row_handle=first, cells=[CellEdit(column="n", value="10")]),
                RowEdit(row_handle=second, cells=[CellEdit(column="n", value="ten")]),
            ],
        )
    )
    inserted = await adapter.insert_rows(
        InsertRowsRequest(node_id="main.strict_t", columns=["n"], rows=[["3"], ["three"]])
    )

    assert isinstance(rejected, CellsRejected)
    assert [(cell.row, cell.column) for cell in rejected.cells] == [(1, "n")]
    assert isinstance(inserted, ValuesRejected)
    assert [(cell.row, cell.value) for cell in inserted.cells] == [(1, "three")]
    # Nothing of either block landed.
    unchanged = await _page(adapter, "main.strict_t")
    assert [row[1] for row in unchanged.rows] == ["1", "2"]


# --- Adding and removing rows ---------------------------------------------------


async def test_a_row_is_inserted_and_read_back_with_what_sqlite_made(
    adapter: SqliteAdapter,
) -> None:
    result = await adapter.insert_row(
        InsertRowRequest(
            node_id="main.items", values=[InsertValue(column="name", value="five")]
        )
    )

    assert result.values[0] == "5"
    assert result.values[1] == "five"
    # The defaults the table declares.
    assert result.values[2] == "0" and result.values[7] == "true"
    assert result.row_handle is not None


async def test_rows_are_inserted_in_one_block(adapter: SqliteAdapter) -> None:
    result = await adapter.insert_rows(
        InsertRowsRequest(node_id="main.labels", columns=["name"], rows=[["blue"], ["black"]])
    )
    failed_block = InsertRowsRequest(
        node_id="main.labels", columns=["name"], rows=[["white"], ["red"]]
    )

    assert isinstance(result, RowsInserted) and result.inserted == 2
    with pytest.raises(ValueError):
        await adapter.insert_rows(failed_block)
    names = [row[1] for row in (await _page(adapter, "main.labels")).rows]
    assert names == ["red", "green", "blue", "black"]


async def test_rows_are_deleted_and_keys_hold(adapter: SqliteAdapter) -> None:
    labels = await _page(adapter, "main.labels")
    red = labels.row_handles[0]
    assert red is not None
    events = await _page(adapter, "main.events")
    picked = [handle for handle in events.row_handles[:2] if handle is not None]

    deleted = await adapter.delete_rows(
        DeleteRowsRequest(node_id="main.events", row_handles=picked)
    )
    # `pairs` points at red without a cascade, so red stays.
    with pytest.raises(ValueError) as refused:
        await adapter.delete_rows(DeleteRowsRequest(node_id="main.labels", row_handles=[red]))

    assert deleted.deleted == 2
    assert str(refused.value) == "Other rows refer to this one"
    assert len((await _page(adapter, "main.events")).rows) == 4


async def test_a_deleted_row_is_a_conflict(adapter: SqliteAdapter, home: Path) -> None:
    handle = await _handle(adapter, "main.events")
    _run(home, "DELETE FROM events WHERE rowid = 1")

    with pytest.raises(RowConflict):
        await adapter.delete_rows(DeleteRowsRequest(node_id="main.events", row_handles=[handle]))


async def test_a_handle_from_another_table_is_refused(adapter: SqliteAdapter) -> None:
    handle = await _handle(adapter, "main.pairs")

    with pytest.raises(ValueError):
        await adapter.update_cell(
            UpdateCellRequest(node_id="main.items", row_handle=handle, column="name", value="x")
        )


# --- Following keys (D110) -------------------------------------------------------


async def test_a_key_is_followed_to_the_row_it_names(adapter: SqliteAdapter) -> None:
    target = await adapter.follow_reference(
        FollowReferenceRequest(
            node_id="main.items",
            reference="to_label",
            values=[ReferenceValue(column="label_id", value="2")],
        )
    )
    empty = await adapter.follow_reference(
        FollowReferenceRequest(
            node_id="main.items",
            reference="to_label",
            values=[ReferenceValue(column="label_id", value=None)],
        )
    )

    assert isinstance(target, ReferencedRows)
    assert target.node.id == "main.labels"
    assert target.filters == [ScalarFilter(column="id", op="eq", value="2")]
    assert isinstance(empty, NoReferencedRows)


async def test_the_keys_that_point_here_are_found_and_followed(adapter: SqliteAdapter) -> None:
    arriving = await adapter.arriving_references("main.labels")
    names = {reference.name: reference for reference in arriving}

    assert set(names) == {"to_label@main.items", 'FOREIGN KEY ("left_id")@main.pairs'}
    assert names["to_label@main.items"].columns == ["id"]
    followed = await adapter.follow_reference(
        FollowReferenceRequest(
            node_id="main.labels",
            reference="to_label@main.items",
            direction="incoming",
            values=[ReferenceValue(column="id", value="1")],
        )
    )
    assert isinstance(followed, ReferencedRows)
    assert followed.node.id == "main.items"
    rows = await _page(adapter, "main.items", filters=followed.filters)
    assert [row[1] for row in rows.rows] == ["one"]


async def test_values_land_in_the_classes_they_were_shown_as(
    adapter: SqliteAdapter, home: Path
) -> None:
    handle = await _handle(adapter, "main.items", 1)
    await adapter.update_cells(
        UpdateCellsRequest(
            node_id="main.items",
            rows=[
                RowEdit(
                    row_handle=handle,
                    cells=[
                        CellEdit(column="picture", value="0xCAFE"),
                        CellEdit(column="loose", value="42"),
                    ],
                )
            ],
        )
    )

    connection = sqlite3.connect(home / FILE)
    try:
        stored = connection.execute(
            "SELECT typeof(picture), typeof(loose) FROM items WHERE id = 2"
        ).fetchone()
    finally:
        connection.close()
    assert stored == ("blob", "integer")
