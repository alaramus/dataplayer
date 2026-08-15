import pytest
from pydantic import TypeAdapter, ValidationError

from app.adapters.catalog import CatalogNode, ColumnNode, SchemaNode, TableNode
from app.adapters.protocol import AdapterError

nodes = TypeAdapter(list[CatalogNode])


def test_union_discriminates_by_kind() -> None:
    parsed = nodes.validate_python(
        [
            {"id": "public", "name": "public", "has_children": True, "kind": "schema"},
            {
                "id": "public.users",
                "name": "users",
                "has_children": True,
                "kind": "table",
                "row_count_estimate": 42,
            },
            {
                "id": "public.users.email",
                "name": "email",
                "has_children": False,
                "kind": "column",
                "data_type": "varchar",
                "nullable": False,
            },
        ]
    )

    assert isinstance(parsed[0], SchemaNode)
    assert isinstance(parsed[1], TableNode)
    assert isinstance(parsed[2], ColumnNode)
    assert parsed[1].row_count_estimate == 42
    assert parsed[2].data_type == "varchar"


def test_unknown_kind_is_rejected() -> None:
    with pytest.raises(ValidationError):
        nodes.validate_python(
            [{"id": "x", "name": "x", "has_children": False, "kind": "wormhole"}]
        )


def test_a_field_of_one_kind_is_not_accepted_on_another() -> None:
    """The failure the old application allowed: one key, two meanings.

    A schema node must not silently carry table metadata.
    """
    with pytest.raises(ValidationError):
        nodes.validate_python(
            [
                {
                    "id": "public",
                    "name": "public",
                    "has_children": True,
                    "kind": "schema",
                    "data_type": "varchar",
                }
            ]
        )


def test_column_has_no_children_by_default() -> None:
    column = ColumnNode(
        id="public.users.email", name="email", data_type="varchar", nullable=True
    )

    assert column.has_children is False


def test_adapter_error_carries_kind_and_message() -> None:
    error = AdapterError("network", "Could not reach the database server")

    assert error.error_kind == "network"
    assert error.message == "Could not reach the database server"
    assert "Could not reach" in str(error)
