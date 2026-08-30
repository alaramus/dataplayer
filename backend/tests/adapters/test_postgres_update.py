from collections.abc import AsyncGenerator

import pytest

from app.adapters.fetch import FetchRequest
from app.adapters.postgres.adapter import PostgresAdapter
from app.adapters.postgres.options import PostgresUserPassword
from app.adapters.update import (
    DeleteRowsRequest,
    InsertRowRequest,
    InsertValue,
    RowConflict,
    UpdateCellRequest,
)
from tests.utils.database import working_postgres_options
from tests.utils.relation_fixture import make_schema, run


@pytest.fixture
async def schema() -> AsyncGenerator[str]:
    async for name in make_schema():
        await run(
            f"INSERT INTO {name}.regions VALUES (1, 'EU')"  # noqa: S608 -- fixture-owned schema.
        )
        yield name


def _adapter() -> PostgresAdapter:
    return PostgresAdapter(PostgresUserPassword(**working_postgres_options()))


async def test_fetch_marks_primary_key_table_and_returns_row_handles(
    schema: str,
) -> None:
    await run(
        f"INSERT INTO {schema}.customers (region_id, region_code, name) "  # noqa: S608 -- fixture-owned schema.
        "VALUES (1, 'EU', 'Ada')"
    )

    result = await _adapter().fetch(
        FetchRequest(node_id=f"{schema}.customers", limit=10)
    )

    assert result.update_supported is True
    assert result.update_reason is None
    assert len(result.row_handles) == len(result.rows)
    assert all(handle for handle in result.row_handles)
    assert next(column for column in result.columns if column.name == "name").editable
    assert not next(
        column for column in result.columns if column.name == "name_upper"
    ).editable
    assert result.insert_supported is True
    assert result.delete_supported is True
    assert next(column for column in result.columns if column.name == "name").insert_required
    assert not next(column for column in result.columns if column.name == "id").insert_required
    assert next(column for column in result.columns if column.name == "id").has_default
    assert next(column for column in result.columns if column.name == "id").insertable
    assert next(column for column in result.columns if column.name == "balance").has_default
    assert not next(
        column for column in result.columns if column.name == "name_upper"
    ).insertable


async def test_a_relation_without_a_primary_key_is_edited_by_its_place(
    schema: str,
) -> None:
    """D42: a key is one way to name a row, not the only one."""
    await run(f"CREATE TABLE {schema}.notes (body text NOT NULL)")
    await run(
        f"INSERT INTO {schema}.notes VALUES ('one'), ('two')"  # noqa: S608 -- fixture-owned schema.
    )
    adapter = _adapter()

    result = await adapter.fetch(FetchRequest(node_id=f"{schema}.notes"))

    assert result.update_supported is True
    assert result.update_reason is None
    assert result.delete_supported is True
    assert result.delete_reason is None
    assert all(handle is not None for handle in result.row_handles)
    assert all(column.editable for column in result.columns)

    handle = result.row_handles[0]
    assert handle is not None
    changed = await adapter.update_cell(
        UpdateCellRequest(
            node_id=f"{schema}.notes", row_handle=handle, column="body", value="ONE"
        )
    )
    assert changed.values == ["ONE"]

    # The row moved when it was written, so the handle that came back is the
    # one that works and the one that was used is spent.
    with pytest.raises(RowConflict):
        await adapter.update_cell(
            UpdateCellRequest(
                node_id=f"{schema}.notes",
                row_handle=handle,
                column="body",
                value="again",
            )
        )
    await adapter.update_cell(
        UpdateCellRequest(
            node_id=f"{schema}.notes",
            row_handle=changed.row_handle,
            column="body",
            value="ONCE",
        )
    )

    deleted = await adapter.delete_rows(
        DeleteRowsRequest(
            node_id=f"{schema}.notes",
            row_handles=[
                handle
                for handle in (
                    await adapter.fetch(FetchRequest(node_id=f"{schema}.notes"))
                ).row_handles
                if handle is not None
            ],
        )
    )
    assert deleted.deleted == 2


async def test_updates_one_cell_and_returns_the_canonical_row(schema: str) -> None:
    await run(
        f"INSERT INTO {schema}.customers (region_id, region_code, name) "  # noqa: S608 -- fixture-owned schema.
        "VALUES (1, 'EU', 'Ada')"
    )
    adapter = _adapter()
    fetched = await adapter.fetch(FetchRequest(node_id=f"{schema}.customers"))
    handle = fetched.row_handles[0]
    assert handle is not None

    updated = await adapter.update_cell(
        UpdateCellRequest(
            node_id=f"{schema}.customers",
            row_handle=handle,
            column="name",
            value="Grace",
        )
    )

    name_at = [column.name for column in fetched.columns].index("name")
    generated_at = [column.name for column in fetched.columns].index("name_upper")
    assert updated.values[name_at] == "Grace"
    assert updated.values[generated_at] == "GRACE"
    assert updated.row_handle != handle


