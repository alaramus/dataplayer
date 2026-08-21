from pathlib import Path

import pytest

from app.adapters.catalog import DirectoryNode, FileNode
from app.adapters.file.catalog import MAX_ENTRIES, FileCatalog
from app.adapters.file.session import FileSession
from app.adapters.protocol import AdapterError


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "q3.csv").write_text("a,b\n1,2\n")
    (tmp_path / "empty").mkdir()
    (tmp_path / "notes.txt").write_text("first\n")
    (tmp_path / "logo.png").write_bytes(b"\x89PNG\r\n")
    return tmp_path


@pytest.fixture
def catalog(root: Path) -> FileCatalog:
    return FileCatalog(FileSession(root))


async def test_directories_come_before_files(catalog: FileCatalog) -> None:
    children = await catalog.list_children(None)

    assert [child.name for child in children] == [
        "empty",
        "reports",
        "logo.png",
        "notes.txt",
    ]


async def test_an_empty_directory_says_it_has_no_children(
    catalog: FileCatalog,
) -> None:
    children = await catalog.list_children(None)
    empty = next(child for child in children if child.name == "empty")

    assert isinstance(empty, DirectoryNode)
    assert empty.has_children is False


async def test_a_directory_with_content_says_so(catalog: FileCatalog) -> None:
    children = await catalog.list_children(None)
    reports = next(child for child in children if child.name == "reports")

    assert reports.has_children is True


async def test_a_file_carries_its_size(catalog: FileCatalog, root: Path) -> None:
    children = await catalog.list_children(None)
    notes = next(child for child in children if child.name == "notes.txt")

    assert isinstance(notes, FileNode)
    assert notes.size_bytes == (root / "notes.txt").stat().st_size


@pytest.mark.parametrize(
    ("name", "content_kind"),
    [("q3.csv", "table"), ("notes.txt", "text"), ("logo.png", "opaque")],
)
async def test_a_file_says_what_can_be_made_of_it(
    catalog: FileCatalog, name: str, content_kind: str
) -> None:
    children = await catalog.list_children("reports" if name == "q3.csv" else None)
    node = next(child for child in children if child.name == name)

    assert isinstance(node, FileNode)
    assert node.content_kind == content_kind


async def test_a_node_id_is_relative_to_the_root(catalog: FileCatalog) -> None:
    """Ids travel back to the client, so they must not name the server."""
    children = await catalog.list_children("reports")

    assert [child.id for child in children] == ["reports/q3.csv"]


async def test_listing_a_file_is_refused(catalog: FileCatalog) -> None:
    with pytest.raises(ValueError):
        await catalog.list_children("notes.txt")


async def test_listing_a_missing_node_is_refused(catalog: FileCatalog) -> None:
    with pytest.raises(ValueError):
        await catalog.list_children("nowhere")


async def test_a_missing_root_is_a_source_failure(tmp_path: Path) -> None:
    """Not a bad request: the connector points at a directory that is gone."""
    catalog = FileCatalog(FileSession(tmp_path / "not-there"))

    with pytest.raises(AdapterError):
        await catalog.list_children(None)


async def test_too_many_entries_fail_instead_of_being_cut_short(
    tmp_path: Path,
) -> None:
    """Silently truncating is the lie the old catalog told."""
    for index in range(MAX_ENTRIES + 1):
        (tmp_path / f"file-{index:05d}.txt").write_text("x")
    catalog = FileCatalog(FileSession(tmp_path))

    with pytest.raises(AdapterError, match="pagination"):
        await catalog.list_children(None)
