from collections.abc import AsyncGenerator

import pytest

from app.adapters.column_changes import (
    AddColumnRequest,
    ColumnDefaultRequest,
    ColumnNullabilityRequest,
    ColumnTypeBlocked,
    ColumnTypeChanged,
    ColumnTypeRequest,
    DropColumnRequest,
    NullabilityBlocked,
    NullabilityChanged,
    RenameColumnRequest,
)
from app.adapters.postgres.adapter import PostgresAdapter
from app.adapters.postgres.counting import COUNT_CEILING
from app.adapters.postgres.options import PostgresUserPassword
from app.adapters.relation import RelationModel
from tests.utils.database import working_postgres_options
from tests.utils.relation_fixture import make_schema, run


@pytest.fixture
async def schema() -> AsyncGenerator[str]:
    async for name in make_schema():
        yield name


def _adapter() -> PostgresAdapter:
    return PostgresAdapter(PostgresUserPassword(**working_postgres_options()))


def _nullable(model: RelationModel, name: str) -> bool:
    return next(column for column in model.columns if column.name == name).nullable


async def _one_region(schema: str) -> None:
    await run(
        f"INSERT INTO {schema}.regions VALUES (1, 'EU')"  # noqa: S608 -- fixture-owned schema.
    )


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


async def test_default_rejects_a_nul_character_before_composing_a_literal(
    schema: str,
) -> None:
    """A NUL makes psycopg raise while quoting, which is not an upstream fault.

    Left to the driver it escapes every handler the route has and answers 500.
    """
    adapter = _adapter()

    with pytest.raises(ValueError, match="NUL character"):
        await adapter.change_column_default(
            ColumnDefaultRequest(
                node_id=f"{schema}.customers",
                name="name",
                action="set",
                value="Anon\x00ymous",
            )
        )


async def test_requires_a_value_when_nothing_stands_in_the_way(schema: str) -> None:
    adapter = _adapter()

    result = await adapter.change_column_nullability(
        ColumnNullabilityRequest(
            node_id=f"{schema}.customers", name="tags", nullable=False
        )
    )

    assert isinstance(result, NullabilityChanged)
    assert result.nullable is False
    assert _nullable(await adapter.relation_model(f"{schema}.customers"), "tags") is False


async def test_stops_requiring_a_value(schema: str) -> None:
    adapter = _adapter()

    result = await adapter.change_column_nullability(
        ColumnNullabilityRequest(
            node_id=f"{schema}.customers", name="name", nullable=True
        )
    )

    assert isinstance(result, NullabilityChanged)
    assert result.nullable is True
    assert _nullable(await adapter.relation_model(f"{schema}.customers"), "name") is True


async def test_rows_without_a_value_are_counted_rather_than_raised(schema: str) -> None:
    adapter = _adapter()
    await _one_region(schema)
    await run(
        f"INSERT INTO {schema}.customers (region_id, region_code, name) "  # noqa: S608 -- fixture-owned schema.
        "VALUES (1, 'EU', 'ann'), (1, 'EU', 'bob')"
    )

    result = await adapter.change_column_nullability(
        ColumnNullabilityRequest(
            node_id=f"{schema}.customers", name="tags", nullable=False
        )
    )

    assert isinstance(result, NullabilityBlocked)
    assert result.rows_without_value == 2
    assert result.exact is True
    # Nothing was altered: the answer is about the rows, not about the shape.
    assert _nullable(await adapter.relation_model(f"{schema}.customers"), "tags") is True


async def test_the_count_of_rows_in_the_way_stops_at_its_ceiling(schema: str) -> None:
    adapter = _adapter()
    await _one_region(schema)
    await run(
        f"INSERT INTO {schema}.customers (region_id, region_code, name) "  # noqa: S608 -- fixture-owned schema.
        "SELECT 1, 'EU', 'c' || g FROM generate_series(1, "
        f"{COUNT_CEILING + 1}) AS g"
    )

    result = await adapter.change_column_nullability(
        ColumnNullabilityRequest(
            node_id=f"{schema}.customers", name="tags", nullable=False
        )
    )

    assert isinstance(result, NullabilityBlocked)
    assert result.rows_without_value == COUNT_CEILING
    assert result.exact is False


async def test_a_key_or_identity_column_is_named_rather_than_sent_to_the_server(
    schema: str,
) -> None:
    adapter = _adapter()

    with pytest.raises(ValueError, match="identity column"):
        await adapter.change_column_nullability(
            ColumnNullabilityRequest(
                node_id=f"{schema}.customers", name="id", nullable=True
            )
        )
    with pytest.raises(ValueError, match="primary key"):
        await adapter.change_column_nullability(
            ColumnNullabilityRequest(
                node_id=f"{schema}.regions", name="code", nullable=True
            )
        )


