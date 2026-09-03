"""What a file's name says it can be opened as, before anything is read."""

import pytest

from app.adapters.file.formats import format_of, representations_of


@pytest.mark.parametrize(
    "name",
    [
        "app-2026-09-03.dump",
        "APP.DUMP",
        "nightly.backup",
        "app.pgdump",
    ],
)
def test_a_database_dump_offers_no_viewer(name: str) -> None:
    """The catalog says so at once instead of after a refused request.

    A `pg_dump --format=custom` archive is what this application's own backups
    are, and it used to fall through to the text default: the catalog offered
    "View as text", the click opened a panel, and the answer — that the file
    is binary — arrived only after the request that had to be made to find
    out.
    """
    assert format_of(name) == "opaque"
    assert representations_of(name) == []


def test_a_name_that_only_looks_like_one_is_still_text() -> None:
    """Classification is by suffix, and `notes.dumped` is not a suffix."""
    assert format_of("notes.dumped") == "text"
