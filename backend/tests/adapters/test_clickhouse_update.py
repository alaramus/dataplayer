"""Changing the rows of a ClickHouse table in the grid (D272)."""

from collections.abc import AsyncIterator

import pytest

from app.adapters.clickhouse.session import quoted_name
from app.adapters.database_ids import relation_id
from app.adapters.fetch import FetchRequest, FetchResult, ScalarFilter, Sort
from app.adapters.protocol import SupportsDelete, SupportsInsert, SupportsUpdate
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
from tests.adapters.clickhouse_fixture import DATABASE, adapter, build, run, tear_down
from tests.utils.services import CLICKHOUSE

DB = quoted_name(DATABASE)
ITEMS = relation_id(DATABASE, "items")
DUPES = relation_id(DATABASE, "dupes")
LIGHT = relation_id(DATABASE, "light")
FLOATY = relation_id(DATABASE, "floaty")
JOURNAL = relation_id(DATABASE, "journal")


@pytest.fixture(scope="module")
async def server() -> AsyncIterator[None]:
    CLICKHOUSE.require()
    await build()
    await run(
        # A table a lightweight UPDATE can change: it keeps `_block_number`.
        f"""
        CREATE TABLE {DB}.light (id UInt32, note String, at DateTime64(3))
        ENGINE = MergeTree ORDER BY id
        SETTINGS enable_block_number_column = 1, enable_block_offset_column = 1
        """,
        f"INSERT INTO {DB}.light VALUES (1, 'one', '2024-01-01 00:00:00'), (2, 'two', '2024-01-01 00:00:00')",
        f"CREATE TABLE {DB}.floaty (a UInt8, f Float64) ENGINE = MergeTree ORDER BY a",
        f"INSERT INTO {DB}.floaty VALUES (1, 0.1), (1, 0.2)",
    )
    yield
    await tear_down()


async def _page(node_id: str, **extra: object) -> FetchResult:
    return await adapter().fetch(FetchRequest(node_id=node_id, **extra))  # type: ignore[arg-type]  # a page's own options, named in each test


def _row(result: FetchResult, column: str, value: str) -> tuple[list[str | None], str]:
    names = [item.name for item in result.columns]
    for cells, handle in zip(result.rows, result.row_handles, strict=True):
        if cells[names.index(column)] == value:
            assert handle is not None
            return cells, handle
    raise AssertionError(f"no row with {column} = {value}")


def test_it_claims_row_changes() -> None:
    source = adapter()
    for capability in (SupportsUpdate, SupportsInsert, SupportsDelete):
        assert isinstance(source, capability)


@pytest.mark.usefixtures("server")
async def test_a_page_says_what_can_be_changed() -> None:
    page = await _page(ITEMS)
    columns = {column.name: column for column in page.columns}

    assert page.update_supported and page.insert_supported and page.delete_supported
    assert all(page.row_handles)
    # A key column decides where the row is kept; no UPDATE moves it.
    assert not columns["id"].editable and not columns["label"].editable
    # A map has no cast from text, and a computed column is not written.
    assert not columns["attrs"].editable
    assert not columns["doubled"].editable and not columns["doubled"].insertable
    assert columns["amount"].editable and columns["tags"].editable
    assert columns["amount"].has_default and not columns["amount"].insert_required


@pytest.mark.usefixtures("server")
async def test_a_cell_is_changed_by_a_mutation_and_read_back() -> None:
    source = adapter()
    _, handle = _row(await _page(ITEMS), "id", "2")

    changed = await source.update_cell(
        UpdateCellRequest(node_id=ITEMS, row_handle=handle, column="amount", value="1.5")
    )

    names = [column.name for column in (await _page(ITEMS)).columns]
    assert changed.values[names.index("amount")] == "1.5000000000"
    assert changed.row_handle != handle
    # The handle read before the change no longer names the row.
    with pytest.raises(RowConflict):
        await source.update_cell(
            UpdateCellRequest(node_id=ITEMS, row_handle=handle, column="amount", value="2")
        )


@pytest.mark.usefixtures("server")
async def test_values_go_back_as_they_were_shown() -> None:
    source = adapter()
    cells, handle = _row(await _page(ITEMS), "id", "3")
    names = [column.name for column in (await _page(ITEMS)).columns]

    result = await source.update_cells(
        UpdateCellsRequest(
            node_id=ITEMS,
            rows=[
                RowEdit(
                    row_handle=handle,
                    cells=[
                        CellEdit(column="tags", value='["x","it\'s \\\\ back"]'),
                        CellEdit(column="pair", value='{"a":7,"b":"q"}'),
                        CellEdit(column="made", value="2025-06-01T10:00:00Z"),
                        CellEdit(column="kind", value="it's big"),
                        CellEdit(column="ok", value="true"),
                        CellEdit(column="seen", value=None),
                    ],
                )
            ],
        )
    )

    assert isinstance(result, CellsUpdated)
    after = dict(zip(names, result.rows[0].values, strict=True))
    assert after["tags"] == '["x","it\'s \\\\ back"]'
    assert after["pair"] == '{"a":7,"b":"q"}'
    assert after["made"] == "2025-06-01T10:00:00Z"
    assert (after["kind"], after["ok"], after["seen"]) == ("it's big", "true", None)
    assert cells[names.index("label")] == after["label"]


