import uuid

import pytest
from pydantic import ValidationError

from app.shares.view import MAX_COLUMNS, RowsView, fingerprint_of


def test_two_ways_of_writing_one_view_have_one_fingerprint() -> None:
    """D59: pressing Share twice gives one address.

    The digest is taken over the validated body, so a client that omits a
    default and one that sends it are still the same view.
    """
    connector = uuid.uuid4()
    spelled_out = RowsView.model_validate(
        {
            "kind": "rows",
            "page_size": 100,
            "filters": [],
            "sort": [{"column": "name", "descending": False}],
            "column_order": [],
            "pinned_left": [],
            "column_visibility": {},
            "column_sizing": {},
        }
    )
    terse = RowsView.model_validate({"sort": [{"column": "name"}]})
    assert fingerprint_of(connector, "public.orders", spelled_out) == fingerprint_of(
        connector, "public.orders", terse
    )


def test_the_same_view_of_another_node_is_another_fingerprint() -> None:
    view = RowsView()
    connector = uuid.uuid4()
    assert fingerprint_of(connector, "public.orders", view) != fingerprint_of(
        connector, "public.customers", view
    )
    assert fingerprint_of(connector, "public.orders", view) != fingerprint_of(
        uuid.uuid4(), "public.orders", view
    )


def test_a_field_that_belongs_to_no_kind_is_refused() -> None:
    with pytest.raises(ValidationError):
        RowsView.model_validate({"kind": "rows", "offset": 40})


def test_an_unknown_kind_is_refused() -> None:
    with pytest.raises(ValidationError):
        RowsView.model_validate({"kind": "chart"})


def test_a_filter_is_a_predicate_and_not_a_fragment() -> None:
    with pytest.raises(ValidationError):
        RowsView.model_validate(
            {"filters": [{"column": "id", "op": "; drop table", "value": "1"}]}
        )


def test_the_page_size_has_a_ceiling() -> None:
    with pytest.raises(ValidationError):
        RowsView.model_validate({"page_size": 100_000})


def test_a_layout_is_bounded() -> None:
    """A body arrives from a client and is stored, so it cannot be unbounded."""
    with pytest.raises(ValidationError):
        RowsView.model_validate(
            {"column_order": [f"c{index}" for index in range(MAX_COLUMNS + 1)]}
        )
    with pytest.raises(ValidationError):
        RowsView.model_validate({"column_sizing": {"name": -5}})
    with pytest.raises(ValidationError):
        RowsView.model_validate({"column_visibility": {"n" * 300: False}})