async def test_nullability_rejects_unknown_column_unchanged_state_and_a_view(
    schema: str,
) -> None:
    adapter = _adapter()

    with pytest.raises(ValueError, match="no column"):
        await adapter.change_column_nullability(
            ColumnNullabilityRequest(
                node_id=f"{schema}.customers", name="missing", nullable=True
            )
        )
    with pytest.raises(ValueError, match="already requires"):
        await adapter.change_column_nullability(
            ColumnNullabilityRequest(
                node_id=f"{schema}.customers", name="name", nullable=False
            )
        )
    with pytest.raises(ValueError, match="already accepts"):
        await adapter.change_column_nullability(
            ColumnNullabilityRequest(
                node_id=f"{schema}.customers", name="tags", nullable=True
            )
        )
    with pytest.raises(ValueError, match="Only tables"):
        await adapter.change_column_nullability(
            ColumnNullabilityRequest(
                node_id=f"{schema}.rich_customers", name="name", nullable=True
            )
        )


async def test_the_counting_query_composes_the_column_name_too(schema: str) -> None:
    """The count is a second place an identifier enters SQL, so it is checked."""
    adapter = _adapter()
    name = 'note"; DROP TABLE regions; --'
    await adapter.add_column(
        AddColumnRequest(node_id=f"{schema}.customers", name=name, type_code="text")
    )

    result = await adapter.change_column_nullability(
        ColumnNullabilityRequest(
            node_id=f"{schema}.customers", name=name, nullable=False
        )
    )

    assert isinstance(result, NullabilityChanged)
    assert _nullable(await adapter.relation_model(f"{schema}.customers"), name) is False
    assert (await adapter.relation_model(f"{schema}.regions")).name == "regions"


def _type_sql(model: RelationModel, name: str) -> str:
    return next(column for column in model.columns if column.name == name).type.sql


async def _customer_with(schema: str, column: str, value: str) -> None:
    """One row, with a value in a column the fixture itself does not have."""
    await run(
        f"INSERT INTO {schema}.customers "  # noqa: S608 -- fixture-owned schema.
        f'(region_id, region_code, name, "{column}") '
        f"VALUES (1, 'EU', 'c' || gen_random_uuid(), '{value}')"
    )


async def test_changes_a_type_the_rows_can_take(schema: str) -> None:
    adapter = _adapter()
    await _one_region(schema)
    await adapter.add_column(
        AddColumnRequest(node_id=f"{schema}.customers", name="score", type_code="text")
    )
    await _customer_with(schema, "score", "42")

    result = await adapter.change_column_type(
        ColumnTypeRequest(
            node_id=f"{schema}.customers", name="score", type_code="integer"
        )
    )

    assert isinstance(result, ColumnTypeChanged)
    assert result.type_sql == "integer"
    model = await adapter.relation_model(f"{schema}.customers")
    assert _type_sql(model, "score") == "integer"


async def test_counts_the_values_the_new_type_cannot_read(schema: str) -> None:
    adapter = _adapter()
    await _one_region(schema)
    await adapter.add_column(
        AddColumnRequest(node_id=f"{schema}.customers", name="score", type_code="text")
    )
    await _customer_with(schema, "score", "42")
    await _customer_with(schema, "score", "ann")
    await _customer_with(schema, "score", "bob")

    result = await adapter.change_column_type(
        ColumnTypeRequest(
            node_id=f"{schema}.customers", name="score", type_code="integer"
        )
    )

    assert isinstance(result, ColumnTypeBlocked)
    assert result.rows_not_convertible == 2
    assert result.exact is True
    # Nothing was rewritten: the answer is about the values, not the shape.
    model = await adapter.relation_model(f"{schema}.customers")
    assert _type_sql(model, "score") == "text"


async def test_the_count_of_unreadable_values_stops_at_its_ceiling(
    schema: str,
) -> None:
    adapter = _adapter()
    await _one_region(schema)
    await adapter.add_column(
        AddColumnRequest(node_id=f"{schema}.customers", name="score", type_code="text")
    )
    await run(
        f"INSERT INTO {schema}.customers (region_id, region_code, name, score) "  # noqa: S608 -- fixture-owned schema.
        "SELECT 1, 'EU', 'c' || g, 'not a number' FROM generate_series(1, "
        f"{COUNT_CEILING + 1}) AS g"
    )

    result = await adapter.change_column_type(
        ColumnTypeRequest(
            node_id=f"{schema}.customers", name="score", type_code="integer"
        )
    )

    assert isinstance(result, ColumnTypeBlocked)
    assert result.rows_not_convertible == COUNT_CEILING
    assert result.exact is False


