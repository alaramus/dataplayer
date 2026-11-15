"""An attachment kept in its owner's folder (D371)."""

from pathlib import Path

import pytest

from app.adapters.actions import StorageFull
from app.connectors.mail_files import (
    TooLarge,
    keep_attachment,
    listing,
    read_stored,
    safe_name,
)


def test_a_name_is_made_plain_on_both_platforms() -> None:
    assert safe_name("отчёт.csv") == "отчёт.csv"
    assert safe_name("../../etc/passwd") == ".._.._etc_passwd"
    assert safe_name("C:evil.txt") == "C_evil.txt"
    assert safe_name("a<b>:c?.txt") == "a_b__c_.txt"
    assert safe_name("") == "attachment"
    assert safe_name("..") == "attachment"
    assert len(safe_name("x" * 400 + ".pdf")) <= 150
    assert safe_name("x" * 400 + ".pdf").endswith(".pdf")


def test_a_second_copy_is_numbered_rather_than_written_over(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    first = keep_attachment(
        home=home, address="alice@example.com", filename="r.csv", body=b"1", limit_bytes=None
    )
    second = keep_attachment(
        home=home, address="alice@example.com", filename="r.csv", body=b"2", limit_bytes=None
    )
    assert first == "Mail/alice@example.com/r.csv"
    assert second == "Mail/alice@example.com/r (2).csv"
    assert (home / first).read_bytes() == b"1"
    assert (home / second).read_bytes() == b"2"


def test_a_write_past_the_limit_is_refused(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / "big.bin").write_bytes(b"x" * 900)
    with pytest.raises(StorageFull):
        keep_attachment(
            home=home, address="a@b.c", filename="f.bin", body=b"y" * 200, limit_bytes=1000
        )
    assert not (home / "Mail" / "a@b.c" / "f.bin").exists()


def test_a_folder_lists_folders_first_and_hides_dotfiles(tmp_path: Path) -> None:
    home = tmp_path / "home"
    (home / "Reports").mkdir(parents=True)
    (home / "Reports" / "q3.csv").write_bytes(b"1234")
    (home / "a.txt").write_bytes(b"a")
    (home / ".hidden").write_bytes(b"h")
    top = listing(home, "")
    assert [(one.name, one.is_directory) for one in top.entries] == [("Reports", True), ("a.txt", False)]
    inside = listing(home, "Reports")
    (only,) = inside.entries
    assert (only.path, only.size) == ("Reports/q3.csv", 4)


def test_a_folder_out_of_the_storage_is_refused(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    for path in ["..", "../other", "a.txt"]:
        with pytest.raises(ValueError):
            listing(home, path)


def test_stored_files_are_read_by_the_containment_rule(tmp_path: Path) -> None:
    home = tmp_path / "home"
    (home / "Reports").mkdir(parents=True)
    (home / "Reports" / "отчёт.csv").write_bytes(b"x,y\n")
    (only,) = read_stored(home, ["Reports/отчёт.csv"], room=1000)
    assert (only.filename, only.media_type, only.body) == ("отчёт.csv", "text/csv", b"x,y\n")
    for refused in ["Reports", "missing.txt", "../secret.txt", "C:/Windows/win.ini"]:
        with pytest.raises(ValueError):
            read_stored(home, [refused], room=1000)


def test_stored_files_past_the_room_left_are_refused_before_reading(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / "big.bin").write_bytes(b"x" * 100)
    with pytest.raises(TooLarge):
        read_stored(home, ["big.bin"], room=99)
