from collections.abc import AsyncGenerator

import pytest

from app.adapters.column_changes import (
    AddColumnRequest,
    ColumnDefaultRequest,
    DropColumnRequest,
    RenameColumnRequest,
)
from app.adapters.postgres.adapter import PostgresAdapter
from app.adapters.postgres.options import PostgresUserPassword
from tests.utils.database import working_postgres_options
from tests.utils.relation_fixture import make_schema, run


@pytest.fixture
async def schema() -> AsyncGenerator[str]:
    async for name in make_schema():
        yield name


def _adapter() -> PostgresAdapter:
    return PostgresAdapter(PostgresUserPassword(**working_postgres_options()))


async def test_table_describes_column_changes_and_source_owned_types(schema: str) -> None:
    model = await _adapter().relation_model(f"{schema}.customers")

    assert model.column_changes_supported is True
    assert model.column_changes_reason is None
    assert {option.code for option in model.column_type_options} >= {
        "text",
        "integer",
        "boolean",
        "timestamp_tz",
        "jsonb",
        "uuid",
    }


async def test_view_and_partition_child_explain_why_columns_cannot_change(
    schema: str,
) -> None:
    view = await _adapter().relation_model(f"{schema}.rich_customers")
    child = await _adapter().relation_model(f"{schema}.events_2026")

    assert view.column_changes_supported is False
    assert view.column_changes_reason == "Only tables can change columns"
    assert child.column_changes_supported is False
    assert child.column_changes_reason == "Change columns on the partitioned parent"
    assert view.column_type_options == []


async def test_adds_a_nullable_column_from_a_validated_type_code(schema: str) -> None:
    adapter = _adapter()

    await adapter.add_column(
        AddColumnRequest(
            node_id=f"{schema}.customers",
            name="review_note",
            type_code="text",
            nullable=True,
        )
    )

    model = await adapter.relation_model(f"{schema}.customers")
    added = next(column for column in model.columns if column.name == "review_note")
    assert added.type.sql == "text"
    assert added.nullable is True


async def test_adds_a_not_null_column_to_an_empty_table(schema: str) -> None:
    adapter = _adapter()

    await adapter.add_column(
        AddColumnRequest(
            node_id=f"{schema}.customers",
            name="approved",
            type_code="boolean",
            nullable=False,
        )
    )

    model = await adapter.relation_model(f"{schema}.customers")
    assert next(column for column in model.columns if column.name == "approved").nullable is False


async def test_rejects_unknown_type_duplicate_name_and_unsafe_relation(schema: str) -> None:
    adapter = _adapter()

    with pytest.raises(ValueError, match="Unknown column type"):
        await adapter.add_column(
            AddColumnRequest(
                node_id=f"{schema}.customers",
                name="payload_copy",
                type_code="text); DROP TABLE customers; --",
            )
        )
    with pytest.raises(ValueError, match="already has"):
        await adapter.add_column(
            AddColumnRequest(
                node_id=f"{schema}.customers", name="name", type_code="text"
            )
        )
    with pytest.raises(ValueError, match="Only tables"):
        await adapter.add_column(
            AddColumnRequest(
                node_id=f"{schema}.rich_customers", name="note", type_code="text"
            )
        )


async def test_identifier_is_composed_and_never_executed_as_sql(schema: str) -> None:
    adapter = _adapter()
    name = 'note"; DROP TABLE regions; --'

    await adapter.add_column(
        AddColumnRequest(
            node_id=f"{schema}.customers", name=name, type_code="text"
        )
    )

    model = await adapter.relation_model(f"{schema}.customers")
    assert name in {column.name for column in model.columns}
    assert (await adapter.relation_model(f"{schema}.regions")).name == "regions"


async def test_drops_one_existing_column(schema: str) -> None:
    adapter = _adapter()
    await adapter.add_column(
        AddColumnRequest(
            node_id=f"{schema}.customers", name="temporary_note", type_code="text"
        )
    )

    await adapter.drop_column(
        DropColumnRequest(node_id=f"{schema}.customers", name="temporary_note")
    )

    model = await adapter.relation_model(f"{schema}.customers")
    assert "temporary_note" not in {column.name for column in model.columns}


