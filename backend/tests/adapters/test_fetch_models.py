import pytest
from pydantic import ValidationError

from app.adapters.fetch import FetchColumn, FetchRequest, Sort
from app.adapters.relation import ColumnType


def test_defaults_are_bounded() -> None:
    request = FetchRequest(node_id="public.connector")

    assert request.limit == 100
    assert request.offset == 0
    assert request.filters == []
    assert request.sort == []


@pytest.mark.parametrize("limit", [0, -1, 1001])
def test_limit_outside_the_allowed_range_is_rejected(limit: int) -> None:
    """-1 must not mean no limit at all."""
    with pytest.raises(ValidationError):
        FetchRequest(node_id="public.connector", limit=limit)


def test_negative_offset_is_rejected() -> None:
    with pytest.raises(ValidationError):
        FetchRequest(node_id="public.connector", offset=-1)


def test_unknown_operator_is_rejected() -> None:
    """Operators are a closed set: an arbitrary string never reaches SQL."""
    with pytest.raises(ValidationError):
        FetchRequest.model_validate(
            {
                "node_id": "public.events",
                "filters": [
                    {"column": "id", "op": "; DROP TABLE users --", "value": "1"}
                ],
            }
        )


def test_null_filter_rejects_a_value() -> None:
    """A null predicate has no value to accidentally bind into SQL."""
    with pytest.raises(ValidationError):
        FetchRequest.model_validate(
            {
                "node_id": "public.events",
                "filters": [{"column": "happened", "op": "is_null", "value": "x"}],
            }
        )


def test_in_filter_requires_values() -> None:
    """An empty IN list is not a meaningful predicate."""
    with pytest.raises(ValidationError):
        FetchRequest.model_validate(
            {
                "node_id": "public.events",
                "filters": [{"column": "id", "op": "in", "values": []}],
            }
        )


def test_scalar_filter_requires_one_text_value() -> None:
    """Filter values cross the boundary as exact text before server coercion."""
    request = FetchRequest.model_validate(
        {
            "node_id": "public.events",
            "filters": [{"column": "id", "op": "gte", "value": "9007199254740993"}],
        }
    )

    assert request.filters[0].op == "gte"


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
