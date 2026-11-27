"""Rows of a DuckDB table edited in the grid, and keys followed (D395).

Every test writes its own file under a temporary home.
"""

from pathlib import Path

import duckdb
import pytest

from app.adapters.duckdb.adapter import DuckdbAdapter
from app.adapters.duckdb.options import DuckdbOptions
from app.adapters.fetch import FetchRequest, FetchResult, ScalarFilter, Sort
from app.adapters.protocol import (
    SupportsArrivingReferences,
    SupportsDelete,
    SupportsInsert,
    SupportsReferences,
    SupportsSkippingInsert,
    SupportsUpdate,
)
from app.adapters.references import (
    FollowReferenceRequest,
    ReferencedRows,
    ReferenceValue,
)
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
from tests.adapters.duckdb_fixture import FILE, build


@pytest.fixture
def adapter(tmp_path: Path) -> DuckdbAdapter:
    build(tmp_path)
    return DuckdbAdapter(DuckdbOptions(path=FILE), tmp_path)


async def _page(adapter: DuckdbAdapter, node_id: str, **request: object) -> FetchResult:
    return await adapter.fetch(FetchRequest(node_id=node_id, **request))  # type: ignore[arg-type]  # the request's own fields, by name


def _cell(page: FetchResult, row: int, column: str) -> str | None:
    names = [one.name for one in page.columns]
    return page.rows[row][names.index(column)]


def test_it_claims_row_edits_and_references(adapter: DuckdbAdapter) -> None:
    for capability in (
        SupportsUpdate,
        SupportsInsert,
        SupportsSkippingInsert,
        SupportsDelete,
        SupportsReferences,
        SupportsArrivingReferences,
    ):
        assert isinstance(adapter, capability)


async def test_a_table_with_a_key_names_its_rows(adapter: DuckdbAdapter) -> None:
    page = await _page(adapter, "main.items")

    assert page.update_supported and page.insert_supported and page.delete_supported
    assert all(handle is not None for handle in page.row_handles)
    assert [reference.name for reference in page.references] == ["items_label_id_id_fkey"]


async def test_a_clone_is_told_a_sequence_s_value_is_duckdb_s(tmp_path: Path) -> None:
    """A `nextval` default gives a new row its own value (D458)."""
    path = build(tmp_path)
    connection = duckdb.connect(str(path))
    try:
        connection.execute(
            "CREATE SEQUENCE counted_id; "
            "CREATE TABLE counted (id BIGINT DEFAULT nextval('counted_id') PRIMARY KEY, n INT DEFAULT 1)"
        )
    finally:
        connection.close()
    page = await _page(DuckdbAdapter(DuckdbOptions(path=FILE), tmp_path), "main.counted")

    assert {column.name: column.assigned_on_insert for column in page.columns} == {"id": True, "n": False}


async def test_a_table_without_a_key_takes_rows_and_is_otherwise_read_only(
    adapter: DuckdbAdapter,
) -> None:
    page = await _page(adapter, "main.events")
    view = await _page(adapter, "main.cheap")

    assert (page.update_supported, page.delete_supported, page.insert_supported) == (
        False,
        False,
        True,
    )
    assert page.update_reason is not None and "primary key" in page.update_reason
    assert all(handle is None for handle in page.row_handles)
    assert (view.update_supported, view.insert_supported) == (False, False)
    with pytest.raises(ValueError, match="primary key"):
        await adapter.delete_rows(DeleteRowsRequest(node_id="main.events", row_handles=["x"]))


