from pathlib import Path

import pytest
from pydantic import ValidationError

from app.adapters import registry
from app.adapters.actions import SupportsActions
from app.adapters.file.adapter import FileAdapter
from app.adapters.file.options import FileOptions
from app.adapters.protocol import (
    SupportsCatalog,
    SupportsDelete,
    SupportsFetch,
    SupportsInsert,
    SupportsUpdate,
)


def _context(home: Path) -> registry.AdapterContext:
    return registry.AdapterContext(home_dir=home)


def test_the_type_is_registered() -> None:
    adapter_type = registry.get("file")

    assert adapter_type.options_schema is FileOptions


def test_a_file_source_can_browse_and_read() -> None:
    adapter = FileAdapter(FileOptions(), _context(Path("/data/users/someone")))

    assert isinstance(adapter, SupportsCatalog)
    assert isinstance(adapter, SupportsFetch)
    assert isinstance(adapter, SupportsUpdate)
    assert isinstance(adapter, SupportsInsert)
    assert isinstance(adapter, SupportsDelete)


def test_the_default_path_is_the_home_directory(tmp_path: Path) -> None:
    adapter = FileAdapter(FileOptions(), _context(tmp_path))

    assert adapter.root == tmp_path


def test_a_path_option_selects_a_folder_inside_the_home(tmp_path: Path) -> None:
    adapter = FileAdapter(FileOptions(path="/reports/2026"), _context(tmp_path))

    assert adapter.root == tmp_path / "reports" / "2026"


@pytest.mark.parametrize(
    ("typed", "stored"),
    [
        ("", "/"),
        ("/", "/"),
        ("   ", "/"),
        ("reports", "/reports"),
        ("/reports/", "/reports"),
        ("reports/2026", "/reports/2026"),
    ],
)
def test_a_stored_path_always_begins_at_the_root(typed: str, stored: str) -> None:
    """One form in the table, whatever the form sent: the root is "/"."""
    assert FileOptions(path=typed).path == stored


def test_the_default_is_stored_as_the_root() -> None:
    assert FileOptions().path == "/"


@pytest.mark.parametrize(
    ("stored", "root"),
    [("/", "home"), ("/reports", "home/reports"), ("/reports/2026", "home/reports/2026")],
)
def test_a_rooted_path_is_joined_below_the_home(
    tmp_path: Path, stored: str, root: str
) -> None:
    """The leading separator is dropped before joining, not carried into it.

    Joining a segment that starts with one would leave personal storage for
    the file system root.
    """
    home = tmp_path / "home"
    adapter = FileAdapter(FileOptions(path=stored), _context(home))

    assert adapter.root == tmp_path / Path(root)


@pytest.mark.parametrize("path", ["../other-user", "reports/../../etc", "C:/Windows"])
def test_a_path_leaving_the_home_is_rejected_by_the_schema(path: str) -> None:
    """Rejected where the form is validated, so the user sees a field error."""
    with pytest.raises(ValidationError):
        FileOptions(path=path)


async def test_the_adapter_lists_the_home_directory(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("hello")
    adapter = FileAdapter(FileOptions(), _context(tmp_path))

    children = await adapter.list_children(None)

    assert [child.name for child in children] == ["notes.txt"]


async def test_check_connection_reports_the_missing_home(tmp_path: Path) -> None:
    adapter = FileAdapter(FileOptions(path="nowhere"), _context(tmp_path))

    result = await adapter.check_connection()

    assert result.ok is False


def test_a_file_source_can_be_asked_to_change_things() -> None:
    adapter = FileAdapter(FileOptions(), _context(Path("/data/users/someone")))

    assert isinstance(adapter, SupportsActions)
