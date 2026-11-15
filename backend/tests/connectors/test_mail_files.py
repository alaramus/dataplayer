"""An attachment kept in its owner's folder (D371)."""

from pathlib import Path

import pytest

from app.adapters.actions import StorageFull
from app.connectors.mail_files import keep_attachment, safe_name


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
