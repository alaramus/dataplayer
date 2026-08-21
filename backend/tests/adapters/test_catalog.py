import pytest
from pydantic import TypeAdapter, ValidationError

from app.adapters.catalog import (
    CatalogNode,
    ColumnNode,
    DirectoryNode,
    FileNode,
    SchemaNode,
    TableNode,
)
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


def test_directories_and_files_are_their_own_kinds() -> None:
    """A file source shares only id, name and has_children with a database."""
    parsed = nodes.validate_python(
        [
            {
                "id": "reports",
                "name": "reports",
                "has_children": True,
                "kind": "directory",
            },
            {
                "id": "reports/q3.csv",
                "name": "q3.csv",
                "has_children": False,
                "kind": "file",
                "size_bytes": 2048,
                "content_kind": "table",
            },
        ]
    )

    assert isinstance(parsed[0], DirectoryNode)
    assert isinstance(parsed[1], FileNode)
    assert parsed[1].content_kind == "table"


def test_a_file_cannot_borrow_a_table_field() -> None:
    with pytest.raises(ValidationError):
        nodes.validate_python(
            [
                {
                    "id": "reports/q3.csv",
                    "name": "q3.csv",
                    "has_children": False,
                    "kind": "file",
                    "size_bytes": 2048,
                    "content_kind": "table",
                    "row_count_estimate": 100,
                }
            ]
        )


def test_unknown_content_kind_is_rejected() -> None:
    with pytest.raises(ValidationError):
        nodes.validate_python(
            [
                {
                    "id": "reports/q3.parquet",
                    "name": "q3.parquet",
                    "has_children": False,
                    "kind": "file",
                    "size_bytes": 1,
                    "content_kind": "columnar",
                }
            ]
        )