async def test_stale_row_handle_cannot_overwrite_a_newer_value(schema: str) -> None:
    await run(
        f"INSERT INTO {schema}.customers (region_id, region_code, name) "  # noqa: S608 -- fixture-owned schema.
        "VALUES (1, 'EU', 'Ada')"
    )
    adapter = _adapter()
    fetched = await adapter.fetch(FetchRequest(node_id=f"{schema}.customers"))
    handle = fetched.row_handles[0]
    assert handle is not None
    request = UpdateCellRequest(
        node_id=f"{schema}.customers",
        row_handle=handle,
        column="name",
        value="Grace",
    )
    await adapter.update_cell(request)

    with pytest.raises(RowConflict):
        await adapter.update_cell(request.model_copy(update={"value": "Linus"}))


async def test_unknown_or_generated_column_is_rejected_before_update(
    schema: str,
) -> None:
    await run(
        f"INSERT INTO {schema}.customers (region_id, region_code, name) "  # noqa: S608 -- fixture-owned schema.
        "VALUES (1, 'EU', 'Ada')"
    )
    adapter = _adapter()
    fetched = await adapter.fetch(FetchRequest(node_id=f"{schema}.customers"))
    handle = fetched.row_handles[0]
    assert handle is not None

    with pytest.raises(ValueError, match="no column"):
        await adapter.update_cell(
            UpdateCellRequest(
                node_id=f"{schema}.customers",
                row_handle=handle,
                column='name" = NULL; --',
                value="bad",
            )
        )
    with pytest.raises(ValueError, match="cannot be edited"):
        await adapter.update_cell(
            UpdateCellRequest(
                node_id=f"{schema}.customers",
                row_handle=handle,
                column="name_upper",
                value="BAD",
            )
        )


async def test_value_rejected_by_postgres_is_a_safe_validation_error(
    schema: str,
) -> None:
    """Named by the type since D41, and still without a word from the driver."""
    await run(
        f"INSERT INTO {schema}.customers (region_id, region_code, name) "  # noqa: S608 -- fixture-owned schema.
        "VALUES (1, 'EU', 'Ada')"
    )
    adapter = _adapter()
    fetched = await adapter.fetch(FetchRequest(node_id=f"{schema}.customers"))
    handle = fetched.row_handles[0]
    assert handle is not None

    with pytest.raises(ValueError) as raised:
        await adapter.update_cell(
            UpdateCellRequest(
                node_id=f"{schema}.customers",
                row_handle=handle,
                column="balance",
                value="not-a-number",
            )
        )
    assert "cannot be read as numeric" in str(raised.value)
    assert "not-a-number" not in str(raised.value)


async def test_a_view_still_says_it_cannot_be_edited(schema: str) -> None:
    result = await _adapter().fetch(FetchRequest(node_id=f"{schema}.rich_customers"))

    assert result.update_supported is False
    assert result.update_reason == "Only tables can be edited"
    assert result.row_handles == [None for _ in result.rows]


async def test_a_page_keeps_its_order_when_a_row_is_edited(schema: str) -> None:
    """The defect D42 was written for: MVCC writes a changed row somewhere else."""
    await run(
        f"INSERT INTO {schema}.customers (region_id, region_code, name) "  # noqa: S608 -- fixture-owned schema.
        "VALUES (1, 'EU', 'ann'), (1, 'EU', 'bob'), (1, 'EU', 'cai')"
    )
    adapter = _adapter()
    before = await adapter.fetch(FetchRequest(node_id=f"{schema}.customers"))
    keys = [row[0] for row in before.rows]
    handle = before.row_handles[0]
    assert handle is not None

    await adapter.update_cell(
        UpdateCellRequest(
            node_id=f"{schema}.customers",
            row_handle=handle,
            column="name",
            value="anna",
        )
    )

    after = await adapter.fetch(FetchRequest(node_id=f"{schema}.customers"))
    assert [row[0] for row in after.rows] == keys