async def test_a_column_that_is_not_a_string_is_attempted_without_a_count(
    schema: str,
) -> None:
    """There is no TRY_CAST, so a cast function is attempted, not predicted."""
    adapter = _adapter()
    await _one_region(schema)
    await adapter.add_column(
        AddColumnRequest(
            node_id=f"{schema}.customers", name="score", type_code="integer"
        )
    )
    await _customer_with(schema, "score", "7")

    result = await adapter.change_column_type(
        ColumnTypeRequest(node_id=f"{schema}.customers", name="score", type_code="text")
    )

    assert isinstance(result, ColumnTypeChanged)
    assert result.type_sql == "text"


async def test_two_types_with_no_conversion_are_refused_before_the_table(
    schema: str,
) -> None:
    """The parser answers, so nothing here restates PostgreSQL's coercion rules."""
    adapter = _adapter()

    with pytest.raises(ValueError, match="no conversion"):
        await adapter.change_column_type(
            ColumnTypeRequest(
                node_id=f"{schema}.customers", name="token", type_code="integer"
            )
        )
    with pytest.raises(ValueError, match="no conversion"):
        await adapter.change_column_type(
            ColumnTypeRequest(
                node_id=f"{schema}.customers", name="tags", type_code="integer"
            )
        )


async def test_a_default_that_cannot_be_cast_is_named(schema: str) -> None:
    adapter = _adapter()
    await adapter.add_column(
        AddColumnRequest(node_id=f"{schema}.customers", name="score", type_code="text")
    )
    await adapter.change_column_default(
        ColumnDefaultRequest(
            node_id=f"{schema}.customers", name="score", action="set", value="hello"
        )
    )

    with pytest.raises(ValueError, match="Remove the column's default"):
        await adapter.change_column_type(
            ColumnTypeRequest(
                node_id=f"{schema}.customers", name="score", type_code="integer"
            )
        )


async def test_a_view_on_the_column_is_named(schema: str) -> None:
    adapter = _adapter()

    with pytest.raises(ValueError, match="view or rule"):
        await adapter.change_column_type(
            ColumnTypeRequest(
                node_id=f"{schema}.customers", name="name", type_code="integer"
            )
        )


async def test_type_change_rejects_unknown_column_code_generated_and_same_type(
    schema: str,
) -> None:
    adapter = _adapter()

    with pytest.raises(ValueError, match="no column"):
        await adapter.change_column_type(
            ColumnTypeRequest(
                node_id=f"{schema}.customers", name="missing", type_code="text"
            )
        )
    with pytest.raises(ValueError, match="Unknown column type"):
        await adapter.change_column_type(
            ColumnTypeRequest(
                node_id=f"{schema}.customers",
                name="payload",
                type_code="text USING payload::text, DROP COLUMN tags",
            )
        )
    with pytest.raises(ValueError, match="generated column"):
        await adapter.change_column_type(
            ColumnTypeRequest(
                node_id=f"{schema}.customers", name="name_upper", type_code="integer"
            )
        )
    with pytest.raises(ValueError, match="identity column"):
        await adapter.change_column_type(
            ColumnTypeRequest(node_id=f"{schema}.customers", name="id", type_code="text")
        )
    with pytest.raises(ValueError, match="already has type"):
        await adapter.change_column_type(
            ColumnTypeRequest(
                node_id=f"{schema}.customers", name="payload", type_code="jsonb"
            )
        )
    with pytest.raises(ValueError, match="Only tables"):
        await adapter.change_column_type(
            ColumnTypeRequest(
                node_id=f"{schema}.rich_customers", name="name", type_code="text"
            )
        )


async def test_the_conversion_composes_a_quoted_column_name(schema: str) -> None:
    """Three statements name the column: the probe, the count and the ALTER."""
    adapter = _adapter()
    name = 'note"; DROP TABLE regions; --'
    await adapter.add_column(
        AddColumnRequest(node_id=f"{schema}.customers", name=name, type_code="text")
    )

    result = await adapter.change_column_type(
        ColumnTypeRequest(node_id=f"{schema}.customers", name=name, type_code="integer")
    )

    assert isinstance(result, ColumnTypeChanged)
    model = await adapter.relation_model(f"{schema}.customers")
    assert _type_sql(model, name) == "integer"
    assert (await adapter.relation_model(f"{schema}.regions")).name == "regions"
