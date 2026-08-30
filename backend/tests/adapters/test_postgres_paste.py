from collections.abc import AsyncGenerator

import pytest

from app.adapters.fetch import FetchRequest, FetchResult
from app.adapters.postgres.adapter import PostgresAdapter
from app.adapters.postgres.options import PostgresUserPassword
from app.adapters.update import (
    CellEdit,
    CellsRejected,
    CellsUpdated,
    RowConflict,
    RowEdit,
    UpdateCellRequest,
    UpdateCellsRequest,
)
from tests.utils.database import working_postgres_options
from tests.utils.relation_fixture import make_schema, run


@pytest.fixture
async def schema() -> AsyncGenerator[str]:
    async for name in make_schema():
        yield name


def _adapter() -> PostgresAdapter:
    return PostgresAdapter(PostgresUserPassword(**working_postgres_options()))


async def _three_customers(schema: str) -> None:
    await run(
        f"INSERT INTO {schema}.regions VALUES (1, 'EU')"  # noqa: S608 -- fixture-owned schema.
    )
    await run(
        f"INSERT INTO {schema}.customers (region_id, region_code, name, balance) "  # noqa: S608 -- fixture-owned schema.
        "VALUES (1, 'EU', 'ann', 1), (1, 'EU', 'bob', 2), (1, 'EU', 'cai', 3)"
    )


async def _page(adapter: PostgresAdapter, schema: str) -> tuple[list[str], list[str]]:
    """The handles of the page, and the names of its columns."""
    result = await _rows(adapter, schema)
    handles = [handle for handle in result.row_handles if handle is not None]
    return handles, [column.name for column in result.columns]


async def _rows(adapter: PostgresAdapter, schema: str) -> FetchResult:
    return await adapter.fetch(
        FetchRequest(node_id=f"{schema}.customers", limit=10, sorts=[("name", "asc")])
    )


async def test_changes_several_cells_across_several_rows_at_once(
    schema: str,
) -> None:
    adapter = _adapter()
    await _three_customers(schema)
    handles, columns = await _page(adapter, schema)

    result = await adapter.update_cells(
        UpdateCellsRequest(
            node_id=f"{schema}.customers",
            rows=[
                RowEdit(
                    row_handle=handles[0],
                    cells=[
                        CellEdit(column="name", value="anna"),
                        CellEdit(column="balance", value="10.50"),
                    ],
                ),
                RowEdit(
                    row_handle=handles[1],
                    cells=[CellEdit(column="name", value="bobby")],
                ),
            ],
        )
    )

    assert isinstance(result, CellsUpdated)
    assert len(result.rows) == 2
    name = columns.index("name")
    assert result.rows[0].values[name] == "anna"
    assert result.rows[1].values[name] == "bobby"
    # And the handles moved on, because the rows have new versions.
    assert result.rows[0].row_handle != handles[0]


async def test_a_value_the_type_cannot_read_names_its_cell_and_writes_nothing(
    schema: str,
) -> None:
    adapter = _adapter()
    await _three_customers(schema)
    handles, columns = await _page(adapter, schema)

    result = await adapter.update_cells(
        UpdateCellsRequest(
            node_id=f"{schema}.customers",
            rows=[
                RowEdit(
                    row_handle=handles[0],
                    cells=[CellEdit(column="name", value="anna")],
                ),
                RowEdit(
                    row_handle=handles[1],
                    cells=[
                        CellEdit(column="balance", value="not a number"),
                        CellEdit(column="token", value="not a uuid"),
                    ],
                ),
            ],
        )
    )

    assert isinstance(result, CellsRejected)
    assert {(cell.row, cell.column) for cell in result.cells} == {
        (1, "balance"),
        (1, "token"),
    }
    # The readable cell of the first row was not written either.
    page = await _rows(adapter, schema)
    assert "anna" not in {row[columns.index("name")] for row in page.rows}


async def test_a_row_that_moved_takes_the_whole_block_with_it(schema: str) -> None:
    adapter = _adapter()
    await _three_customers(schema)
    handles, columns = await _page(adapter, schema)
    await run(
        f"UPDATE {schema}.customers SET name = 'moved' WHERE name = 'bob'"  # noqa: S608 -- fixture-owned schema.
    )

    with pytest.raises(RowConflict):
        await adapter.update_cells(
            UpdateCellsRequest(
                node_id=f"{schema}.customers",
                rows=[
                    RowEdit(
                        row_handle=handles[0],
                        cells=[CellEdit(column="name", value="anna")],
                    ),
                    RowEdit(
                        row_handle=handles[1],
                        cells=[CellEdit(column="name", value="bobby")],
                    ),
                ],
            )
        )

    # The first row was rolled back with the second: nothing landed.
    page = await _rows(adapter, schema)
    names = {row[columns.index("name")] for row in page.rows}
    assert "anna" not in names
    assert "ann" in names


async def test_an_empty_value_is_written_as_nothing(schema: str) -> None:
    adapter = _adapter()
    await _three_customers(schema)
    handles, columns = await _page(adapter, schema)

    result = await adapter.update_cells(
        UpdateCellsRequest(
            node_id=f"{schema}.customers",
            rows=[
                RowEdit(
                    row_handle=handles[0], cells=[CellEdit(column="tags", value=None)]
                )
            ],
        )
    )

    assert isinstance(result, CellsUpdated)
    assert result.rows[0].values[columns.index("tags")] is None


async def test_rejects_unknown_and_uneditable_columns(schema: str) -> None:
    adapter = _adapter()
    await _three_customers(schema)
    handles, _ = await _page(adapter, schema)

    with pytest.raises(ValueError, match="no column"):
        await adapter.update_cells(
            UpdateCellsRequest(
                node_id=f"{schema}.customers",
                rows=[
                    RowEdit(
                        row_handle=handles[0],
                        cells=[CellEdit(column="missing", value="x")],
                    )
                ],
            )
        )
    with pytest.raises(ValueError, match="cannot be edited"):
        await adapter.update_cells(
            UpdateCellsRequest(
                node_id=f"{schema}.customers",
                rows=[
                    RowEdit(
                        row_handle=handles[0],
                        cells=[CellEdit(column="name_upper", value="X")],
                    )
                ],
            )
        )


async def test_one_cell_is_refused_as_precisely_as_two_thousand(
    schema: str,
) -> None:
    """The single-cell route shares the check, so it names the type too."""
    adapter = _adapter()
    await _three_customers(schema)
    handles, _ = await _page(adapter, schema)

    with pytest.raises(ValueError, match="cannot be read as numeric"):
        await adapter.update_cell(
            UpdateCellRequest(
                node_id=f"{schema}.customers",
                row_handle=handles[0],
                column="balance",
                value="not a number",
            )
        )
