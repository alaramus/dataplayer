import pytest
from pydantic import ValidationError

from app.adapters.fetch import FetchColumn, FetchRequest, Filter, Sort
from app.adapters.relation import ColumnType


def test_defaults_are_bounded() -> None:
    request = FetchRequest(node_id="public.connector")

    assert request.limit == 100
    assert request.offset == 0
    assert request.filters == []
    assert request.sort == []


@pytest.mark.parametrize("limit", [0, -1, 1001])
def test_limit_outside_the_allowed_range_is_rejected(limit: int) -> None:
    """The old application defaulted to limit=-1, meaning no limit at all."""
    with pytest.raises(ValidationError):
        FetchRequest(node_id="public.connector", limit=limit)


def test_negative_offset_is_rejected() -> None:
    with pytest.raises(ValidationError):
        FetchRequest(node_id="public.connector", offset=-1)


def test_unknown_operator_is_rejected() -> None:
    """Operators are a closed set: an arbitrary string never reaches SQL."""
    with pytest.raises(ValidationError):
        Filter(column="id", op="; DROP TABLE users --", value=1)  # type: ignore[arg-type]


def test_filter_without_value_is_allowed_for_null_checks() -> None:
    assert Filter(column="updated_at", op="is_null").value is None


def test_sort_defaults_to_ascending() -> None:
    assert Sort(column="name").descending is False


def test_a_fetch_column_states_type_and_operations() -> None:
    column = FetchColumn(
        name="amount",
        type=ColumnType(
            sql="numeric(20,2)", category="number", precision=20, scale=2
        ),
        sortable=True,
        filter_operators=["eq", "gt", "is_null"],
    )

    assert column.type.category == "number"
    assert column.sortable is True
    assert column.filter_operators == ["eq", "gt", "is_null"]
