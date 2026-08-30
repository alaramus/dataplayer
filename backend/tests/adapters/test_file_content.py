from pathlib import Path

import pytest

from app.adapters.content import (
    ContentRequest,
    JsonArray,
    JsonContent,
    JsonLinesContent,
    JsonObject,
    JsonScalar,
    TextContent,
)
from app.adapters.file.content import (
    MAX_JSON_BYTES,
    MAX_JSON_LINE_BYTES,
    MAX_JSON_LINES_PAGE_BYTES,
    MAX_TEXT_BYTES,
    FileContent,
)
from app.adapters.file.session import FileSession


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "document.json").write_text(
        '{"id": 10000000000000001, "active": true, "tags": ["one"]}',
        encoding="utf-8",
    )
    (tmp_path / "broken.json").write_text('{"id" 1}', encoding="utf-8")
    (tmp_path / "events.jsonl").write_text(
        '{"id": 1}\nnot json\n\n{"id": 3}\n', encoding="utf-8"
    )
    (tmp_path / "notes.txt").write_text("first\nsecond\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def content(root: Path) -> FileContent:
    return FileContent(FileSession(root))


async def test_json_is_a_nested_value_instead_of_rows(content: FileContent) -> None:
    result = await content.read_content(
        ContentRequest(node_id="document.json", representation="json")
    )

    assert isinstance(result, JsonContent)
    assert isinstance(result.value, JsonObject)
    fields = {entry.name: entry.value for entry in result.value.entries}
    assert isinstance(fields["id"], JsonScalar)
    assert fields["id"].kind == "number"
    assert fields["id"].value == "10000000000000001"
    assert isinstance(fields["tags"], JsonArray)


async def test_broken_json_stays_in_the_json_viewer_as_source_text(
    content: FileContent,
) -> None:
    result = await content.read_content(
        ContentRequest(node_id="broken.json", representation="json")
    )

    assert isinstance(result, JsonContent)
    assert result.value is None
    assert result.source_text == '{"id" 1}'
    assert result.notice is not None
    assert "line 1" in result.notice


async def test_large_json_stays_in_its_viewer_as_a_bounded_source_preview(
    content: FileContent, root: Path
) -> None:
    (root / "large.json").write_text(
        '"' + ("x" * MAX_JSON_BYTES) + '"', encoding="utf-8"
    )

    result = await content.read_content(
        ContentRequest(node_id="large.json", representation="json")
    )

    assert isinstance(result, JsonContent)
    assert result.value is None
    assert result.truncated is True
    assert result.notice is not None
    assert "larger than" in result.notice


async def test_json_lines_are_independent_values_with_physical_line_numbers(
    content: FileContent,
) -> None:
    result = await content.read_content(
        ContentRequest(node_id="events.jsonl", representation="jsonl")
    )

    assert isinstance(result, JsonLinesContent)
    assert [item.line_number for item in result.items] == [1, 2, 4]
    assert result.items[0].value is not None
    assert result.items[1].value is None
    assert result.items[1].source_text == "not json"
    assert result.items[1].notice is not None
    assert result.items[2].value is not None


async def test_json_lines_page_by_records_not_blank_physical_lines(
    content: FileContent,
) -> None:
    first = await content.read_content(
        ContentRequest(
            node_id="events.jsonl", representation="jsonl", limit=2, offset=0
        )
    )
    last = await content.read_content(
        ContentRequest(
            node_id="events.jsonl", representation="jsonl", limit=2, offset=2
        )
    )

    assert isinstance(first, JsonLinesContent)
    assert first.has_more is True
    assert isinstance(last, JsonLinesContent)
    assert [item.line_number for item in last.items] == [4]
    assert last.has_more is False


async def test_one_oversized_json_line_does_not_hide_the_next_value(
    content: FileContent, root: Path
) -> None:
    (root / "large-line.jsonl").write_text(
        ("x" * (MAX_JSON_LINE_BYTES + 1)) + '\n{"id": 2}\n', encoding="utf-8"
    )

    result = await content.read_content(
        ContentRequest(node_id="large-line.jsonl", representation="jsonl")
    )

    assert isinstance(result, JsonLinesContent)
    assert [item.line_number for item in result.items] == [1, 2]
    assert result.items[0].truncated is True
    assert result.items[0].notice is not None
    assert result.items[1].value is not None


async def test_json_lines_have_a_byte_bound_as_well_as_a_record_bound(
    content: FileContent, root: Path
) -> None:
    filler = "x" * (MAX_JSON_LINE_BYTES - 100)
    assert len(filler.encode()) * 5 > MAX_JSON_LINES_PAGE_BYTES
    (root / "wide.jsonl").write_text(
        "".join(f'{{"value":"{filler}"}}\n' for _ in range(5)), encoding="utf-8"
    )

    result = await content.read_content(
        ContentRequest(node_id="wide.jsonl", representation="jsonl", limit=100)
    )

    assert isinstance(result, JsonLinesContent)
    assert len(result.items) < 5
    assert result.has_more is True


async def test_text_has_its_own_bounded_representation(
    content: FileContent,
) -> None:
    result = await content.read_content(
        ContentRequest(node_id="notes.txt", representation="text")
    )

    assert isinstance(result, TextContent)
    assert result.text == "first\nsecond\n"
    assert result.truncated is False


async def test_a_text_preview_is_cut_without_claiming_to_be_the_whole_file(
    content: FileContent, root: Path
) -> None:
    (root / "large.txt").write_text("x" * (MAX_TEXT_BYTES + 1), encoding="utf-8")

    result = await content.read_content(
        ContentRequest(node_id="large.txt", representation="text")
    )

    assert isinstance(result, TextContent)
    assert len(result.text) == MAX_TEXT_BYTES
    assert result.truncated is True


async def test_binary_bytes_disguised_as_text_are_refused(
    content: FileContent, root: Path
) -> None:
    (root / "binary.txt").write_bytes(b"text\x00binary")

    with pytest.raises(ValueError, match="binary"):
        await content.read_content(
            ContentRequest(node_id="binary.txt", representation="text")
        )


async def test_a_representation_the_node_did_not_offer_is_refused(
    content: FileContent,
) -> None:
    with pytest.raises(ValueError, match="does not offer"):
        await content.read_content(
            ContentRequest(node_id="notes.txt", representation="json")
        )
