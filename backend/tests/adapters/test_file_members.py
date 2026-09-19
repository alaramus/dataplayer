"""How a node id that may name something inside a file is read (D51)."""

import zipfile
from pathlib import Path

import pytest
from openpyxl import Workbook

from app.adapters.explorer.members import member_id, resolve_node
from app.adapters.file.storage import LocalStorage


@pytest.fixture
def session(tmp_path: Path) -> LocalStorage:
    book = Workbook()
    book.save(tmp_path / "budget.xlsx")
    (tmp_path / "notes.txt").write_text("first\n", encoding="utf-8")
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "q3.csv").write_text("id\n1\n", encoding="utf-8")
    (tmp_path / "trap.xlsx").mkdir()
    (tmp_path / "trap.xlsx" / "1").write_text("id\n1\n", encoding="utf-8")
    with zipfile.ZipFile(tmp_path / "bundle.zip", "w") as bundle:
        bundle.writestr("docs/readme.md", "# Inside\n")
    with zipfile.ZipFile(tmp_path / "reports" / "inner.zip", "w") as inner:
        inner.writestr("notes.txt", "one\n")
    return LocalStorage(tmp_path)


def test_an_id_that_names_a_file_is_a_place(session: LocalStorage) -> None:
    resolved = resolve_node(session, "notes.txt")

    assert resolved.member is None
    assert resolved.is_member is False
    assert resolved.name == "notes.txt"


def test_an_id_that_names_a_directory_is_a_place(session: LocalStorage) -> None:
    assert resolve_node(session, "reports").member is None


def test_the_last_segment_of_a_container_id_is_a_member(
    session: LocalStorage,
) -> None:
    resolved = resolve_node(session, "budget.xlsx/1")

    assert resolved.member == "1"
    assert resolved.name == "budget.xlsx"


def test_an_existing_path_is_never_split(session: LocalStorage) -> None:
    """A directory named like a workbook keeps its ordinary meaning."""
    resolved = resolve_node(session, "trap.xlsx/1")

    assert resolved.member is None
    assert resolved.entry is not None and not resolved.entry.is_directory


def test_a_member_of_something_that_holds_none_is_simply_missing(
    session: LocalStorage,
) -> None:
    resolved = resolve_node(session, "notes.txt/1")

    assert resolved.member is None
    assert resolved.entry is None


def test_everything_after_the_container_is_the_member(session: LocalStorage) -> None:
    """A sheet is one segment and an archive entry is a path, so the resolver
    hands over the whole remainder and the container decides what it may be."""
    resolved = resolve_node(session, "budget.xlsx/1/2")

    assert resolved.member == "1/2"
    assert resolved.name == "budget.xlsx"


def test_an_archive_takes_a_path_as_its_member(session: LocalStorage) -> None:
    resolved = resolve_node(session, "bundle.zip/docs/readme.md")

    assert resolved.member == "docs/readme.md"
    assert resolved.name == "bundle.zip"


def test_the_longest_container_prefix_wins(session: LocalStorage) -> None:
    """An archive inside a folder is found before the folder is."""
    resolved = resolve_node(session, "reports/inner.zip/notes.txt")

    assert resolved.member == "notes.txt"
    assert resolved.name == "inner.zip"


def test_containment_is_judged_before_anything_is_split(
    session: LocalStorage,
) -> None:
    with pytest.raises(ValueError, match="outside the connector root"):
        resolve_node(session, "../budget.xlsx/1")


def test_a_member_id_is_composed_by_the_source() -> None:
    assert member_id("reports/budget.xlsx", "2") == "reports/budget.xlsx/2"
