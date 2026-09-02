import base64
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from openpyxl import Workbook

from app.adapters.dataset import ParquetDataset, WorksheetDataset
from app.adapters.file import summary as summary_module
from app.adapters.file.session import FileSession
from app.adapters.file.summary import FileSummaries
from app.adapters.protocol import NodeNotFound
from app.adapters.summary import (
    ArchiveContents,
    DelimitedContents,
    DirectoryContents,
    EntryContents,
    ImageContents,
    PdfContents,
    TextContents,
    WorkbookContents,
)

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "notes.txt").write_bytes(b"first\nsecond\nthird\n")
    (tmp_path / "windows.txt").write_bytes(b"first\r\nsecond\r\n")
    (tmp_path / "mixed.txt").write_bytes(b"first\r\nsecond\nthird")
    (tmp_path / "latin.txt").write_bytes(b"caf\xe9 noir\n")
    (tmp_path / "empty.txt").write_bytes(b"")
    # A quoted value holding a line ending: three lines of text, two rows.
    (tmp_path / "people.csv").write_bytes(
        b'name,note\nAnn,"first\nsecond"\nBo,plain\n'
    )
    (tmp_path / "wide.tsv").write_bytes(b"id\tname\tnote\n1\tone\tx\n")
    (tmp_path / "pixel.png").write_bytes(PNG_1X1)
    (tmp_path / "forged.png").write_bytes(b"not an image at all")
    (tmp_path / "program.exe").write_bytes(b"MZ\x00\x00")
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "one.txt").write_text("one\n", encoding="utf-8")
    (tmp_path / "reports" / "two.txt").write_text("two\n", encoding="utf-8")
    (tmp_path / "reports" / "deeper").mkdir()

    pq.write_table(
        pa.table(
            {
                "id": pa.array([1, 2, 3], type=pa.int64()),
                "city": pa.array(["one", "two", "three"]),
            }
        ),
        tmp_path / "cities.parquet",
    )

    book = Workbook()
    revenue = book.active
    assert revenue is not None
    revenue.title = "Revenue"
    revenue.append(["quarter", "amount"])
    revenue.append(["Q1", 820])
    notes = book.create_sheet("Working notes")
    notes.append(["note"])
    notes.sheet_state = "hidden"
    book.save(tmp_path / "budget.xlsx")

    with zipfile.ZipFile(tmp_path / "bundle.zip", "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("readme.md", "# Inside\n" * 100)
        bundle.writestr("docs/notes.txt", "first\nsecond\n")
    (tmp_path / "damaged.zip").write_bytes(b"not an archive")
    return tmp_path


@pytest.fixture
def summaries(root: Path) -> FileSummaries:
    return FileSummaries(FileSession(root))


async def test_a_text_file_states_its_facts_and_its_lines(
    summaries: FileSummaries,
) -> None:
    summary = await summaries.node_summary("notes.txt")

    assert summary.kind == "file"
    assert summary.name == "notes.txt"
    assert summary.size_bytes == 19
    assert summary.modified_at is not None
    assert summary.modified_at.tzinfo == UTC
    assert summary.permissions is not None
    assert summary.permissions.startswith("-")
    # What it may be opened as is the catalog's own ordered answer (D47).
    assert [item.kind for item in summary.representations] == ["text"]

    contents = summary.contents
    assert isinstance(contents, TextContents)
    assert contents.encoding == "utf-8"
    assert contents.lines == 3
    assert contents.line_endings == "lf"
    assert contents.longest_line_bytes == 6
    assert contents.not_counted is None


async def test_line_endings_are_counted_rather_than_assumed(
    summaries: FileSummaries,
) -> None:
    windows = await summaries.node_summary("windows.txt")
    mixed = await summaries.node_summary("mixed.txt")

    assert isinstance(windows.contents, TextContents)
    assert windows.contents.line_endings == "crlf"
    assert windows.contents.lines == 2

    assert isinstance(mixed.contents, TextContents)
    assert mixed.contents.line_endings == "mixed"
    # Two terminators and a last line nothing terminates.
    assert mixed.contents.lines == 3


async def test_an_empty_file_has_no_lines_and_no_endings(
    summaries: FileSummaries,
) -> None:
    summary = await summaries.node_summary("empty.txt")

    assert isinstance(summary.contents, TextContents)
    assert summary.contents.lines == 0
    assert summary.contents.line_endings == "none"
    assert summary.contents.encoding == "utf-8"


async def test_bytes_that_are_not_utf_8_say_so(summaries: FileSummaries) -> None:
    """The alternative is decoding with replacements and calling it text."""
    summary = await summaries.node_summary("latin.txt")

    assert isinstance(summary.contents, TextContents)
    assert summary.contents.encoding == "not-utf-8"
    # Still counted: a line ending is a byte whatever the encoding is.
    assert summary.contents.lines == 1


async def test_a_file_past_the_ceiling_is_not_counted(
    summaries: FileSummaries, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stated ceiling, rather than a wait nobody asked for."""
    monkeypatch.setattr(summary_module, "MAX_COUNTED_BYTES", 8)

    summary = await summaries.node_summary("notes.txt")

    assert isinstance(summary.contents, TextContents)
    assert summary.contents.lines is None
    assert summary.contents.longest_line_bytes is None
    assert summary.contents.not_counted is not None
    # The facts every file has are still there.
    assert summary.size_bytes == 19


async def test_a_delimited_file_is_counted_by_its_parser(
    summaries: FileSummaries,
) -> None:
    """A line ending inside quotes is not the end of a row."""
    summary = await summaries.node_summary("people.csv")

    contents = summary.contents
    assert isinstance(contents, DelimitedContents)
    assert contents.delimiter == "comma"
    assert contents.columns == 2
    assert contents.rows == 2
    assert contents.encoding == "utf-8"


async def test_a_tab_separated_file_names_its_delimiter(
    summaries: FileSummaries,
) -> None:
    summary = await summaries.node_summary("wide.tsv")

    assert isinstance(summary.contents, DelimitedContents)
    assert summary.contents.delimiter == "tab"
    assert summary.contents.columns == 3
    assert summary.contents.rows == 1


async def test_a_columnar_file_states_what_its_footer_states(
    summaries: FileSummaries,
) -> None:
    """The same model the relation view shows: one computation, one place."""
    summary = await summaries.node_summary("cities.parquet")

    contents = summary.contents
    assert isinstance(contents, ParquetDataset)
    assert contents.rows == 3
    assert contents.columns == 2


async def test_a_workbook_counts_its_sheets(summaries: FileSummaries) -> None:
    summary = await summaries.node_summary("budget.xlsx")

    contents = summary.contents
    assert isinstance(contents, WorkbookContents)
    assert contents.sheets == 2
    assert contents.hidden_sheets == 1
    # A workbook is not one table, so it opens nothing itself (D51).
    assert summary.representations == []


async def test_one_sheet_is_described_as_the_member_it_is(
    summaries: FileSummaries,
) -> None:
    summary = await summaries.node_summary("budget.xlsx/1")

    assert summary.kind == "dataset"
    assert summary.name == "Revenue"
    # No bytes and no times of its own: they belong to the workbook.
    assert summary.size_bytes is None
    assert summary.modified_at is None
    contents = summary.contents
    assert isinstance(contents, WorksheetDataset)
    assert contents.sheet_position == 1
    assert contents.sheet_count == 2
    assert contents.workbook == "budget.xlsx"


async def test_an_archive_is_counted_from_its_central_directory(
    summaries: FileSummaries,
) -> None:
    summary = await summaries.node_summary("bundle.zip")

    contents = summary.contents
    assert isinstance(contents, ArchiveContents)
    assert contents.files == 2
    assert contents.entries == 2
    assert contents.encrypted == 0
    assert contents.links == 0
    # Deflated: what it expands to is larger than what it takes.
    assert contents.size_bytes > contents.compressed_bytes


async def test_an_entry_states_what_the_archive_says_about_it(
    summaries: FileSummaries,
) -> None:
    summary = await summaries.node_summary("bundle.zip/docs/notes.txt")

    assert summary.kind == "entry"
    assert summary.name == "notes.txt"
    assert summary.size_bytes == 13
    contents = summary.contents
    assert isinstance(contents, EntryContents)
    assert contents.compressed_bytes is not None
    assert contents.encrypted is False
    assert [item.kind for item in summary.representations] == ["text"]


async def test_an_image_states_its_size_without_decoding_it(
    summaries: FileSummaries,
) -> None:
    summary = await summaries.node_summary("pixel.png")

    contents = summary.contents
    assert isinstance(contents, ImageContents)
    assert contents.media_type == "image/png"
    assert (contents.width, contents.height) == (1, 1)


async def test_a_misleading_suffix_is_named_rather_than_failing(
    summaries: FileSummaries,
) -> None:
    """D47's known deviation reaching the reader instead of an error page."""
    image = await summaries.node_summary("forged.png")
    archive = await summaries.node_summary("damaged.zip")

    assert image.contents is None
    assert image.notice is not None
    assert archive.contents is None
    assert archive.notice is not None
    # The facts every file has survive a format that could not be read.
    assert image.size_bytes == 19


async def test_an_opaque_file_says_only_what_every_file_says(
    summaries: FileSummaries,
) -> None:
    summary = await summaries.node_summary("program.exe")

    assert summary.contents is None
    assert summary.notice is None
    assert summary.representations == []
    assert summary.size_bytes == 4


async def test_a_directory_counts_one_level_of_itself(
    summaries: FileSummaries,
) -> None:
    summary = await summaries.node_summary("reports")

    assert summary.kind == "directory"
    contents = summary.contents
    assert isinstance(contents, DirectoryContents)
    assert contents.entries == 3
    assert contents.files == 2
    assert contents.directories == 1
    assert contents.not_counted is None


async def test_a_directory_past_the_listing_ceiling_is_not_counted(
    summaries: FileSummaries, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The number that refuses to list it is the number that refuses to count it."""
    monkeypatch.setattr(summary_module, "MAX_ENTRIES", 1)

    summary = await summaries.node_summary("reports")

    contents = summary.contents
    assert isinstance(contents, DirectoryContents)
    assert contents.entries is None
    assert contents.not_counted is not None


async def test_a_node_that_is_not_there_is_not_found(
    summaries: FileSummaries,
) -> None:
    with pytest.raises(NodeNotFound):
        await summaries.node_summary("nowhere.txt")


async def test_a_sheet_that_is_not_there_is_not_found(
    summaries: FileSummaries,
) -> None:
    with pytest.raises(NodeNotFound):
        await summaries.node_summary("budget.xlsx/9")


@pytest.mark.parametrize(
    "node_id",
    ["../secret.txt", "/etc/passwd", "C:/Windows/win.ini", "reports/../../away.txt"],
)
async def test_a_path_that_leaves_the_root_is_refused(
    summaries: FileSummaries, node_id: str
) -> None:
    """The one containment rule, judged before anything is opened (D8)."""
    with pytest.raises(ValueError):
        await summaries.node_summary(node_id)


async def test_a_pdf_states_the_version_it_declares(
    summaries: FileSummaries, root: Path
) -> None:
    (root / "manual.pdf").write_bytes(b"%PDF-1.7\n1 0 obj\n")

    summary = await summaries.node_summary("manual.pdf")

    contents = summary.contents
    assert isinstance(contents, PdfContents)
    assert contents.version == "1.7"


async def test_a_symbolic_link_out_of_the_root_is_refused(
    summaries: FileSummaries, root: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    outside = tmp_path_factory.mktemp("outside")
    (outside / "secret.txt").write_text("not yours\n", encoding="utf-8")
    try:
        (root / "escape.txt").symlink_to(outside / "secret.txt")
    except OSError:  # pragma: no cover - Windows without the privilege
        pytest.skip("This platform will not create a symbolic link here")

    with pytest.raises(ValueError):
        await summaries.node_summary("escape.txt")


async def test_the_creation_time_is_absent_where_the_platform_states_none(
    summaries: FileSummaries, root: Path
) -> None:
    """Filling it with the inode change time would be a plausible lie."""
    summary = await summaries.node_summary("notes.txt")

    assert summary.accessed_at is not None
    stated = hasattr((root / "notes.txt").stat(), "st_birthtime")
    assert (summary.created_at is not None) == stated


async def test_a_stale_date_inside_an_archive_does_not_fail_the_summary(
    summaries: FileSummaries, root: Path
) -> None:
    with zipfile.ZipFile(root / "dated.zip", "w") as dated:
        info = zipfile.ZipInfo("old.txt", date_time=(1980, 1, 1, 0, 0, 0))
        dated.writestr(info, "old\n")

    summary = await summaries.node_summary("dated.zip/old.txt")

    assert summary.modified_at == datetime(1980, 1, 1, tzinfo=UTC)
