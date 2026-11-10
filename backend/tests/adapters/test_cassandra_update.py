"""Changing a Cassandra table's rows, checked against what was read (D345)."""

from collections.abc import AsyncIterator

import pytest

from app.adapters.cassandra.adapter import CassandraAdapter
from app.adapters.fetch import FetchRequest, FetchResult, ScalarFilter
from app.adapters.protocol import SupportsUpdate
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
from tests.adapters.cassandra_fixture import (
    KEYSPACE,
    TARGETS,
    Target,
    build,
    run,
    tear_down,
)

ITEMS = f"{KEYSPACE}.items"
MANY = f"{KEYSPACE}.many"


@pytest.fixture(params=TARGETS, ids=lambda target: target.flavour, scope="module")
async def target(request: pytest.FixtureRequest) -> AsyncIterator[Target]:
    chosen: Target = request.param
    chosen.server.require()
    await build(chosen)
    yield chosen
    await tear_down(chosen)


async def _row(
    adapter: CassandraAdapter, node: str, column: str, value: str
) -> FetchResult:
    return await adapter.fetch(
        FetchRequest(
            node_id=node, filters=[ScalarFilter(column=column, op="eq", value=value)]
        )
    )


def _cells(page: FetchResult, index: int = 0) -> dict[str, str | None]:
    return dict(
        zip([column.name for column in page.columns], page.rows[index], strict=True)
    )


async def test_a_table_offers_edits_and_a_view_does_not(target: Target) -> None:
    adapter = target.adapter()
    assert isinstance(adapter, SupportsUpdate)

    table = await adapter.fetch(FetchRequest(node_id=ITEMS, limit=5))
    view = await adapter.fetch(FetchRequest(node_id=f"{KEYSPACE}.items_by_ok", limit=5))
    system = await adapter.fetch(FetchRequest(node_id="system.local", limit=5))

    assert table.update_supported and len(table.row_handles) == len(table.rows)
    editable = {column.name: column.editable for column in table.columns}
    assert not editable["shop"] and not editable["id"] and not editable["at"]
    assert editable["label"] and editable["tags"] and editable["span"]
    required = {column.name for column in table.columns if column.insert_required}
    assert required == {"shop", "id", "at"}
    assert not view.update_supported and view.update_reason
    assert not system.update_supported and system.row_handles == []


async def test_a_cell_is_changed_and_the_row_read_again(target: Target) -> None:
    adapter = target.adapter()
    page = await _row(adapter, MANY, "p", "10")

    changed = await adapter.update_cell(
        UpdateCellRequest(
            node_id=MANY,
            row_handle=page.row_handles[0] or "",
            column="word",
            value="ten",
        )
    )

    assert changed.values == ["10", "0", "ten"]
    assert changed.row_handle != page.row_handles[0]
    again = await _row(adapter, MANY, "p", "10")
    assert again.rows == [["10", "0", "ten"]]


async def test_a_row_changed_since_it_was_read_is_refused(target: Target) -> None:
    adapter = target.adapter()
    page = await _row(adapter, MANY, "p", "11")
    await adapter.update_cell(
        UpdateCellRequest(
            node_id=MANY, row_handle=page.row_handles[0] or "", column="v", value="7"
        )
    )

    with pytest.raises(RowConflict):
        await adapter.update_cell(
            UpdateCellRequest(
                node_id=MANY,
                row_handle=page.row_handles[0] or "",
                column="v",
                value="8",
            )
        )


async def test_a_value_the_column_cannot_hold_is_refused(target: Target) -> None:
    adapter = target.adapter()
    page = await _row(adapter, MANY, "p", "12")

    with pytest.raises(ValueError, match='Invalid value for column "v"'):
        await adapter.update_cell(
            UpdateCellRequest(
                node_id=MANY,
                row_handle=page.row_handles[0] or "",
                column="v",
                value="seven",
            )
        )
    with pytest.raises(ValueError):
        await adapter.update_cell(
            UpdateCellRequest(
                node_id=MANY,
                row_handle=page.row_handles[0] or "",
                column="p",
                value="13",
            )
        )


