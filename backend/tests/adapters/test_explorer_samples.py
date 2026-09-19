"""The sample files, and a source made of files filled with them (D90, D153)."""

from pathlib import Path

from app.adapters.explorer.samples import SAMPLE_ROWS, write_samples
from app.adapters.file.adapter import FileAdapter
from app.adapters.file.options import FileOptions
from app.adapters.registry import AdapterContext


def test_samples_cover_the_native_file_viewers(tmp_path: Path) -> None:
    """Tabular, plain-text and image files all have examples."""
    write_samples(tmp_path)

    names = {path.name for path in tmp_path.rglob("*")}
    assert {"sample.csv", "sample.tsv", "notes.txt", "logo.png", "reports"} <= names


def test_a_sample_file_pairs_with_the_demonstration_schema(tmp_path: Path) -> None:
    """A declared reference needs two ends that match (D106).

    The file's slugs are the ones `postgres_complex_data.sql` inserts, so
    drawing a reference between them and following it lands on a row rather
    than on an empty page.
    """
    write_samples(tmp_path)

    for name in ("accounts.csv", "renewals.csv"):
        rows = (tmp_path / name).read_text(encoding="utf-8").splitlines()
        assert rows[0].split(",")[0] == "slug"
        assert [row.split(",")[0] for row in rows[1:]] == ["northstar-labs", "blue-orbit"]


def test_samples_cover_both_structured_viewers(tmp_path: Path) -> None:
    """A document, one value per line, and invalid source text (D47)."""
    write_samples(tmp_path)

    names = {path.name for path in tmp_path.rglob("*")}
    assert {"people.json", "events.jsonl", "broken.json"} <= names


def test_the_sample_table_spans_more_than_one_page(tmp_path: Path) -> None:
    write_samples(tmp_path)

    lines = (tmp_path / "sample.csv").read_text(encoding="utf-8").splitlines()
    assert len(lines) == SAMPLE_ROWS + 1


def test_writing_twice_leaves_the_same_content(tmp_path: Path) -> None:
    write_samples(tmp_path)
    first = (tmp_path / "sample.csv").read_text(encoding="utf-8")

    write_samples(tmp_path)

    assert (tmp_path / "sample.csv").read_text(encoding="utf-8") == first


async def test_a_source_made_of_files_is_filled_with_them(tmp_path: Path) -> None:
    """What a started server is given to look at: the same files, written into
    the folder the source stands in through its own storage."""
    adapter = FileAdapter(FileOptions(), AdapterContext(home_dir=tmp_path))

    said = await adapter.install_sample_data()

    names = {node.name for node in await adapter.list_children(None)}
    assert {"sample.csv", "guide.md", "bundle.zip", "reports", "empty"} <= names
    assert said == f"{len(names)} sample files and folders"
