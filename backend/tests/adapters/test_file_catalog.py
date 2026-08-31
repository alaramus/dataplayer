from pathlib import Path

import pytest

from app.adapters.catalog import DirectoryNode, FileNode
from app.adapters.file.catalog import MAX_ENTRIES, FileCatalog
from app.adapters.file.session import FileSession
from app.adapters.protocol import AdapterError, NodeNotFound


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "q3.csv").write_text("a,b\n1,2\n")
    (tmp_path / "empty").mkdir()
    (tmp_path / "notes.txt").write_text("first\n")
    (tmp_path / "logo.png").write_bytes(b"\x89PNG\r\n")
    (tmp_path / "people.json").write_text('[{"id": 1}]')
    (tmp_path / "events.jsonl").write_text('{"id": 1}\n')
    (tmp_path / "readme.md").write_text("# Title\n")
    return tmp_path


@pytest.fixture
def catalog(root: Path) -> FileCatalog:
    return FileCatalog(FileSession(root))


async def test_directories_come_before_files(catalog: FileCatalog) -> None:
    children = await catalog.list_children(None)

    assert [child.name for child in children] == [
        "empty",
        "reports",
        "events.jsonl",
        "logo.png",
        "notes.txt",
        "people.json",
        "readme.md",
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
    ("name", "representations"),
    [
        ("q3.csv", ["table"]),
        ("people.json", ["json", "table"]),
        ("events.jsonl", ["jsonl", "table"]),
        ("notes.txt", ["text"]),
        ("readme.md", ["markdown", "text"]),
        ("logo.png", ["image"]),
    ],
)
async def test_a_file_says_how_it_can_be_opened_in_preferred_order(
    catalog: FileCatalog, name: str, representations: list[str]
) -> None:
    children = await catalog.list_children("reports" if name == "q3.csv" else None)
    node = next(child for child in children if child.name == name)

    assert isinstance(node, FileNode)
    assert [item.kind for item in node.representations] == representations


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


async def test_path_to_a_nested_file_names_every_directory_above_it(
    catalog: FileCatalog,
) -> None:
    path = await catalog.path_to("reports/q3.csv")

    assert [node.name for node in path] == ["reports", "q3.csv"]
    assert isinstance(path[0], DirectoryNode)
    assert path[0].id == "reports"
    assert isinstance(path[1], FileNode)
    assert path[1].id == "reports/q3.csv"
    assert [item.kind for item in path[1].representations] == ["table"]


async def test_path_to_a_file_in_the_root_is_the_file_alone(
    catalog: FileCatalog,
) -> None:
    """The root is the connector itself and is never a step of the path."""
    path = await catalog.path_to("notes.txt")

    assert [node.name for node in path] == ["notes.txt"]


async def test_path_to_a_directory_ends_with_that_directory(
    catalog: FileCatalog,
) -> None:
    path = await catalog.path_to("reports")

    assert [node.name for node in path] == ["reports"]
    assert isinstance(path[0], DirectoryNode)
    assert path[0].has_children is True


async def test_path_to_something_that_is_not_there_is_not_found(
    catalog: FileCatalog,
) -> None:
    with pytest.raises(NodeNotFound):
        await catalog.path_to("reports/q4.csv")


@pytest.mark.parametrize(
    "node_id", ["../outside", "/etc/passwd", "C:/Windows", "reports/../../outside"]
)
async def test_path_to_a_node_outside_the_root_is_refused(
    catalog: FileCatalog, node_id: str
) -> None:
    """The same containment rule as everything else, not a second one."""
    with pytest.raises(ValueError):
        await catalog.path_to(node_id)
