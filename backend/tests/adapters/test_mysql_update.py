"""Changing rows of a MySQL table, and following its keys (D234, D110).

On MySQL and MariaDB. Every test makes the rows it changes, so their order
does not matter.
"""

import uuid
from collections.abc import AsyncIterator

import pytest

from app.adapters.fetch import FetchRequest, FetchResult, ScalarFilter
from app.adapters.mysql import ids
from app.adapters.mysql.adapter import MysqlAdapter
from app.adapters.references import (
    FollowReferenceRequest,
    ReferencedRows,
    ReferenceValue,
)
from app.adapters.resources import Pooling, ResourceStore
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
from tests.adapters.mysql_fixture import TARGETS, Target, run

DATABASE = "dp_rows"
PARENTS = ids.relation_id(DATABASE, "parents")
THINGS = ids.relation_id(DATABASE, "things")
PAIRS = ids.relation_id(DATABASE, "pairs")
HEAP = ids.relation_id(DATABASE, "heap")

_SCHEMA = [
    f"DROP DATABASE IF EXISTS {DATABASE}",
    f"CREATE DATABASE {DATABASE}",
    f"CREATE TABLE {DATABASE}.parents (id INT PRIMARY KEY, name VARCHAR(20) NOT NULL)",
    f"""
    CREATE TABLE {DATABASE}.things (
        id INT AUTO_INCREMENT PRIMARY KEY,
        label VARCHAR(20) NOT NULL UNIQUE,
        amount DECIMAL(10,2),
        raw VARBINARY(4),
        place POINT,
        seen TIMESTAMP NULL,
        flags BIT(3),
        doubled INT AS (amount * 2) VIRTUAL,
        parent_id INT,
        CONSTRAINT things_parent FOREIGN KEY (parent_id) REFERENCES {DATABASE}.parents (id)
    )
    """,
    f"CREATE TABLE {DATABASE}.pairs (a INT NOT NULL, b VARCHAR(10), UNIQUE KEY pairs_a (a))",
    f"CREATE TABLE {DATABASE}.heap (a INT, b INT)",
    f"INSERT INTO {DATABASE}.parents VALUES (1, 'Ann'), (2, 'Bob')",
]


@pytest.fixture(params=TARGETS, ids=lambda target: target.flavour, scope="module")
async def target(request: pytest.FixtureRequest) -> AsyncIterator[Target]:
    chosen: Target = request.param
    chosen.server.require()
    await run(chosen, *_SCHEMA)
    yield chosen
    await run(chosen, f"DROP DATABASE IF EXISTS {DATABASE}")


def _label() -> str:
    return uuid.uuid4().hex[:10]


async def _row(adapter: MysqlAdapter, node_id: str, column: str, value: str) -> tuple[FetchResult, int]:
    page = await adapter.fetch(
        FetchRequest(node_id=node_id, filters=[ScalarFilter(column=column, op="eq", value=value)])
    )
    assert len(page.rows) == 1, page.rows
    return page, 0


def _value(page: FetchResult, row: int, column: str) -> str | None:
    names = [one.name for one in page.columns]
    return page.rows[row][names.index(column)]


async def _thing(adapter: MysqlAdapter, **values: str | None) -> tuple[str, str]:
    """A new row of `things`, as its label and handle."""
    label = values.pop("label", None) or _label()
    inserted = await adapter.insert_row(
        InsertRowRequest(
            node_id=THINGS,
            values=[InsertValue(column="label", value=label)]
            + [InsertValue(column=name, value=value) for name, value in values.items()],
        )
    )
    assert inserted.row_handle is not None
    return label, inserted.row_handle


# --- What a page offers --------------------------------------------------


async def test_a_table_with_a_key_offers_every_change(target: Target) -> None:
    adapter = target.adapter()
    await _thing(adapter)

    page = await adapter.fetch(FetchRequest(node_id=THINGS))
    columns = {column.name: column for column in page.columns}

    assert page.update_supported and page.insert_supported and page.delete_supported
    assert all(handle is not None for handle in page.row_handles)
    assert columns["label"].editable and columns["label"].insert_required
    assert columns["id"].insertable and not columns["id"].insert_required
    # A generated column is the server's to compute.
    assert not columns["doubled"].editable and not columns["doubled"].insertable
    assert [reference.name for reference in page.references] == ["things_parent"]


async def test_a_table_with_no_key_is_edited_by_its_whole_row(target: Target) -> None:
    page = await target.adapter().fetch(FetchRequest(node_id=HEAP))

    assert page.insert_supported
    assert page.update_supported and page.delete_supported


# --- A table with no key (D242) ------------------------------------------