@pytest.mark.usefixtures("server")
async def test_a_value_the_column_cannot_hold_is_named_and_nothing_changes() -> None:
    source = adapter()
    _, handle = _row(await _page(ITEMS), "id", "1")

    result = await source.update_cells(
        UpdateCellsRequest(
            node_id=ITEMS,
            rows=[
                RowEdit(
                    row_handle=handle,
                    cells=[
                        CellEdit(column="big", value="-1"),
                        CellEdit(column="amount", value="3"),
                        CellEdit(column="kind", value="huge"),
                        CellEdit(column="tags", value="[not json"),
                    ],
                )
            ],
        )
    )

    assert isinstance(result, CellsRejected)
    assert [cell.column for cell in result.cells] == ["big", "kind", "tags"]
    _, same = _row(await _page(ITEMS), "id", "1")
    assert same == handle


@pytest.mark.usefixtures("server")
async def test_a_lightweight_update_where_the_table_can_take_one() -> None:
    _, handle = _row(await _page(LIGHT), "id", "2")

    changed = await adapter().update_cell(
        UpdateCellRequest(node_id=LIGHT, row_handle=handle, column="note", value="tab\there")
    )

    assert changed.values == ["2", "tab\there", "2024-01-01T00:00:00.000Z"]


@pytest.mark.usefixtures("server")
async def test_rows_alike_in_every_value_change_together() -> None:
    source = adapter()
    page = await _page(DUPES, sort=[Sort(column="b")])
    handles = [handle for cells, handle in zip(page.rows, page.row_handles, strict=True) if cells == ["1", "b"]]
    assert len(handles) == 2 and handles[0] != handles[1]

    assert handles[0] is not None
    await source.update_cell(
        UpdateCellRequest(node_id=DUPES, row_handle=handles[0], column="b", value="c")
    )
    changed = await _page(DUPES, sort=[Sort(column="b")])
    assert [cells for cells in changed.rows if cells[0] == "1"] == [["1", "a"], ["1", "c"], ["1", "c"]]

    picked = [
        handle for cells, handle in zip(changed.rows, changed.row_handles, strict=True) if cells == ["1", "c"]
    ][:1]
    deleted = await source.delete_rows(DeleteRowsRequest(node_id=DUPES, row_handles=[h for h in picked if h]))

    # One picked, both gone: nothing tells them apart (D272).
    assert deleted.deleted == 2
    assert (await _page(DUPES)).rows == [["0", "z"], ["1", "a"]]


@pytest.mark.usefixtures("server")
async def test_rows_alike_but_for_a_float_are_not_guessed_between() -> None:
    _, handle = _row(await _page(FLOATY), "f", "0.1")

    with pytest.raises(ValueError, match="cannot be told apart"):
        await adapter().update_cell(
            UpdateCellRequest(node_id=FLOATY, row_handle=handle, column="f", value="0.3")
        )


@pytest.mark.usefixtures("server")
async def test_rows_are_inserted_with_their_values_read_by_the_server() -> None:
    source = adapter()

    one = await source.insert_row(
        InsertRowRequest(
            node_id=ITEMS,
            values=[
                InsertValue(column="id", value="40"),
                InsertValue(column="label", value="new"),
                InsertValue(column="tags", value='["p"]'),
                InsertValue(column="attrs", value='{"z":3}'),
                InsertValue(column="made", value="2025-01-01T00:00:00Z"),
                InsertValue(column="kind", value="small"),
                InsertValue(column="ok", value="true"),
                InsertValue(column="amount", value="2.25"),
            ],
        )
    )
    many = await source.insert_rows(
        InsertRowsRequest(node_id=ITEMS, columns=["id", "label"], rows=[["41", "a"], ["42", "b"]])
    )
    refused = await source.insert_rows(
        InsertRowsRequest(node_id=ITEMS, columns=["id", "label"], rows=[["43", "c"], ["x", "d"]])
    )

    assert one.row_handle is None
    assert isinstance(many, RowsInserted) and many.inserted == 2
    assert isinstance(refused, ValuesRejected)
    assert [(cell.row, cell.column, cell.value) for cell in refused.cells] == [(1, "id", "x")]
    page = await _page(ITEMS, filters=[ScalarFilter(column="id", op="gte", value="40")])
    names = [column.name for column in page.columns]
    first = dict(zip(names, page.rows[0], strict=True))
    assert [row[0] for row in page.rows] == ["40", "41", "42"]
    assert (first["tags"], first["attrs"], first["made"]) == ('["p"]', '{"z":3}', "2025-01-01T00:00:00Z")
    assert first["amount"] == "2.2500000000"
    # A column nobody filled takes its default.
    assert first["seen"] is None


@pytest.mark.usefixtures("server")
async def test_what_an_engine_cannot_change_is_said() -> None:
    journal = await _page(JOURNAL)
    view = await _page(relation_id(DATABASE, "item_labels"))
    system = await _page(relation_id("system", "one"))

    # A Log table keeps inserted rows and changes none.
    assert journal.insert_supported and not journal.update_supported
    assert journal.update_reason is not None and "Log" in journal.update_reason
    assert not view.insert_supported and not view.update_supported
    assert not system.insert_supported and system.update_reason
    await adapter().insert_row(
        InsertRowRequest(node_id=JOURNAL, values=[InsertValue(column="line", value="three")])
    )
    assert len((await _page(JOURNAL)).rows) == 3


@pytest.mark.usefixtures("server")
async def test_a_filter_value_arrives_as_it_was_typed() -> None:
    """The server reads a parameter as escaped text; a backslash is kept."""
    await run(f"INSERT INTO {DB}.journal VALUES ('back\\\\slash\there')")

    found = await _page(
        JOURNAL, filters=[ScalarFilter(column="line", op="eq", value="back\\slash\there")]
    )

    assert found.rows == [["back\\slash\there"]]
