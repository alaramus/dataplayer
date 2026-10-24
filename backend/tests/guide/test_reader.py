"""The guide's pages as the catalog and the screen read them (D183)."""

import re
from pathlib import Path

import pytest

from app.adapters import registry
from app.core.translation import LANGUAGES, Language, in_language
from app.guide import reader

LINK = re.compile(r"\]\(([^)]+)\)")


def test_every_source_type_has_a_page_with_what_you_can_see() -> None:
    for adapter_type in registry.all_types():
        found = reader.page(reader.source_page_key(adapter_type.name))
        assert found is not None, adapter_type.name
        assert reader.bullets(found.markdown, reader.CAN_SEE), adapter_type.name


@pytest.mark.parametrize("language", LANGUAGES)
def test_a_short_list_stays_short(language: Language) -> None:
    """Read in a narrow panel beside the grid of types, one line per item.

    In every language, and measured whole: an item wrapped onto a second line
    of its page is one item, and was once measured by its first line only.
    """

    def long_items() -> list[tuple[str, str]]:
        return [
            (one.key, item)
            for one in reader.pages_in(language).values()
            for heading in (reader.CAN_SEE, reader.CAN_CHANGE)
            for item in reader.bullets(one.markdown, heading)
            if len(item) > 80
        ]

    assert in_language(language, long_items) == []


def test_a_link_between_pages_names_a_page() -> None:
    """The guide window follows these links itself, so each must land."""
    keys = set(reader.pages())
    for one in reader.pages().values():
        for target in LINK.findall(one.markdown):
            assert target.endswith(".md"), (one.key, target)
            assert target.removesuffix(".md") in keys, (one.key, target)


def test_the_bullets_of_one_heading_stop_at_the_next() -> None:
    markdown = "# T\n\n## What you can see\n\n- one\n- two\n  more\n\n## Other\n\n- not\n"

    assert reader.bullets(markdown, reader.CAN_SEE) == ["one", "two more"]
    assert reader.bullets(markdown, reader.CAN_CHANGE) == []


def test_a_bullet_wrapped_onto_more_lines_is_one_item() -> None:
    """The page wraps a long item; the catalog's panel showed only its first line."""
    markdown = (
        "# T\n\n## What you can see\n\n"
        "- What the server does: processes, variables, status, users,\n"
        "  routines, triggers, events and engines\n"
        "- Every matching row\n\n"
        "Text after the list.\n"
    )

    assert reader.bullets(markdown, reader.CAN_SEE) == [
        "What the server does: processes, variables, status, users, routines, triggers, events and engines",
        "Every matching row",
    ]


def test_a_page_is_titled_by_its_first_heading(tmp_path: Path) -> None:
    (tmp_path / "about-this.md").write_text("Intro\n\n# About this\n\nText\n", encoding="utf-8")

    assert reader.read(tmp_path)["about-this"].title == "About this"


def test_a_page_without_a_title_is_refused(tmp_path: Path) -> None:
    (tmp_path / "untitled.md").write_text("No heading here\n", encoding="utf-8")

    with pytest.raises(ValueError, match="no title"):
        reader.read(tmp_path)


def test_a_file_whose_name_is_not_a_key_is_refused(tmp_path: Path) -> None:
    (tmp_path / "Not A Key.md").write_text("# Title\n", encoding="utf-8")

    with pytest.raises(ValueError, match="not a key"):
        reader.read(tmp_path)