async def _loose(target: Target, *rows: str, columns: str = "a INT, b VARCHAR(10)") -> str:
    """A table of its own with no key, holding these rows."""
    name = f"loose_{uuid.uuid4().hex[:8]}"
    await run(
        target,
        f"CREATE TABLE {DATABASE}.{name} ({columns})",
        *(f"INSERT INTO {DATABASE}.{name} VALUES {row}" for row in rows),
    )
    return ids.relation_id(DATABASE, name)


async def _page(adapter: MysqlAdapter, node_id: str) -> FetchResult:
    return await adapter.fetch(FetchRequest(node_id=node_id, limit=50))


async def test_a_cell_of_a_row_with_no_key_changes_and_no_other(target: Target) -> None:
    adapter = target.adapter()
    node_id = await _loose(target, "(1, 'x')", "(2, NULL)", "(3, 'A')", "(3, 'a')")
    page = await _page(adapter, node_id)
    row = page.rows.index(["3", "a"])
    handle = page.row_handles[row]
    assert handle is not None

    result = await adapter.update_cell(
        UpdateCellRequest(node_id=node_id, row_handle=handle, column="b", value="changed")
    )
    nulls = page.rows.index(["2", None])
    await adapter.update_cell(
        UpdateCellRequest(node_id=node_id, row_handle=page.row_handles[nulls] or "", column="b", value="set")
    )

    assert result.values == ["3", "changed"]
    after = sorted((await _page(adapter, node_id)).rows, key=str)
    assert after == sorted([["1", "x"], ["2", "set"], ["3", "A"], ["3", "changed"]], key=str)


async def test_rows_the_same_in_every_value_are_changed_and_deleted_one_by_one(
    target: Target,
) -> None:
    adapter = target.adapter()
    node_id = await _loose(target, "(1, 'x')", "(1, 'x')", "(1, 'x')")
    page = await _page(adapter, node_id)
    handles = [handle for handle in page.row_handles if handle is not None]

    assert len(set(handles)) == 3
    await adapter.update_cell(
        UpdateCellRequest(node_id=node_id, row_handle=handles[0], column="b", value="y")
    )
    deleted = await adapter.delete_rows(
        DeleteRowsRequest(node_id=node_id, row_handles=handles[1:])
    )

    assert deleted.deleted == 2
    assert (await _page(adapter, node_id)).rows == [["1", "y"]]


async def test_a_row_changed_by_somebody_else_is_not_written_over(target: Target) -> None:
    adapter = target.adapter()
    node_id = await _loose(target, "(1, 'x')")
    handle = (await _page(adapter, node_id)).row_handles[0]
    assert handle is not None
    _, name = ids.parse(node_id)
    await run(target, f"UPDATE {DATABASE}.{name} SET b = 'theirs'")

    with pytest.raises(RowConflict):
        await adapter.update_cell(
            UpdateCellRequest(node_id=node_id, row_handle=handle, column="b", value="mine")
        )


async def test_rows_alike_but_for_a_float_are_not_guessed_between(target: Target) -> None:
    adapter = target.adapter()
    node_id = await _loose(
        target, "(1, 0.5)", "(1, 0.25)", columns="a INT, f DOUBLE"
    )
    page = await _page(adapter, node_id)
    handle = page.row_handles[0]
    assert handle is not None

    with pytest.raises(ValueError, match="cannot be told apart"):
        await adapter.update_cell(
            UpdateCellRequest(node_id=node_id, row_handle=handle, column="a", value="2")
        )


async def test_the_server_s_own_tables_are_not_changed(target: Target) -> None:
    page = await target.adapter().fetch(
        FetchRequest(node_id=ids.relation_id("mysql", "db"), limit=1)
    )

    assert not page.update_supported and not page.insert_supported
    assert page.update_reason is not None and "mysql" in page.update_reason


# --- Changing ------------------------------------------------------------


async def test_a_cell_changes_and_its_handle_moves_on(target: Target) -> None:
    adapter = target.adapter()
    label, handle = await _thing(adapter, amount="1.00")

    changed = await adapter.update_cell(
        UpdateCellRequest(node_id=THINGS, row_handle=handle, column="amount", value="2.50")
    )
    page, _ = await _row(adapter, THINGS, "label", label)

    assert _value(page, 0, "amount") == "2.50"
    assert _value(page, 0, "doubled") == "5"
    assert changed.row_handle == page.row_handles[0]
    # The handle read before the change names a version that is gone.
    with pytest.raises(RowConflict):
        await adapter.update_cell(
            UpdateCellRequest(node_id=THINGS, row_handle=handle, column="amount", value="3")
        )