async def test_a_cell_is_written_and_the_row_comes_back_as_written(
    adapter: DuckdbAdapter,
) -> None:
    page = await _page(adapter, "main.items")
    handle = page.row_handles[0]
    assert handle is not None

    result = await adapter.update_cell(
        UpdateCellRequest(node_id="main.items", row_handle=handle, column="price", value="3.25")
    )

    assert result.values == ["1", "one", "3.25", "1"]
    assert result.row_handle != handle
    with pytest.raises(RowConflict):
        # The handle read before the change no longer matches the row.
        await adapter.update_cell(
            UpdateCellRequest(node_id="main.items", row_handle=handle, column="price", value="4")
        )


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("huge", "-170141183460469231731687303715884105727"),
        ("exact", "1.0000000001"),
        ("day", "1999-12-31"),
        ("moment", "2030-05-06 07:08:09+00"),
        ("span", "3 months 4 days 05:06:07"),
        ("ident", "00000000-0000-0000-0000-000000000001"),
        ("feeling", "sad"),
        ("active", "false"),
        ("picture", "0x0102FF"),
        ("doc", '{"x": 1}'),
    ],
)
async def test_a_value_goes_back_as_the_text_it_is_shown_as(
    adapter: DuckdbAdapter, column: str, value: str
) -> None:
    page = await _page(adapter, "main.kinds")
    handle = page.row_handles[0]
    assert handle is not None

    result = await adapter.update_cell(
        UpdateCellRequest(node_id="main.kinds", row_handle=handle, column=column, value=value)
    )
    again = await _page(adapter, "main.kinds")

    names = [one.name for one in page.columns]
    assert result.values[names.index(column)] == value
    assert _cell(again, 0, column) == value


async def test_a_nested_or_generated_column_is_not_written(adapter: DuckdbAdapter) -> None:
    page = await _page(adapter, "main.kinds")
    editable = {column.name: column.editable for column in page.columns}
    handle = page.row_handles[0]
    assert handle is not None

    assert (editable["tags"], editable["point"], editable["counts"]) == (False, False, False)
    assert editable["huge"] is True
    with pytest.raises(ValueError, match="cannot be edited"):
        await adapter.update_cell(
            UpdateCellRequest(node_id="main.kinds", row_handle=handle, column="tags", value="[]")
        )


async def test_a_value_duckdb_cannot_read_is_refused_by_its_type(adapter: DuckdbAdapter) -> None:
    page = await _page(adapter, "main.kinds")
    handle = page.row_handles[0]
    assert handle is not None

    with pytest.raises(ValueError, match="cannot be read as DATE"):
        await adapter.update_cell(
            UpdateCellRequest(node_id="main.kinds", row_handle=handle, column="day", value="soon")
        )


async def test_a_paste_lands_whole_or_names_the_cells_refused(adapter: DuckdbAdapter) -> None:
    page = await _page(adapter, "main.items", sort=[Sort(column="id")])
    first, second = page.row_handles[0], page.row_handles[1]
    assert first is not None and second is not None

    refused = await adapter.update_cells(
        UpdateCellsRequest(
            node_id="main.items",
            rows=[
                RowEdit(row_handle=first, cells=[CellEdit(column="price", value="7")]),
                RowEdit(row_handle=second, cells=[CellEdit(column="price", value="lots")]),
            ],
        )
    )
    unchanged = await _page(adapter, "main.items", sort=[Sort(column="id")])
    landed = await adapter.update_cells(
        UpdateCellsRequest(
            node_id="main.items",
            rows=[
                RowEdit(row_handle=first, cells=[CellEdit(column="price", value="7")]),
                RowEdit(row_handle=second, cells=[CellEdit(column="name", value="deux")]),
            ],
        )
    )

    assert isinstance(refused, CellsRejected)
    assert [(cell.row, cell.column) for cell in refused.cells] == [(1, "price")]
    assert _cell(unchanged, 0, "price") == "1.50"
    assert isinstance(landed, CellsUpdated)
    assert [row.values[:3] for row in landed.rows] == [["1", "one", "7.00"], ["2", "deux", "2.00"]]


@pytest.mark.parametrize(
    ("node_id", "column", "value", "message"),
    [
        ("main.items", "name", None, "A required value is missing"),
        (
            "main.labels",
            "name",
            "green",
            "DuckDB cannot change a key or unique column of a row other rows refer to",
        ),
        ("main.items", "name", "", "The value breaks a check of the table"),
        ("main.items", "label_id", "99", "The value refers to a row that does not exist"),
    ],
)
async def test_a_change_the_table_refuses_says_which_rule(
    adapter: DuckdbAdapter, node_id: str, column: str, value: str | None, message: str
) -> None:
    page = await _page(adapter, node_id, sort=[Sort(column="id")])
    handle = page.row_handles[0]
    assert handle is not None

    with pytest.raises(ValueError) as refused:
        await adapter.update_cell(
            UpdateCellRequest(node_id=node_id, row_handle=handle, column=column, value=value)
        )

    assert str(refused.value) == message


