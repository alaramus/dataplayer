from pathlib import Path

from app.seed_storage import SAMPLE_ROWS, write_samples


def test_samples_cover_every_content_kind(tmp_path: Path) -> None:
    """A table, plain text and something unreadable: the three outcomes."""
    write_samples(tmp_path)

    names = {path.name for path in tmp_path.rglob("*")}
    assert {"sample.csv", "sample.tsv", "notes.txt", "logo.png", "reports"} <= names


def test_the_sample_table_spans_more_than_one_page(tmp_path: Path) -> None:
    write_samples(tmp_path)

    lines = (tmp_path / "sample.csv").read_text(encoding="utf-8").splitlines()
    assert len(lines) == SAMPLE_ROWS + 1


def test_writing_twice_leaves_the_same_content(tmp_path: Path) -> None:
    write_samples(tmp_path)
    first = (tmp_path / "sample.csv").read_text(encoding="utf-8")

    write_samples(tmp_path)

    assert (tmp_path / "sample.csv").read_text(encoding="utf-8") == first