async def test_a_change_made_by_somebody_else_is_not_written_over(target: Target) -> None:
    adapter = target.adapter()
    label, handle = await _thing(adapter, amount="1.00")
    await run(target, f"UPDATE {DATABASE}.things SET amount = 9 WHERE label = '{label}'")

    with pytest.raises(RowConflict):
        await adapter.update_cell(
            UpdateCellRequest(node_id=THINGS, row_handle=handle, column="label", value=_label())
        )


async def test_values_come_back_as_they_were_shown(target: Target) -> None:
    adapter = target.adapter()
    label, handle = await _thing(adapter)

    changed = await adapter.update_cells(
        UpdateCellsRequest(
            node_id=THINGS,
            rows=[
                RowEdit(
                    row_handle=handle,
                    cells=[
                        CellEdit(column="raw", value="0x01FF"),
                        CellEdit(column="place", value="POINT(3 4)"),
                        CellEdit(column="seen", value="2024-05-06T10:00:00+03:00"),
                        CellEdit(column="flags", value="6"),
                    ],
                )
            ],
        )
    )
    page, _ = await _row(adapter, THINGS, "label", label)

    assert isinstance(changed, CellsUpdated)
    assert _value(page, 0, "raw") == "0x01FF"
    assert _value(page, 0, "place") == "POINT(3 4)"
    assert _value(page, 0, "seen") == "2024-05-06T07:00:00+00:00"
    assert _value(page, 0, "flags") == "6"


async def test_values_a_column_cannot_hold_are_named_and_nothing_lands(target: Target) -> None:
    adapter = target.adapter()
    first, one = await _thing(adapter, amount="1.00")
    second, two = await _thing(adapter, amount="1.00")

    answer = await adapter.update_cells(
        UpdateCellsRequest(
            node_id=THINGS,
            rows=[
                RowEdit(row_handle=one, cells=[CellEdit(column="amount", value="5")]),
                RowEdit(
                    row_handle=two,
                    cells=[
                        CellEdit(column="amount", value="lots"),
                        CellEdit(column="place", value="not a shape"),
                    ],
                ),
            ],
        )
    )
    page, _ = await _row(adapter, THINGS, "label", first)

    assert isinstance(answer, CellsRejected)
    assert {(cell.row, cell.column) for cell in answer.cells} == {(1, "amount"), (1, "place")}
    assert _value(page, 0, "amount") == "1.00"
    with pytest.raises(ValueError):
        await adapter.update_cell(
            UpdateCellRequest(node_id=THINGS, row_handle=one, column="amount", value="x")
        )


async def test_a_key_column_may_change_and_the_row_is_found_by_its_new_key(target: Target) -> None:
    adapter = target.adapter()
    old = 1000 + uuid.uuid4().int % 100000
    await run(target, f"INSERT INTO {DATABASE}.pairs VALUES ({old}, 'x')")
    page, _ = await _row(adapter, PAIRS, "a", str(old))
    handle = page.row_handles[0]
    assert handle is not None

    changed = await adapter.update_cell(
        UpdateCellRequest(node_id=PAIRS, row_handle=handle, column="a", value=str(old + 1))
    )

    assert changed.values == [str(old + 1), "x"]


async def test_a_refused_constraint_is_said_in_words(target: Target) -> None:
    adapter = target.adapter()
    taken, _ = await _thing(adapter)
    _, handle = await _thing(adapter)

    with pytest.raises(ValueError, match="unique"):
        await adapter.update_cell(
            UpdateCellRequest(node_id=THINGS, row_handle=handle, column="label", value=taken)
        )
    with pytest.raises(ValueError, match="does not exist"):
        await adapter.update_cell(
            UpdateCellRequest(node_id=THINGS, row_handle=handle, column="parent_id", value="99")
        )


async def test_the_session_mode_is_put_back_after_a_write(target: Target) -> None:
    store = ResourceStore(max_entries=2, max_idle_seconds=60)
    try:
        options = target.options()
        adapter = MysqlAdapter(options, Pooling(store=store, connector_id=uuid.uuid4()))
        await _thing(adapter)
        page = await adapter.fetch(FetchRequest(node_id=THINGS, limit=1))
        assert page.rows
        rows = await adapter._session.query("SELECT @@SESSION.sql_mode AS mode")  # noqa: SLF001  # the pooled session itself is the subject
        assert "STRICT_ALL_TABLES" not in str(rows[0]["mode"])
    finally:
        await store.aclose()


# --- Inserting and deleting ----------------------------------------------


