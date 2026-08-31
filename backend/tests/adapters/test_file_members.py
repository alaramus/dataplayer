"""How a node id that may name something inside a file is read (D51)."""

from pathlib import Path

import pytest
from openpyxl import Workbook

from app.adapters.file.members import member_id, resolve_node
from app.adapters.file.session import FileSession


@pytest.fixture
def session(tmp_path: Path) -> FileSession:
    book = Workbook()
    book.save(tmp_path / "budget.xlsx")
    (tmp_path / "notes.txt").write_text("first\n", encoding="utf-8")
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "q3.csv").write_text("id\n1\n", encoding="utf-8")
    (tmp_path / "trap.xlsx").mkdir()
    (tmp_path / "trap.xlsx" / "1").write_text("id\n1\n", encoding="utf-8")
    return FileSession(tmp_path)


def test_an_id_that_names_a_file_is_a_path(session: FileSession) -> None:
    resolved = resolve_node(session, "notes.txt")

    assert resolved.member is None
    assert resolved.is_member is False
    assert resolved.path.name == "notes.txt"


def test_an_id_that_names_a_directory_is_a_path(session: FileSession) -> None:
    assert resolve_node(session, "reports").member is None


def test_the_last_segment_of_a_container_id_is_a_member(
    session: FileSession,
) -> None:
    resolved = resolve_node(session, "budget.xlsx/1")

    assert resolved.member == "1"
    assert resolved.path.name == "budget.xlsx"


def test_an_existing_path_is_never_split(session: FileSession) -> None:
    """A directory named like a workbook keeps its ordinary meaning."""
    resolved = resolve_node(session, "trap.xlsx/1")

    assert resolved.member is None
    assert resolved.path.is_file()


def test_a_member_of_something_that_holds_none_is_simply_missing(
    session: FileSession,
) -> None:
    resolved = resolve_node(session, "notes.txt/1")

    assert resolved.member is None
    assert not resolved.path.exists()


def test_only_one_segment_is_read_as_a_member(session: FileSession) -> None:
    resolved = resolve_node(session, "budget.xlsx/1/2")

    assert resolved.member is None
    assert not resolved.path.exists()


def test_containment_is_judged_before_anything_is_split(
    session: FileSession,
) -> None:
    with pytest.raises(ValueError, match="outside the connector root"):
        resolve_node(session, "../budget.xlsx/1")


def test_a_member_id_is_composed_by_the_source() -> None:
    assert member_id("reports/budget.xlsx", "2") == "reports/budget.xlsx/2"