async def test_drop_rejects_an_unknown_column_and_partition_child(schema: str) -> None:
    adapter = _adapter()

    with pytest.raises(ValueError, match="no column"):
        await adapter.drop_column(
            DropColumnRequest(node_id=f"{schema}.customers", name="missing")
        )
    with pytest.raises(ValueError, match="partitioned parent"):
        await adapter.drop_column(
            DropColumnRequest(node_id=f"{schema}.events_2026", name="happened")
        )


async def test_drop_does_not_cascade_to_dependent_objects(schema: str) -> None:
    adapter = _adapter()

    with pytest.raises(ValueError, match="source rejected"):
        await adapter.drop_column(
            DropColumnRequest(node_id=f"{schema}.customers", name="name")
        )

    model = await adapter.relation_model(f"{schema}.customers")
    assert "name" in {column.name for column in model.columns}
    assert (await adapter.relation_model(f"{schema}.rich_customers")).name == "rich_customers"


async def test_not_null_addition_to_existing_rows_is_rejected_safely(schema: str) -> None:
    await run(
        f"INSERT INTO {schema}.regions VALUES (1, 'EU')"  # noqa: S608 -- fixture-owned schema.
    )

    with pytest.raises(ValueError, match="source rejected"):
        await _adapter().add_column(
            AddColumnRequest(
                node_id=f"{schema}.regions",
                name="required_note",
                type_code="text",
                nullable=False,
            )
        )


async def test_renames_a_column_and_keeps_dependent_metadata(schema: str) -> None:
    adapter = _adapter()

    result = await adapter.rename_column(
        RenameColumnRequest(
            node_id=f"{schema}.customers", name="region_id", new_name="area_id"
        )
    )

    model = await adapter.relation_model(f"{schema}.customers")
    assert result.name == "area_id"
    assert "area_id" in {column.name for column in model.columns}
    assert "region_id" not in {column.name for column in model.columns}
    assert any("area_id" in constraint.columns for constraint in model.constraints)


async def test_rename_rejects_unknown_duplicate_and_unsafe_names(schema: str) -> None:
    adapter = _adapter()

    with pytest.raises(ValueError, match="no column"):
        await adapter.rename_column(
            RenameColumnRequest(
                node_id=f"{schema}.customers", name="missing", new_name="present"
            )
        )
    with pytest.raises(ValueError, match="already has"):
        await adapter.rename_column(
            RenameColumnRequest(
                node_id=f"{schema}.customers", name="name", new_name="id"
            )
        )

    quoted = 'area"; DROP TABLE regions; --'
    await adapter.rename_column(
        RenameColumnRequest(
            node_id=f"{schema}.customers", name="region_id", new_name=quoted
        )
    )
    assert quoted in {
        column.name
        for column in (await adapter.relation_model(f"{schema}.customers")).columns
    }
    assert (await adapter.relation_model(f"{schema}.regions")).name == "regions"


async def test_sets_literal_default_and_drops_it(schema: str) -> None:
    adapter = _adapter()
    dangerous_text = "Robert'); DROP TABLE regions; --"

    await adapter.change_column_default(
        ColumnDefaultRequest(
            node_id=f"{schema}.customers",
            name="name",
            action="set",
            value=dangerous_text,
        )
    )

    model = await adapter.relation_model(f"{schema}.customers")
    stored_default = next(c for c in model.columns if c.name == "name").default
    assert stored_default is not None
    assert dangerous_text.replace("'", "''") in stored_default
    assert (await adapter.relation_model(f"{schema}.regions")).name == "regions"

    await adapter.change_column_default(
        ColumnDefaultRequest(
            node_id=f"{schema}.customers", name="name", action="drop"
        )
    )
    model = await adapter.relation_model(f"{schema}.customers")
    assert next(c for c in model.columns if c.name == "name").default is None


async def test_default_rejects_invalid_literal_unknown_and_generated_column(
    schema: str,
) -> None:
    adapter = _adapter()

    with pytest.raises(ValueError, match="source rejected"):
        await adapter.change_column_default(
            ColumnDefaultRequest(
                node_id=f"{schema}.customers",
                name="region_id",
                action="set",
                value="not an integer",
            )
        )
    with pytest.raises(ValueError, match="no column"):
        await adapter.change_column_default(
            ColumnDefaultRequest(
                node_id=f"{schema}.customers", name="missing", action="drop"
            )
        )
    with pytest.raises(ValueError, match="generated column"):
        await adapter.change_column_default(
            ColumnDefaultRequest(
                node_id=f"{schema}.customers", name="name_upper", action="drop"
            )
        )