async def test_an_inserted_row_is_read_back_with_what_the_server_made(target: Target) -> None:
    adapter = target.adapter()
    label = _label()

    inserted = await adapter.insert_row(
        InsertRowRequest(node_id=THINGS, values=[InsertValue(column="label", value=label)])
    )

    assert inserted.row_handle is not None
    assert inserted.values[0] is not None and inserted.values[0].isdigit()
    assert inserted.values[1] == label
    with pytest.raises(ValueError, match="label"):
        await adapter.insert_row(InsertRowRequest(node_id=THINGS, values=[]))


async def test_a_row_without_a_key_is_inserted_without_a_handle(target: Target) -> None:
    inserted = await target.adapter().insert_row(
        InsertRowRequest(node_id=HEAP, values=[InsertValue(column="a", value="7")])
    )

    assert inserted.row_handle is None
    assert inserted.values == ["7", None]


async def test_a_block_of_rows_lands_whole_or_names_what_it_cannot(target: Target) -> None:
    adapter = target.adapter()
    labels = [_label() for _ in range(3)]

    refused = await adapter.insert_rows(
        InsertRowsRequest(
            node_id=THINGS,
            columns=["label", "amount"],
            rows=[[labels[0], "1"], [labels[1], "many"], [labels[2], "3"]],
        )
    )
    landed = await adapter.insert_rows(
        InsertRowsRequest(
            node_id=THINGS,
            columns=["label", "amount", "place"],
            rows=[[label, "1", "POINT(1 1)"] for label in labels],
        )
    )

    assert isinstance(refused, ValuesRejected)
    assert [(cell.row, cell.column, cell.value) for cell in refused.cells] == [(1, "amount", "many")]
    assert isinstance(landed, RowsInserted) and landed.inserted == 3


async def test_rows_are_deleted_only_as_they_were_read(target: Target) -> None:
    adapter = target.adapter()
    first, one = await _thing(adapter)
    second, two = await _thing(adapter)
    await run(target, f"UPDATE {DATABASE}.things SET amount = 1 WHERE label = '{second}'")

    with pytest.raises(RowConflict):
        await adapter.delete_rows(DeleteRowsRequest(node_id=THINGS, row_handles=[one, two]))
    deleted = await adapter.delete_rows(DeleteRowsRequest(node_id=THINGS, row_handles=[one]))

    assert deleted.deleted == 1
    page = await adapter.fetch(
        FetchRequest(node_id=THINGS, filters=[ScalarFilter(column="label", op="eq", value=second)])
    )
    assert len(page.rows) == 1


async def test_a_row_others_refer_to_is_not_deleted(target: Target) -> None:
    adapter = target.adapter()
    await _thing(adapter, parent_id="2")
    page, _ = await _row(adapter, PARENTS, "id", "2")
    handle = page.row_handles[0]
    assert handle is not None

    with pytest.raises(ValueError, match="refer"):
        await adapter.delete_rows(DeleteRowsRequest(node_id=PARENTS, row_handles=[handle]))


# --- Following keys ------------------------------------------------------


async def test_a_key_is_followed_both_ways(target: Target) -> None:
    adapter = target.adapter()
    await _thing(adapter, parent_id="1")

    forward = await adapter.follow_reference(
        FollowReferenceRequest(
            node_id=THINGS,
            reference="things_parent",
            values=[ReferenceValue(column="parent_id", value="1")],
        )
    )
    arriving = await adapter.arriving_references(PARENTS)
    backward = await adapter.follow_reference(
        FollowReferenceRequest(
            node_id=PARENTS,
            reference=arriving[0].name,
            direction="incoming",
            values=[ReferenceValue(column="id", value="1")],
        )
    )
    empty = await adapter.follow_reference(
        FollowReferenceRequest(
            node_id=THINGS,
            reference="things_parent",
            values=[ReferenceValue(column="parent_id", value=None)],
        )
    )

    assert isinstance(forward, ReferencedRows)
    assert forward.node.id == PARENTS
    assert [(one.column, one.value) for one in forward.filters] == [("id", "1")]  # type: ignore[union-attr]  # scalar filters, built by the source
    assert [(one.columns, one.source_title) for one in arriving] == [(["id"], f"{DATABASE}.things")]
    assert isinstance(backward, ReferencedRows)
    assert backward.node.id == THINGS
    assert [(one.column, one.value) for one in backward.filters] == [("parent_id", "1")]  # type: ignore[union-attr]  # the same
    assert empty.kind == "none"
    with pytest.raises(ValueError):
        await adapter.follow_reference(
            FollowReferenceRequest(
                node_id=THINGS,
                reference="no_such_key",
                values=[ReferenceValue(column="parent_id", value="1")],
            )
        )

