import pytest
from pydantic import TypeAdapter, ValidationError

from app.adapters.relation import (
    Column,
    ColumnType,
    Constraint,
    ForeignKey,
    PrimaryKey,
    RelationModel,
)


def _text() -> ColumnType:
    return ColumnType(sql="text", category="string")


def test_a_scalar_type_needs_only_its_sql_and_category() -> None:
    column_type = ColumnType(sql="text", category="string")

    assert column_type.dimensions == 0
    assert column_type.element is None
    assert column_type.enum_values is None


def test_an_array_type_carries_its_element_and_depth() -> None:
    column_type = ColumnType(
        sql="integer[]",
        category="array",
        dimensions=1,
        element=ColumnType(sql="integer", category="number"),
    )

    assert column_type.element is not None
    assert column_type.element.category == "number"


def test_a_field_of_one_constraint_is_not_accepted_on_another() -> None:
    """The union is closed: a key belonging to a foreign key must fail loudly."""
    adapter = TypeAdapter(Constraint)

    with pytest.raises(ValidationError):
        adapter.validate_python(
            {
                "kind": "primary_key",
                "name": "orders_pkey",
                "columns": ["id"],
                "target_node_id": "public.customers",
            }
        )


def test_a_foreign_key_names_the_target_as_a_node_id() -> None:
    key = ForeignKey(
        name="orders_customer_fkey",
        columns=["customer_id", "customer_region"],
        target_node_id="public.customers",
        target_columns=["id", "region"],
        on_update="no_action",
        on_delete="cascade",
        match="simple",
    )

    assert key.kind == "foreign_key"
    assert key.columns == ["customer_id", "customer_region"]


def test_a_relation_model_holds_columns_constraints_and_indexes() -> None:
    model = RelationModel(
        node_id="public.orders",
        schema_name="public",
        name="orders",
        kind="table",
        owner="postgres",
        persistence="permanent",
        columns=[
            Column(position=1, name="id", type=_text(), nullable=False, storage="plain")
        ],
        constraints=[PrimaryKey(name="orders_pkey", columns=["id"])],
    )

    assert model.indexes == []
    assert model.partitioning is None
