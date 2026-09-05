"""A JSON file as a table: the whole file decides the columns."""

import json
from pathlib import Path

import pytest

from app.adapters.file import records
from app.adapters.file.records import NotRecords, Table


def write(root: Path, name: str, text: str) -> Path:
    path = root / name
    path.write_text(text, encoding="utf-8")
    return path


def table(path: Path) -> Table:
    result = records.read(path)
    assert isinstance(result, Table)
    return result


def refusal(path: Path) -> NotRecords:
    result = records.read(path)
    assert isinstance(result, NotRecords)
    return result


def test_an_array_of_objects_becomes_a_row_each(tmp_path: Path) -> None:
    path = write(tmp_path, "a.json", '[{"id": 1, "name": "Ann"}, {"id": 2}]')

    result = table(path)

    assert [column.name for column in result.columns] == ["id", "name"]
    assert result.rows == [["1", "Ann"], ["2", None]]


def test_a_key_seen_only_in_a_later_record_is_still_a_column(tmp_path: Path) -> None:
    """The reason the file is read whole: a page must not decide the shape."""
    path = write(tmp_path, "a.json", '[{"id": 1}, {"id": 2, "city": "Riga"}]')

    result = table(path)

    assert [column.name for column in result.columns] == ["id", "city"]
    assert result.rows == [["1", None], ["2", "Riga"]]


def test_columns_keep_the_order_they_were_first_seen_in(tmp_path: Path) -> None:
    path = write(tmp_path, "a.json", '[{"b": 1}, {"a": 2}, {"c": 3, "a": 4}]')

    result = table(path)

    assert [column.name for column in result.columns] == ["b", "a", "c"]


def test_a_lone_object_is_a_table_of_one_row(tmp_path: Path) -> None:
    path = write(tmp_path, "a.json", '{"id": 1, "name": "Ann"}')

    result = table(path)

    assert [column.name for column in result.columns] == ["id", "name"]
    assert result.rows == [["1", "Ann"]]


def test_records_that_are_not_all_objects_share_one_column(tmp_path: Path) -> None:
    path = write(tmp_path, "a.json", '[1, "two", {"a": 1}]')

    result = table(path)

    assert [column.name for column in result.columns] == ["value"]
    assert result.rows == [["1"], ["two"], ['{"a":1}']]


def test_an_empty_array_is_a_table_with_no_columns(tmp_path: Path) -> None:
    path = write(tmp_path, "a.json", "[]")

    result = table(path)

    assert result.columns == []
    assert result.rows == []


def test_a_key_that_is_empty_is_given_a_usable_name(tmp_path: Path) -> None:
    """The same rule a delimited header goes through: names are addressable."""
    path = write(tmp_path, "a.json", '[{"": 1}]')

    result = table(path)

    assert [column.name for column in result.columns] == ["column_1"]


def test_a_column_states_the_type_the_file_gives_it(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        "a.json",
        '[{"n": 1, "s": "x", "b": true, "j": {"k": 1}, "empty": null}]',
    )

    result = table(path)

    assert {column.name: column.type.category for column in result.columns} == {
        "n": "number",
        "s": "string",
        "b": "boolean",
        "j": "json",
        "empty": "string",
    }


def test_a_column_whose_records_disagree_is_text(tmp_path: Path) -> None:
    path = write(tmp_path, "a.json", '[{"v": 1}, {"v": "one"}]')

    result = table(path)

    assert result.columns[0].type.category == "string"


def test_a_null_does_not_decide_the_type_of_a_column(tmp_path: Path) -> None:
    path = write(tmp_path, "a.json", '[{"v": null}, {"v": 1}]')

    result = table(path)

    assert result.columns[0].type.category == "number"


def test_a_json_projection_states_no_operators_of_its_own(
    tmp_path: Path,
) -> None:
    """Equality is added by the source that reads the page, not here (D109)."""
    path = write(tmp_path, "a.json", '[{"n": 1}]')

    result = table(path)

    assert result.columns[0].sortable is False
    assert result.columns[0].filter_operators == []


def test_a_large_number_keeps_every_digit(tmp_path: Path) -> None:
    """A float would round it, and the value is an identifier."""
    path = write(tmp_path, "a.json", '[{"id": 10000000000000001}]')

    result = table(path)

    assert result.rows == [["10000000000000001"]]


def test_a_nested_value_is_compact_json_text(tmp_path: Path) -> None:
    path = write(tmp_path, "a.json", '[{"tags": ["a", "b"]}]')

    result = table(path)

    assert result.rows == [['["a","b"]']]


def test_a_string_is_itself_rather_than_quoted_json(tmp_path: Path) -> None:
    path = write(tmp_path, "a.json", '[{"s": "a,b"}]')

    result = table(path)

    assert result.rows == [["a,b"]]


def test_one_record_per_line_is_read_by_the_extension(tmp_path: Path) -> None:
    path = write(tmp_path, "a.jsonl", '{"id": 1}\n{"id": 2, "city": "Riga"}\n')

    result = table(path)

    assert [column.name for column in result.columns] == ["id", "city"]
    assert result.rows == [["1", None], ["2", "Riga"]]


def test_ndjson_is_the_same_format_under_another_name(tmp_path: Path) -> None:
    path = write(tmp_path, "a.ndjson", '{"id": 1}\n')

    assert table(path).rows == [["1"]]


def test_a_blank_line_separates_records_rather_than_being_one(
    tmp_path: Path,
) -> None:
    path = write(tmp_path, "a.jsonl", '{"id": 1}\n\n{"id": 2}\n')

    assert table(path).rows == [["1"], ["2"]]


def test_a_document_that_does_not_parse_is_refused_with_its_place(
    tmp_path: Path,
) -> None:
    path = write(tmp_path, "a.json", '{"a": 1,\n "b" 2}')

    reason = refusal(path).reason

    assert "line 2" in reason
    assert "projected as a table" in reason


def test_a_line_that_does_not_parse_names_its_line(tmp_path: Path) -> None:
    path = write(tmp_path, "a.jsonl", '{"a": 1}\nnot json\n')

    assert "Line 2" in refusal(path).reason


def test_a_file_too_large_to_read_whole_is_refused(tmp_path: Path) -> None:
    """The bound is what keeps the whole-file pass a bounded request."""
    filler = "x" * 200
    rows = [json.dumps({"id": index, "filler": filler}) for index in range(30_000)]
    path = write(tmp_path, "a.jsonl", "\n".join(rows))
    assert path.stat().st_size > records.MAX_RECORD_BYTES

    assert "larger than" in refusal(path).reason


def test_text_that_is_not_utf8_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "a.json"
    path.write_bytes(b'["\xff\xfe"]')

    assert "UTF-8" in refusal(path).reason


@pytest.mark.parametrize("text", ["", "   "])
def test_an_empty_file_is_not_a_json_document(tmp_path: Path, text: str) -> None:
    path = write(tmp_path, "a.json", text)

    assert isinstance(records.read(path), NotRecords)