async def test_two_pages_of_an_unsorted_read_do_not_overlap(schema: str) -> None:
    """Without an order, LIMIT/OFFSET promises nothing about what page two holds."""
    await run(
        f"INSERT INTO {schema}.customers (region_id, region_code, name) "  # noqa: S608 -- fixture-owned schema.
        "SELECT 1, 'EU', 'c' || g FROM generate_series(1, 20) AS g"
    )
    adapter = _adapter()

    first = await adapter.fetch(
        FetchRequest(node_id=f"{schema}.customers", limit=10, offset=0)
    )
    second = await adapter.fetch(
        FetchRequest(node_id=f"{schema}.customers", limit=10, offset=10)
    )

    seen = [row[0] for row in first.rows] + [row[0] for row in second.rows]
    assert len(seen) == 20
    assert len(set(seen)) == 20


async def test_inserts_a_row_with_defaults_and_returns_canonical_values(
    schema: str,
) -> None:
    adapter = _adapter()

    inserted = await adapter.insert_row(
        InsertRowRequest(
            node_id=f"{schema}.customers",
            values=[
                InsertValue(column="region_id", value="1"),
                InsertValue(column="region_code", value="EU"),
                InsertValue(column="name", value="Ada"),
            ],
        )
    )

    fetched = await adapter.fetch(FetchRequest(node_id=f"{schema}.customers"))
    names = [column.name for column in fetched.columns]
    assert inserted.values[names.index("id")] == "1"
    assert inserted.values[names.index("balance")] == "0.00"
    assert inserted.values[names.index("name_upper")] == "ADA"
    assert inserted.row_handle is not None


async def test_insert_distinguishes_omitted_default_from_explicit_null(
    schema: str,
) -> None:
    inserted = await _adapter().insert_row(
        InsertRowRequest(
            node_id=f"{schema}.customers",
            values=[
                InsertValue(column="region_id", value="1"),
                InsertValue(column="region_code", value="EU"),
                InsertValue(column="name", value="Ada"),
                InsertValue(column="tags", value=None),
            ],
        )
    )
    columns = (await _adapter().fetch(FetchRequest(node_id=f"{schema}.customers"))).columns
    names = [column.name for column in columns]

    assert inserted.values[names.index("tags")] is None
    assert inserted.values[names.index("balance")] == "0.00"


async def test_insert_rejects_missing_unknown_and_generated_columns(
    schema: str,
) -> None:
    adapter = _adapter()

    with pytest.raises(ValueError, match="Required columns.*name"):
        await adapter.insert_row(
            InsertRowRequest(
                node_id=f"{schema}.customers",
                values=[
                    InsertValue(column="region_id", value="1"),
                    InsertValue(column="region_code", value="EU"),
                ],
            )
        )
    with pytest.raises(ValueError, match="no column"):
        await adapter.insert_row(
            InsertRowRequest(
                node_id=f"{schema}.customers",
                values=[InsertValue(column='name) VALUES (NULL); --', value="bad")],
            )
        )
    with pytest.raises(ValueError, match="cannot be inserted"):
        await adapter.insert_row(
            InsertRowRequest(
                node_id=f"{schema}.customers",
                values=[InsertValue(column="name_upper", value="BAD")],
            )
        )


async def test_deletes_several_rows_by_their_versioned_handles(schema: str) -> None:
    await run(
        f"INSERT INTO {schema}.customers (region_id, region_code, name) "  # noqa: S608 -- fixture-owned schema.
        "VALUES (1, 'EU', 'Ada'), (1, 'EU', 'Grace')"
    )
    adapter = _adapter()
    fetched = await adapter.fetch(FetchRequest(node_id=f"{schema}.customers"))
    handles = [handle for handle in fetched.row_handles if handle is not None]

    deleted = await adapter.delete_rows(
        DeleteRowsRequest(node_id=f"{schema}.customers", row_handles=handles)
    )

    assert deleted.deleted == 2
    assert (await adapter.fetch(FetchRequest(node_id=f"{schema}.customers"))).rows == []


async def test_stale_handle_makes_bulk_delete_atomic(schema: str) -> None:
    await run(
        f"INSERT INTO {schema}.customers (region_id, region_code, name) "  # noqa: S608 -- fixture-owned schema.
        "VALUES (1, 'EU', 'Ada'), (1, 'EU', 'Grace')"
    )
    adapter = _adapter()
    fetched = await adapter.fetch(FetchRequest(node_id=f"{schema}.customers"))
    handles = [handle for handle in fetched.row_handles if handle is not None]
    await adapter.update_cell(
        UpdateCellRequest(
            node_id=f"{schema}.customers",
            row_handle=handles[0],
            column="name",
            value="Ada Lovelace",
        )
    )

    with pytest.raises(RowConflict):
        await adapter.delete_rows(
            DeleteRowsRequest(node_id=f"{schema}.customers", row_handles=handles)
        )

    assert len((await adapter.fetch(FetchRequest(node_id=f"{schema}.customers"))).rows) == 2
