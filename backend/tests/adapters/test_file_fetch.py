import json
from pathlib import Path

import pytest

from app.adapters.fetch import FetchRequest, Sort
from app.adapters.file.fetch import FileFetch
from app.adapters.file.session import FileSession


@pytest.fixture
def root(tmp_path: Path) -> Path:
    rows = "\n".join(f"{index},city-{index}" for index in range(1, 11))
    (tmp_path / "cities.csv").write_text(f"id,name\n{rows}\n", encoding="utf-8")
    (tmp_path / "semicolons.csv").write_text("id;name\n1;one\n", encoding="utf-8")
    (tmp_path / "tabbed.tsv").write_text("id\tname\n1\tone\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("first\nsecond\nthird\n", encoding="utf-8")
    people = [{"id": number, "name": f"person-{number}"} for number in range(1, 6)]
    people[4]["city"] = "Riga"
    (tmp_path / "people.json").write_text(json.dumps(people), encoding="utf-8")
    (tmp_path / "broken.json").write_text('{"a" 1}', encoding="utf-8")
    (tmp_path / "logo.png").write_bytes(b"\x89PNG\r\n")
    (tmp_path / "guide.md").write_text("# Title\n")
    (tmp_path / "disguised.txt").write_bytes(b"text\x00binary")
    (tmp_path / "reports").mkdir()
    return tmp_path


@pytest.fixture
def fetch(root: Path) -> FileFetch:
    return FileFetch(FileSession(root))


async def test_the_header_line_names_the_columns(fetch: FileFetch) -> None:
    result = await fetch.fetch(FetchRequest(node_id="cities.csv", limit=2))

    assert [column.name for column in result.columns] == ["id", "name"]
    assert result.rows[0] == ["1", "city-1"]


async def test_columns_of_a_delimited_file_have_string_types(fetch: FileFetch) -> None:
    """A CSV carries no types, and inventing them would be a guess."""
    result = await fetch.fetch(FetchRequest(node_id="cities.csv", limit=1))

    assert {column.type.category for column in result.columns} == {"string"}
    assert all(column.sortable is False for column in result.columns)
    assert all(column.filter_operators == [] for column in result.columns)
    assert all(
        isinstance(cell, str)
        for row in result.rows
        for cell in row
        if cell is not None
    )
    assert result.update_supported is True
    assert result.insert_supported is True
    assert result.delete_supported is True
    assert all(
        column.editable and column.nullable and column.insertable
        for column in result.columns
    )
    assert all(handle is not None for handle in result.row_handles)


async def test_a_page_in_the_middle_knows_there_is_more(fetch: FileFetch) -> None:
    result = await fetch.fetch(FetchRequest(node_id="cities.csv", limit=3, offset=3))

    assert [row[0] for row in result.rows] == ["4", "5", "6"]
    assert result.has_more is True


async def test_the_last_page_knows_it_is_last(fetch: FileFetch) -> None:
    result = await fetch.fetch(FetchRequest(node_id="cities.csv", limit=5, offset=5))

    assert len(result.rows) == 5
    assert result.has_more is False


async def test_a_semicolon_file_is_still_read_as_columns(fetch: FileFetch) -> None:
    result = await fetch.fetch(FetchRequest(node_id="semicolons.csv"))

    assert [column.name for column in result.columns] == ["id", "name"]


async def test_a_tab_separated_file_is_read_by_its_extension(
    fetch: FileFetch,
) -> None:
    result = await fetch.fetch(FetchRequest(node_id="tabbed.tsv"))

    assert [column.name for column in result.columns] == ["id", "name"]


async def test_repeated_and_empty_column_names_are_made_usable(
    fetch: FileFetch, root: Path
) -> None:
    (root / "awkward.csv").write_text("id,,id\n1,2,3\n", encoding="utf-8")

    result = await fetch.fetch(FetchRequest(node_id="awkward.csv"))

    names = [column.name for column in result.columns]
    assert len(set(names)) == 3
    assert "" not in names


async def test_a_short_row_is_padded_to_the_header(
    fetch: FileFetch, root: Path
) -> None:
    (root / "ragged.csv").write_text("id,name,note\n1,one\n", encoding="utf-8")

    result = await fetch.fetch(FetchRequest(node_id="ragged.csv"))

    assert result.rows == [["1", "one", None]]


async def test_a_text_file_is_read_line_by_line(fetch: FileFetch) -> None:
    result = await fetch.fetch(FetchRequest(node_id="notes.txt", limit=2, offset=1))

    assert [column.name for column in result.columns] == ["line_no", "line"]
    assert result.rows == [["2", "second"], ["3", "third"]]
    assert result.has_more is False


async def test_a_file_source_admits_per_column_it_cannot_sort_or_filter(
    fetch: FileFetch,
) -> None:
    result = await fetch.fetch(FetchRequest(node_id="notes.txt"))

    assert all(column.sortable is False for column in result.columns)
    assert all(column.filter_operators == [] for column in result.columns)


async def test_asking_for_sorting_is_refused(fetch: FileFetch) -> None:
    request = FetchRequest(node_id="cities.csv", sort=[Sort(column="id")])

    with pytest.raises(ValueError, match="sort"):
        await fetch.fetch(request)


async def test_asking_for_a_filter_is_refused(fetch: FileFetch) -> None:
    request = FetchRequest.model_validate(
        {
            "node_id": "cities.csv",
            "filters": [{"column": "id", "op": "eq", "value": "1"}],
        }
    )

    with pytest.raises(ValueError, match="filter"):
        await fetch.fetch(request)


async def test_a_binary_file_is_refused(fetch: FileFetch) -> None:
    with pytest.raises(ValueError):
        await fetch.fetch(FetchRequest(node_id="logo.png"))


async def test_a_file_that_lies_about_its_extension_is_refused(
    fetch: FileFetch,
) -> None:
    """Classification is by name; the bytes get the last word."""
    with pytest.raises(ValueError):
        await fetch.fetch(FetchRequest(node_id="disguised.txt"))


async def test_a_document_is_not_a_table(fetch: FileFetch) -> None:
    """Markdown declares a document and a source, and neither one is rows."""
    with pytest.raises(ValueError, match="cannot be read as rows"):
        await fetch.fetch(FetchRequest(node_id="guide.md"))


async def test_a_directory_cannot_be_read_as_rows(fetch: FileFetch) -> None:
    with pytest.raises(ValueError):
        await fetch.fetch(FetchRequest(node_id="reports"))


async def test_a_missing_file_is_refused(fetch: FileFetch) -> None:
    with pytest.raises(ValueError):
        await fetch.fetch(FetchRequest(node_id="nowhere.csv"))


async def test_leaving_the_root_is_refused(fetch: FileFetch) -> None:
    with pytest.raises(ValueError):
        await fetch.fetch(FetchRequest(node_id="../secrets.txt"))


async def test_explicit_json_table_projection_reads_records(fetch: FileFetch) -> None:
    result = await fetch.fetch(FetchRequest(node_id="people.json", limit=2))

    assert [column.name for column in result.columns] == ["id", "name", "city"]
    assert result.rows[0] == ["1", "person-1", None]
    assert result.has_more is True


async def test_every_page_of_a_json_file_has_the_same_columns(
    fetch: FileFetch,
) -> None:
    """The shape comes from the file, not from the page that was asked for."""
    first = await fetch.fetch(FetchRequest(node_id="people.json", limit=2))
    last = await fetch.fetch(FetchRequest(node_id="people.json", limit=2, offset=4))

    assert [column.name for column in first.columns] == [
        column.name for column in last.columns
    ]
    assert last.rows == [["5", "person-5", "Riga"]]
    assert last.has_more is False


async def test_a_json_file_that_does_not_parse_refuses_the_table_projection(
    fetch: FileFetch,
) -> None:
    """A table request is not silently answered with another representation."""
    with pytest.raises(ValueError, match="not valid JSON"):
        await fetch.fetch(FetchRequest(node_id="broken.json"))


async def test_a_json_table_projection_remains_read_only(
    fetch: FileFetch,
) -> None:
    result = await fetch.fetch(FetchRequest(node_id="people.json"))

    assert result.update_supported is False
    assert result.row_handles == [None] * len(result.rows)
