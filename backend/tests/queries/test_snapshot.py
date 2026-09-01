"""Reading a captured result: which rows, in what order, and as CSV.

Pure, because none of it touches a source: the rows were read once and every
question after that is asked of them (D64).
"""

import pytest

from app.adapters.query import MaterialisedResult, ResultColumn
from app.adapters.relation import ColumnType
from app.queries import snapshot
from app.queries.snapshot import SnapshotSort, SnapshotView


def result(
    rows: list[list[str | None]], categories: list[str] | None = None
) -> MaterialisedResult:
    width = len(rows[0]) if rows else 1
    kinds = categories or ["string"] * width
    return MaterialisedResult(
        columns=[
            ResultColumn(
                id=str(index),
                name=f"c{index}",
                type=ColumnType(sql="text", category=kind),  # type: ignore[arg-type]
            )
            for index, kind in enumerate(kinds)
        ],
        rows=rows,
    )


def view(**kwargs: object) -> SnapshotView:
    return SnapshotView.model_validate(kwargs)


def test_numbers_sort_by_value_and_not_by_their_text() -> None:
    """"9" before "10" is what a text sort would say, and it is wrong."""
    captured = result([["9"], ["10"], ["1.5"]], ["number"])

    ordered = snapshot.apply(captured, view(sort=[{"column": "0"}]))

    assert ordered == [["1.5"], ["9"], ["10"]]


def test_numbers_keep_their_precision() -> None:
    """A float would round these two into one value."""
    captured = result(
        [["12345678901234567890.2"], ["12345678901234567890.1"]], ["number"]
    )

    ordered = snapshot.apply(captured, view(sort=[{"column": "0"}]))

    assert ordered == [["12345678901234567890.1"], ["12345678901234567890.2"]]


def test_dates_and_times_sort_chronologically() -> None:
    captured = result(
        [["2026-01-02T00:00:00"], ["2025-12-31T23:59:59"], ["2026-01-01T12:00:00"]],
        ["datetime"],
    )

    ordered = snapshot.apply(captured, view(sort=[{"column": "0"}]))

    assert [row[0] for row in ordered] == [
        "2025-12-31T23:59:59",
        "2026-01-01T12:00:00",
        "2026-01-02T00:00:00",
    ]


def test_booleans_sort_false_before_true() -> None:
    captured = result([["true"], ["false"], ["true"]], ["boolean"])

    ordered = snapshot.apply(captured, view(sort=[{"column": "0"}]))

    assert [row[0] for row in ordered] == ["false", "true", "true"]


def test_text_sorts_by_code_point_rather_than_by_a_collation() -> None:
    captured = result([["b"], ["A"], ["a"], ["B"]])

    ordered = snapshot.apply(captured, view(sort=[{"column": "0"}]))

    assert [row[0] for row in ordered] == ["A", "B", "a", "b"]


@pytest.mark.parametrize("descending", [False, True])
def test_null_stays_at_the_far_end_whichever_way_a_column_sorts(
    descending: bool,
) -> None:
    captured = result([["2"], [None], ["1"]], ["number"])

    ordered = snapshot.apply(
        captured, view(sort=[{"column": "0", "descending": descending}])
    )

    assert ordered[-1] == [None]


def test_the_original_order_is_the_tiebreaker() -> None:
    captured = result([["1", "first"], ["1", "second"], ["1", "third"]], ["number", "string"])

    ordered = snapshot.apply(captured, view(sort=[{"column": "0"}]))

    assert [row[1] for row in ordered] == ["first", "second", "third"]


def test_several_keys_are_read_left_to_right() -> None:
    captured = result(
        [["b", "2"], ["a", "2"], ["b", "1"], ["a", "1"]], ["string", "number"]
    )

    ordered = snapshot.apply(
        captured,
        view(sort=[{"column": "0"}, {"column": "1", "descending": True}]),
    )

    assert ordered == [["a", "2"], ["a", "1"], ["b", "2"], ["b", "1"]]


def test_filters_compare_as_the_column_holds_rather_than_as_text() -> None:
    captured = result([["9"], ["10"], ["11"]], ["number"])

    kept = snapshot.apply(
        captured, view(filters=[{"column": "0", "op": "gt", "value": "9"}])
    )

    assert kept == [["10"], ["11"]]


def test_text_filters_ignore_case_where_they_say_they_do() -> None:
    captured = result([["Invoice"], ["invoiced"], ["other"]])

    assert snapshot.apply(
        captured, view(filters=[{"column": "0", "op": "contains", "value": "INVOICE"}])
    ) == [["Invoice"], ["invoiced"]]
    assert snapshot.apply(
        captured,
        view(filters=[{"column": "0", "op": "starts_with", "value": "invoiceD"}]),
    ) == [["invoiced"]]


def test_null_is_asked_for_and_never_matched_by_a_comparison() -> None:
    captured = result([["1"], [None], ["2"]], ["number"])

    assert snapshot.apply(
        captured, view(filters=[{"column": "0", "op": "is_null"}])
    ) == [[None]]
    assert snapshot.apply(
        captured, view(filters=[{"column": "0", "op": "is_not_null"}])
    ) == [["1"], ["2"]]
    assert snapshot.apply(
        captured, view(filters=[{"column": "0", "op": "gt", "value": "0"}])
    ) == [["1"], ["2"]]


def test_one_of_several_values_is_matched_exactly() -> None:
    captured = result([["a"], ["b"], ["c"]])

    kept = snapshot.apply(
        captured, view(filters=[{"column": "0", "op": "in", "values": ["a", "c"]}])
    )

    assert kept == [["a"], ["c"]]


def test_filters_are_applied_together() -> None:
    captured = result([["1", "x"], ["2", "y"], ["3", "x"]], ["number", "string"])

    kept = snapshot.apply(
        captured,
        view(
            filters=[
                {"column": "0", "op": "gte", "value": "2"},
                {"column": "1", "op": "eq", "value": "x"},
            ]
        ),
    )

    assert kept == [["3", "x"]]


def test_a_column_this_result_does_not_have_is_refused() -> None:
    captured = result([["1"]])

    with pytest.raises(ValueError, match="no column"):
        snapshot.apply(captured, view(sort=[{"column": "7"}]))


def test_a_sort_is_typed_by_its_own_column() -> None:
    """The category of the column being sorted, not of the first one."""
    captured = result([["x", "9"], ["y", "10"]], ["string", "number"])

    ordered = snapshot.apply(captured, view(sort=[SnapshotSort(column="1").model_dump()]))

    assert ordered == [["x", "9"], ["y", "10"]]


def test_csv_keeps_null_and_an_empty_string_apart() -> None:
    captured = result([[None, ""]])

    written = snapshot.to_csv(captured.columns, captured.rows).decode("utf-8-sig")

    assert written.splitlines()[1] == ',""'


def test_csv_starts_with_the_headings_as_they_are_shown() -> None:
    captured = result([["1"]])

    written = snapshot.to_csv(captured.columns, captured.rows).decode("utf-8-sig")

    # Quoted, because that is what keeps a null apart from an empty string
    # everywhere in the row below it.
    assert written.splitlines()[0] == '"c0"'


def test_a_filename_carries_nothing_but_a_name() -> None:
    assert snapshot.safe_stem('../../etc/passwd"') == "etc-passwd"
    assert snapshot.safe_stem("   ") == "result"
