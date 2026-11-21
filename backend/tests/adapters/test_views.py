"""A view of a document is a closed set of blocks and values (D419, D420)."""

import pytest
from pydantic import TypeAdapter, ValidationError

from app.adapters.content import ContentResult
from app.adapters.views import (
    MAX_BLOCKS,
    MAX_ROWS,
    MAX_TEXT,
    DocumentView,
    NoticeBlock,
    SectionBlock,
    TableBlock,
    ViewHeader,
    chips,
    code,
    table,
    text,
)

CONTENT: TypeAdapter[object] = TypeAdapter(ContentResult)


def _view(*blocks: dict[str, object]) -> dict[str, object]:
    return {"kind": "view", "header": {"title": "web"}, "blocks": list(blocks)}


def test_a_view_is_a_member_of_the_content_union() -> None:
    read = CONTENT.validate_python(
        _view(
            {
                "kind": "section",
                "title": "Overview",
                "blocks": [
                    {
                        "kind": "fields",
                        "fields": [
                            {"label": "Size", "value": {"kind": "bytes", "value": 1024}},
                            {"label": "Image", "value": {"kind": "link", "text": "alpine", "node_id": "image:x"}},
                            {"label": "User", "value": {"kind": "empty"}},
                        ],
                    }
                ],
            }
        )
    )
    assert isinstance(read, DocumentView)


def test_an_unknown_block_is_refused() -> None:
    with pytest.raises(ValidationError):
        CONTENT.validate_python(_view({"kind": "chart", "series": []}))


def test_an_unknown_value_kind_is_refused() -> None:
    with pytest.raises(ValidationError):
        CONTENT.validate_python(
            _view({"kind": "fields", "fields": [{"label": "When", "value": {"kind": "calendar", "value": 1}}]})
        )


def test_a_field_unknown_to_a_block_is_refused() -> None:
    with pytest.raises(ValidationError):
        CONTENT.validate_python(_view({"kind": "notice", "text": "Restarted", "width": 300}))


def test_sections_do_not_nest() -> None:
    inner = {"kind": "section", "title": "Inner", "blocks": []}
    with pytest.raises(ValidationError):
        CONTENT.validate_python(_view({"kind": "section", "title": "Outer", "blocks": [inner]}))


def test_a_tone_is_one_of_a_closed_set() -> None:
    with pytest.raises(ValidationError):
        NoticeBlock.model_validate({"text": "Hot", "tone": "red"})


def test_a_table_row_has_one_value_per_column() -> None:
    with pytest.raises(ValidationError):
        TableBlock(columns=["Port", "Host"], rows=[[text("80/tcp")]])


def test_a_view_holds_at_most_its_ceiling_of_blocks() -> None:
    notice = NoticeBlock(text="x")
    sections = [SectionBlock(title="s", blocks=[notice] * 9) for _ in range(MAX_BLOCKS // 10 + 1)]
    with pytest.raises(ValidationError):
        DocumentView(header=ViewHeader(title="t"), blocks=list(sections))


def test_a_long_table_says_how_many_rows_it_left_out() -> None:
    cut = table(["n"], [[text(str(n))] for n in range(MAX_ROWS + 7)])
    assert len(cut.rows) == MAX_ROWS
    assert cut.omitted == 7


def test_long_text_is_cut_and_says_so() -> None:
    value = code("x" * (MAX_TEXT + 1))
    assert len(value.text) == MAX_TEXT
    assert value.truncated
    assert not text("short").truncated


def test_chips_say_how_many_they_left_out() -> None:
    assert chips(["a"] * (MAX_ROWS + 2)).omitted == 2