async def test_a_duplicate_is_refused_as_one(adapter: DuckdbAdapter) -> None:
    made = await adapter.insert_row(
        InsertRowRequest(
            node_id="main.labels",
            values=[InsertValue(column="id", value="3"), InsertValue(column="name", value="blue")],
        )
    )
    assert made.row_handle is not None

    with pytest.raises(ValueError) as refused:
        await adapter.update_cell(
            UpdateCellRequest(
                node_id="main.labels", row_handle=made.row_handle, column="name", value="red"
            )
        )

    assert str(refused.value) == "Another row already has that value where values must be unique"


async def test_a_row_is_inserted_with_its_defaults_and_named(adapter: DuckdbAdapter) -> None:
    result = await adapter.insert_row(
        InsertRowRequest(
            node_id="main.items",
            values=[
                InsertValue(column="id", value="5"),
                InsertValue(column="name", value="five"),
            ],
        )
    )

    assert result.values == ["5", "five", "0.00", None]
    assert result.row_handle is not None
    with pytest.raises(ValueError, match="Required columns"):
        await adapter.insert_row(
            InsertRowRequest(node_id="main.items", values=[InsertValue(column="id", value="6")])
        )


async def test_rows_are_inserted_in_a_block_and_skipped_where_a_key_holds_them(
    adapter: DuckdbAdapter,
) -> None:
    block = await adapter.insert_rows(
        InsertRowsRequest(node_id="main.events", columns=["kind", "step"], rows=[["d", "1"], ["e", "2"]])
    )
    skipped = await adapter.insert_rows_skipping(
        InsertRowsRequest(node_id="main.labels", columns=["id", "name"], rows=[["1", "red"], ["3", "blue"]])
    )
    refused = await adapter.insert_rows(
        InsertRowsRequest(node_id="main.events", columns=["kind", "step"], rows=[["f", "x"]])
    )

    assert isinstance(block, RowsInserted) and block.inserted == 2
    assert isinstance(skipped, RowsInserted) and skipped.inserted == 1
    assert isinstance(refused, ValuesRejected)
    assert [(cell.row, cell.column, cell.value) for cell in refused.cells] == [(0, "step", "x")]
    assert len((await _page(adapter, "main.events")).rows) == 6


async def test_rows_are_deleted_by_their_key_unless_others_refer_to_them(
    adapter: DuckdbAdapter,
) -> None:
    labels = await _page(adapter, "main.labels", sort=[Sort(column="id")])
    items = await _page(adapter, "main.items", sort=[Sort(column="id")])
    first = labels.row_handles[0]
    assert first is not None

    with pytest.raises(ValueError, match="Other rows refer to this one"):
        await adapter.delete_rows(DeleteRowsRequest(node_id="main.labels", row_handles=[first]))
    handles = [handle for handle in items.row_handles[2:] if handle is not None]
    deleted = await adapter.delete_rows(DeleteRowsRequest(node_id="main.items", row_handles=handles))

    assert deleted.deleted == 2
    assert [row[0] for row in (await _page(adapter, "main.items")).rows] == ["1", "2"]


async def test_a_key_is_followed_both_ways(adapter: DuckdbAdapter) -> None:
    out = await adapter.follow_reference(
        FollowReferenceRequest(
            node_id="main.items",
            reference="items_label_id_id_fkey",
            values=[ReferenceValue(column="label_id", value="2")],
        )
    )
    arriving = await adapter.arriving_references("main.labels")
    back = await adapter.follow_reference(
        FollowReferenceRequest(
            node_id="main.labels",
            reference=arriving[0].name,
            direction="incoming",
            values=[ReferenceValue(column="id", value="2")],
        )
    )

    assert isinstance(out, ReferencedRows)
    assert out.node.id == "main.labels"
    assert out.filters == [ScalarFilter(column="id", op="eq", value="2")]
    assert [one.source_title for one in arriving] == ["main.items"]
    assert isinstance(back, ReferencedRows)
    assert back.node.id == "main.items"
    assert back.filters == [ScalarFilter(column="label_id", op="eq", value="2")]
