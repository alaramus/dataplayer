"""IMAP's modified UTF-7 for folder names (RFC 3501, 5.1.3)."""

from app.adapters.mail import utf7


def test_cyrillic_is_named_as_imap_names_it() -> None:
    assert utf7.encode("Входящие") == "&BBIERQQ+BDQETwRJBDgENQ-"
    assert utf7.decode("&BBIERQQ+BDQETwRJBDgENQ-") == "Входящие"


def test_an_ampersand_stands_for_itself() -> None:
    assert utf7.encode("R&D") == "R&-D"
    assert utf7.decode("R&-D") == "R&D"


def test_names_round_trip() -> None:
    for name in ["INBOX", "Отчёты/2026", "日本語", "a & b", "Mix Ё z", "😀"]:
        assert utf7.decode(utf7.encode(name)) == name


def test_text_that_is_not_modified_utf7_is_left_as_it_is() -> None:
    assert utf7.decode("Broken&abc") == "Broken&abc"
