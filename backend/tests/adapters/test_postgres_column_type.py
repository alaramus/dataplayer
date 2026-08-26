from typing import Any

from app.adapters.postgres.column_type import build_column_type


def _row(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "sql_type": "text",
        "type_category": "S",
        "type_name": "text",
        "type_mod": -1,
        "element_sql": None,
        "element_category": None,
        "element_name": None,
        "enum_values": None,
        "element_enum_values": None,
    }
    base.update(overrides)
    return base


def test_a_plain_type_keeps_what_format_type_said() -> None:
    result = build_column_type(_row())
    assert result.sql == "text"
    assert result.category == "string"


def test_an_array_is_a_category_of_its_own_and_carries_its_element() -> None:
    result = build_column_type(
        _row(
            sql_type="integer[]",
            type_category="A",
            type_name="_int4",
            element_sql="integer",
            element_category="N",
            element_name="int4",
        )
    )
    assert result.sql == "integer[]"
    assert result.category == "array"
    assert result.dimensions == 1
    assert result.element is not None
    assert result.element.sql == "integer"
    assert result.element.category == "number"


def test_a_two_dimensional_array_is_counted_from_the_sql() -> None:
    result = build_column_type(
        _row(
            sql_type="integer[][]",
            type_category="A",
            type_name="_int4",
            element_sql="integer",
            element_category="N",
            element_name="int4",
        )
    )
    assert result.dimensions == 2


def test_varchar_keeps_its_length() -> None:
    result = build_column_type(
        _row(
            sql_type="character varying(50)",
            type_category="S",
            type_name="varchar",
            type_mod=54,
        )
    )
    assert result.length == 50


def test_numeric_keeps_precision_and_scale() -> None:
    result = build_column_type(
        _row(
            sql_type="numeric(10,2)",
            type_category="N",
            type_name="numeric",
            type_mod=((10 << 16) | 2) + 4,
        )
    )
    assert result.precision == 10
    assert result.scale == 2


def test_the_types_postgres_files_under_user_defined_are_told_apart() -> None:
    assert build_column_type(
        _row(sql_type="jsonb", type_category="U", type_name="jsonb")
    ).category == "json"
    assert build_column_type(
        _row(sql_type="uuid", type_category="U", type_name="uuid")
    ).category == "uuid"
    assert build_column_type(
        _row(sql_type="bytea", type_category="U", type_name="bytea")
    ).category == "binary"


def test_an_enum_carries_its_labels_in_declared_order() -> None:
    result = build_column_type(
        _row(
            sql_type="public.mood",
            type_category="E",
            type_name="mood",
            enum_values=["sad", "ok", "happy"],
        )
    )
    assert result.category == "enum"
    assert result.enum_values == ["sad", "ok", "happy"]


def test_an_array_of_enums_carries_the_labels_on_the_element() -> None:
    result = build_column_type(
        _row(
            sql_type="public.mood[]",
            type_category="A",
            type_name="_mood",
            element_sql="public.mood",
            element_category="E",
            element_name="mood",
            element_enum_values=["sad", "ok", "happy"],
        )
    )
    assert result.element is not None
    assert result.element.enum_values == ["sad", "ok", "happy"]


def test_an_unknown_category_falls_through_rather_than_failing() -> None:
    result = build_column_type(
        _row(sql_type="pg_lsn", type_category="Z", type_name="pg_lsn")
    )
    assert result.category == "other"