async def test_collections_and_a_user_type_are_written_as_json(target: Target) -> None:
    adapter = target.adapter()
    page = await _row(adapter, ITEMS, "id", "1")
    handle = page.row_handles[0] or ""

    result = await adapter.update_cells(
        UpdateCellsRequest(
            node_id=ITEMS,
            rows=[
                RowEdit(
                    row_handle=handle,
                    cells=[
                        CellEdit(column="tags", value='["z"]'),
                        CellEdit(column="uniq", value="[5, 4]"),
                        CellEdit(column="attrs", value='{"a": 2}'),
                        CellEdit(column="counts", value='[[7, "seven"]]'),
                        CellEdit(column="pair", value='[9, "nine"]'),
                        CellEdit(column="home", value='{"street": "High", "zip": 5}'),
                        CellEdit(column="amount", value="1.50"),
                        CellEdit(column="label", value=None),
                    ],
                )
            ],
        )
    )

    assert isinstance(result, CellsUpdated)
    cells = dict(
        zip(
            [column.name for column in page.columns], result.rows[0].values, strict=True
        )
    )
    assert cells["tags"] == '["z"]'
    assert cells["uniq"] == "[4,5]"
    assert cells["attrs"] == '{"a":2}'
    assert cells["counts"] == '[[7,"seven"]]'
    assert cells["pair"] == '[9,"nine"]'
    assert cells["home"] == '{"street":"High","zip":5}'
    assert cells["amount"] == "1.50"
    assert cells["label"] is None


async def test_a_paste_with_a_bad_value_changes_nothing(target: Target) -> None:
    adapter = target.adapter()
    first = await _row(adapter, MANY, "p", "20")
    second = await _row(adapter, MANY, "p", "21")

    result = await adapter.update_cells(
        UpdateCellsRequest(
            node_id=MANY,
            rows=[
                RowEdit(
                    row_handle=first.row_handles[0] or "",
                    cells=[CellEdit(column="v", value="1")],
                ),
                RowEdit(
                    row_handle=second.row_handles[0] or "",
                    cells=[CellEdit(column="v", value="x")],
                ),
            ],
        )
    )

    assert isinstance(result, CellsRejected)
    assert [(cell.row, cell.column) for cell in result.cells] == [(1, "v")]
    assert (await _row(adapter, MANY, "p", "20")).rows == first.rows


async def test_a_row_is_inserted_and_its_key_cannot_be_inserted_twice(
    target: Target,
) -> None:
    adapter = target.adapter()
    values = [
        InsertValue(column="p", value="9001"),
        InsertValue(column="v", value="3"),
        InsertValue(column="word", value="new"),
    ]

    inserted = await adapter.insert_row(InsertRowRequest(node_id=MANY, values=values))

    assert inserted.values == ["9001", "3", "new"]
    assert inserted.row_handle is not None
    with pytest.raises(ValueError, match="already there"):
        await adapter.insert_row(InsertRowRequest(node_id=MANY, values=values))


async def test_an_insert_needs_the_whole_key(target: Target) -> None:
    with pytest.raises(ValueError, match="primary key"):
        await target.adapter().insert_row(
            InsertRowRequest(
                node_id=ITEMS,
                values=[
                    InsertValue(column="shop", value="x"),
                    InsertValue(column="id", value="1"),
                ],
            )
        )


async def test_a_block_of_rows_is_inserted_or_refused_whole(target: Target) -> None:
    adapter = target.adapter()

    refused = await adapter.insert_rows(
        InsertRowsRequest(
            node_id=MANY, columns=["p", "v"], rows=[["8001", "1"], ["8002", "x"]]
        )
    )
    accepted = await adapter.insert_rows(
        InsertRowsRequest(
            node_id=MANY,
            columns=["p", "v", "word"],
            rows=[["8001", "1", "a"], ["8002", "2", "b"]],
        )
    )

    assert isinstance(refused, ValuesRejected)
    assert [(cell.row, cell.column, cell.value) for cell in refused.cells] == [
        (1, "v", "x")
    ]
    assert isinstance(accepted, RowsInserted) and accepted.inserted == 2
    assert (await _row(adapter, MANY, "p", "8002")).rows == [["8002", "2", "b"]]


async def test_rows_are_deleted_by_their_key(target: Target) -> None:
    adapter = target.adapter()
    await run(target, "INSERT INTO dp_test_cql.many (p, v) VALUES (7001, 1)")
    page = await _row(adapter, MANY, "p", "7001")

    deleted = await adapter.delete_rows(
        DeleteRowsRequest(node_id=MANY, row_handles=[page.row_handles[0] or ""])
    )

    assert deleted.deleted == 1
    assert (await _row(adapter, MANY, "p", "7001")).rows == []


async def test_a_handle_from_somewhere_else_is_refused(target: Target) -> None:
    with pytest.raises(ValueError):
        await target.adapter().delete_rows(
            DeleteRowsRequest(node_id=MANY, row_handles=["junk"])
        )


async def test_a_view_is_not_changed(target: Target) -> None:
    with pytest.raises(ValueError):
        await target.adapter().insert_row(
            InsertRowRequest(
                node_id=f"{KEYSPACE}.items_by_ok",
                values=[InsertValue(column="ok", value="true")],
            )
        )
