from collections.abc import AsyncGenerator

import pytest

from app.adapters.fetch import FetchRequest
from app.adapters.postgres.adapter import PostgresAdapter
from app.adapters.postgres.options import PostgresUserPassword
from app.adapters.update import RowConflict, UpdateCellRequest
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


async def test_relation_without_primary_key_explains_why_it_is_read_only(
    schema: str,
) -> None:
    await run(f"CREATE TABLE {schema}.notes (body text NOT NULL)")

    result = await _adapter().fetch(FetchRequest(node_id=f"{schema}.notes"))

    assert result.update_supported is False
    assert result.update_reason == "A primary key is required to edit rows"
    assert result.row_handles == [None for _ in result.rows]
    assert not any(column.editable for column in result.columns)


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
    await run(
        f"INSERT INTO {schema}.customers (region_id, region_code, name) "  # noqa: S608 -- fixture-owned schema.
        "VALUES (1, 'EU', 'Ada')"
    )
    adapter = _adapter()
    fetched = await adapter.fetch(FetchRequest(node_id=f"{schema}.customers"))
    handle = fetched.row_handles[0]
    assert handle is not None

    with pytest.raises(ValueError, match="source rejected"):
        await adapter.update_cell(
            UpdateCellRequest(
                node_id=f"{schema}.customers",
                row_handle=handle,
                column="balance",
                value="not-a-number",
            )
        )
