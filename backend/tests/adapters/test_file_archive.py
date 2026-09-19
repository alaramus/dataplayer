"""Walking into an archive, and what an entry does and does not admit (D53)."""

import base64
import zipfile
from pathlib import Path

import pytest

from app.adapters.catalog import EntryNode
from app.adapters.content import ContentRequest, EditorContentRequest
from app.adapters.explorer.actions import ExplorerActions
from app.adapters.explorer.archive import (
    MAX_ENTRIES,
    MAX_ENTRY_BYTES,
    NotAnArchive,
    UnsafeArchive,
)
from app.adapters.explorer.catalog import ExplorerCatalog
from app.adapters.explorer.content import ExplorerContent
from app.adapters.explorer.fetch import ExplorerFetch
from app.adapters.fetch import FetchRequest
from app.adapters.file.storage import LocalStorage
from app.adapters.protocol import NodeNotFound
from tests.utils.media import pdf_bytes

# One real 1x1 PNG, for the reason the seed script gives: the viewer verifies
# the bytes, so invented ones would test the refusal instead of the viewer.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _bundle(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("readme.md", "# Inside an archive\n\nA document.\n")
        archive.writestr("docs/notes.txt", "first\nsecond\nthird\n")
        archive.writestr("docs/cities.csv", "id,name\n1,one\n2,two\n")
        archive.writestr("docs/pixel.png", PNG)
        archive.writestr("docs/report.pdf", pdf_bytes())
        archive.writestr("empty/", b"")
        link = zipfile.ZipInfo("docs/elsewhere")
        # The mode bits a unix zip uses to say "this entry is a symbolic link".
        link.external_attr = (0o120777 << 16) | 0o20
        archive.writestr(link, "../../etc/passwd")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    _bundle(tmp_path / "bundle.zip")
    (tmp_path / "not-really.zip").write_bytes(b"not an archive at all")
    with zipfile.ZipFile(tmp_path / "escaping.zip", "w") as escaping:
        escaping.writestr("../outside.txt", "somewhere else\n")
    # A directory named like an archive, holding a file with an entry's shape.
    (tmp_path / "trap.zip").mkdir()
    (tmp_path / "trap.zip" / "readme.md").write_text("# On disk\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def catalog(root: Path) -> ExplorerCatalog:
    return ExplorerCatalog(LocalStorage(root))


@pytest.fixture
def content(root: Path) -> ExplorerContent:
    return ExplorerContent(LocalStorage(root))


@pytest.fixture
def fetch(root: Path) -> ExplorerFetch:
    return ExplorerFetch(LocalStorage(root))


async def test_an_archive_is_a_file_with_children_and_no_viewer(
    catalog: ExplorerCatalog,
) -> None:
    nodes = {node.name: node for node in await catalog.list_children(None)}

    bundle = nodes["bundle.zip"]
    assert bundle.kind == "file"
    assert bundle.has_children is True
    assert bundle.representations == []


async def test_the_first_level_holds_folders_and_files(
    catalog: ExplorerCatalog,
) -> None:
    nodes = await catalog.list_children("bundle.zip")

    assert [node.name for node in nodes] == ["docs", "empty", "readme.md"]
    assert all(node.kind == "entry" for node in nodes)
    assert [node.has_children for node in nodes] == [True, True, False]
    assert nodes[0].id == "bundle.zip/docs"


async def test_a_folder_inside_an_archive_is_walked_into(
    catalog: ExplorerCatalog,
) -> None:
    """`docs` is never an entry of its own here; its contents imply it."""
    nodes = await catalog.list_children("bundle.zip/docs")

    assert [node.name for node in nodes] == [
        "cities.csv",
        "elsewhere",
        "notes.txt",
        "pixel.png",
        "report.pdf",
    ]
    assert [node.id for node in nodes][0] == "bundle.zip/docs/cities.csv"


async def test_an_entry_offers_the_viewers_an_expansion_can_feed(
    catalog: ExplorerCatalog,
) -> None:
    nodes = {node.name: node for node in await catalog.list_children("bundle.zip/docs")}

    assert [item.kind for item in nodes["notes.txt"].representations] == ["text"]
    assert [item.kind for item in nodes["cities.csv"].representations] == ["table"]
    assert [item.kind for item in nodes["pixel.png"].representations] == ["image"]
    # A PDF is streamed by range, which an expansion cannot answer (D53).
    assert nodes["report.pdf"].representations == []


async def test_an_entry_states_what_the_directory_says_about_it(
    catalog: ExplorerCatalog,
) -> None:
    nodes = {node.name: node for node in await catalog.list_children("bundle.zip")}

    readme = nodes["readme.md"]
    assert isinstance(readme, EntryNode)
    assert readme.size_bytes == len("# Inside an archive\n\nA document.\n")
    assert readme.compressed_bytes is not None
    assert readme.modified_at is not None


async def test_a_link_inside_an_archive_is_listed_and_has_no_viewer(
    catalog: ExplorerCatalog,
) -> None:
    nodes = {node.name: node for node in await catalog.list_children("bundle.zip/docs")}

    link = nodes["elsewhere"]
    assert isinstance(link, EntryNode)
    assert link.is_link is True
    assert link.representations == []


async def test_a_link_inside_an_archive_is_never_read(content: ExplorerContent) -> None:
    with pytest.raises(ValueError):
        await content.read_content(
            ContentRequest(
                node_id="bundle.zip/docs/elsewhere", representation="text"
            )
        )


async def test_an_archive_whose_entry_leaves_it_is_refused_whole(
    catalog: ExplorerCatalog,
) -> None:
    """Listing the rest would be a second containment rule (D53)."""
    with pytest.raises(UnsafeArchive, match="leaves it"):
        await catalog.list_children("escaping.zip")


async def test_bytes_that_are_not_an_archive_are_refused(
    catalog: ExplorerCatalog,
) -> None:
    with pytest.raises(NotAnArchive, match="not an archive"):
        await catalog.list_children("not-really.zip")


async def test_an_archive_with_too_many_entries_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "many.zip"
    with zipfile.ZipFile(path, "w") as archive:
        for index in range(MAX_ENTRIES + 1):
            archive.writestr(f"f{index}.txt", "x")
    catalog = ExplorerCatalog(LocalStorage(tmp_path))

    with pytest.raises(ValueError, match=f"more than {MAX_ENTRIES} entries"):
        await catalog.list_children("many.zip")


async def test_a_directory_named_like_an_archive_keeps_its_meaning(
    catalog: ExplorerCatalog, content: ExplorerContent
) -> None:
    nodes = await catalog.list_children("trap.zip")

    assert [node.kind for node in nodes] == ["file"]
    result = await content.read_content(
        ContentRequest(node_id="trap.zip/readme.md", representation="markdown")
    )
    assert result.kind == "markdown"


async def test_a_document_inside_an_archive_is_read_by_its_ordinary_viewer(
    content: ExplorerContent,
) -> None:
    result = await content.read_content(
        ContentRequest(node_id="bundle.zip/readme.md", representation="markdown")
    )

    assert result.kind == "markdown"
    assert "Inside an archive" in result.text


async def test_text_inside_an_archive_is_read(content: ExplorerContent) -> None:
    result = await content.read_content(
        ContentRequest(node_id="bundle.zip/docs/notes.txt", representation="text")
    )

    assert result.kind == "text"
    assert result.text.startswith("first")


async def test_an_image_inside_an_archive_is_verified(content: ExplorerContent) -> None:
    preview = await content.preview_content(
        ContentRequest(node_id="bundle.zip/docs/pixel.png", representation="image")
    )

    assert preview.media_type == "image/png"
    assert preview.filename == "pixel.png"
    assert (preview.width, preview.height) == (1, 1)


async def test_a_table_inside_an_archive_is_paged(fetch: ExplorerFetch) -> None:
    result = await fetch.fetch(
        FetchRequest(node_id="bundle.zip/docs/cities.csv", limit=1)
    )

    assert [column.name for column in result.columns] == ["id", "name"]
    assert result.rows == [["1", "one"]]
    assert result.has_more is True


async def test_a_representation_the_entry_does_not_offer_is_refused(
    content: ExplorerContent,
) -> None:
    with pytest.raises(ValueError, match="does not offer"):
        await content.read_content(
            ContentRequest(node_id="bundle.zip/docs/report.pdf", representation="pdf")
        )


async def test_an_entry_is_shown_in_the_editor_and_never_saved(
    content: ExplorerContent,
) -> None:
    """Refusing to open it would take the reading away with the writing."""
    document = await content.read_editor_content(
        EditorContentRequest(node_id="bundle.zip/docs/notes.txt")
    )

    assert document.text.startswith("first")
    assert document.filename == "notes.txt"
    assert document.writable is False
    assert document.version is None
    assert document.reason is not None


async def test_an_entry_keeps_its_own_language_in_the_editor(
    tmp_path: Path,
) -> None:
    with zipfile.ZipFile(tmp_path / "bundle.zip", "w") as archive:
        archive.writestr("config.json", '{"a": 1}')
    content = ExplorerContent(LocalStorage(tmp_path))

    document = await content.read_editor_content(
        EditorContentRequest(node_id="bundle.zip/config.json")
    )

    assert document.language_hint == "json"
    assert document.validation == "json"


async def test_an_entry_cannot_be_written_or_streamed(content: ExplorerContent) -> None:
    from app.adapters.content import UpdateContentRequest

    with pytest.raises(ValueError, match="cannot be written"):
        await content.update_content(
            UpdateContentRequest(
                node_id="bundle.zip/docs/notes.txt", text="new", version="whatever"
            )
        )
    with pytest.raises(ValueError, match="cannot be streamed"):
        await content.open_content_stream(
            ContentRequest(node_id="bundle.zip/docs/report.pdf", representation="pdf")
        )


async def test_an_entry_larger_than_the_ceiling_is_refused_before_it_is_read(
    tmp_path: Path,
) -> None:
    """The declared size is checked first, so nothing is inflated to find out."""
    path = tmp_path / "big.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("huge.txt", b"\0" * (MAX_ENTRY_BYTES + 1))
    content = ExplorerContent(LocalStorage(tmp_path))

    with pytest.raises(ValueError, match="larger than"):
        await content.read_content(
            ContentRequest(node_id="big.zip/huge.txt", representation="text")
        )


async def test_an_entry_that_holds_more_than_it_declares_is_refused(
    tmp_path: Path,
) -> None:
    """The declaration bounds the read, and the checksum catches the lie.

    `zipfile` stops at the size the central directory states, so an entry that
    holds more than it admits to fails its own CRC there. What matters is that
    the failure is named as a damaged entry rather than as a file that is not
    an archive, and that nothing is left behind.
    """
    from app.adapters.explorer import archive as archive_module

    path = tmp_path / "understated.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("data.txt", b"x" * 4096)
    _shrink_declared_size(path, 16)

    with pytest.raises(ValueError, match="damaged"):
        archive_module.extract(path, "data.txt")


async def test_the_path_to_an_entry_walks_through_its_archive(
    catalog: ExplorerCatalog,
) -> None:
    path = await catalog.path_to("bundle.zip/docs/notes.txt")

    assert [(node.kind, node.name) for node in path] == [
        ("file", "bundle.zip"),
        ("entry", "docs"),
        ("entry", "notes.txt"),
    ]


async def test_the_path_to_an_entry_that_is_not_there_is_not_found(
    catalog: ExplorerCatalog,
) -> None:
    with pytest.raises(NodeNotFound):
        await catalog.path_to("bundle.zip/docs/missing.txt")


async def test_an_entry_admits_download_and_nothing_else(root: Path) -> None:
    actions = ExplorerActions(LocalStorage(root))

    offered = await actions.available("bundle.zip/docs/notes.txt")

    assert [action.name for action in offered] == ["download"]


async def test_one_entry_is_downloaded_on_its_own(root: Path) -> None:
    actions = ExplorerActions(LocalStorage(root))
    download = actions.action("download")

    result = await download.download(["bundle.zip/docs/notes.txt"], {})  # type: ignore[attr-defined]

    assert result.metadata.filename == "notes.txt"
    body = b"".join([chunk async for chunk in result.body])
    assert body == b"first\nsecond\nthird\n"


async def test_a_folder_inside_an_archive_is_not_downloaded(root: Path) -> None:
    from app.adapters.actions import ActionRefused

    actions = ExplorerActions(LocalStorage(root))
    download = actions.action("download")

    with pytest.raises((ActionRefused, ValueError)):
        await download.download(["bundle.zip/docs"], {})  # type: ignore[attr-defined]


def _shrink_declared_size(path: Path, declared: int) -> None:
    """Claim a smaller uncompressed size than the entry really has.

    The counterpart of the workbook test: there a declaration was inflated to
    trip the ceiling, here it is shrunk so the ceiling can only be found by
    counting the bytes as they arrive.
    """
    raw = bytearray(path.read_bytes())
    # From the end: the signature of a central directory header is four bytes
    # that a compressed payload may hold too.
    start = raw.rindex(b"PK\x01\x02")
    raw[start + 24 : start + 28] = declared.to_bytes(4, "little")
    path.write_bytes(bytes(raw))
