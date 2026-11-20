"""A folder's listing as FTP servers send it (D384)."""

from datetime import UTC, datetime

import pytest

from app.adapters.ftp.listing import from_list_line, from_mlsd_line, moment_of

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)


def test_an_mlsd_line_states_its_facts() -> None:
    found = from_mlsd_line(
        "type=file;size=1234;modify=20260305140210;unix.mode=0644; a b.csv"
    )

    assert found is not None
    assert (found.name, found.kind, found.size_bytes) == ("a b.csv", "file", 1234)
    assert found.modified_at == datetime(2026, 3, 5, 14, 2, 10, tzinfo=UTC)
    assert found.permissions == "-rw-r--r--"


@pytest.mark.parametrize(
    ("line", "kind"),
    [
        ("Type=DIR;Modify=20260101000000; reports", "directory"),
        ("type=OS.unix=slink:/srv/data;modify=20260101000000; data", "link"),
        ("type=OS.unix=symlink; data", "link"),
    ],
)
def test_an_mlsd_type_is_read_whatever_its_case(line: str, kind: str) -> None:
    found = from_mlsd_line(line)

    assert found is not None and found.kind == kind


@pytest.mark.parametrize(
    "line", ["type=cdir; .", "type=pdir; ..", "type=OS.unix=chr-1/3; null"]
)
def test_the_folder_its_parent_and_devices_are_left_out(line: str) -> None:
    assert from_mlsd_line(line) is None


def test_a_unix_listing_is_read_by_its_date() -> None:
    lines = [
        "total 12",
        "-rw-r--r--    1 1000     1000         1234 Mar 05 14:02 sales.csv",
        "drwxr-xr-x    2 ftp      ftp          4096 Jan  9  2024 old reports",
        "lrwxrwxrwx    1 ftp      ftp             9 Nov 01 09:00 data -> /srv/data",
        "-rw-r--r--    1 owner             7 Dec 31 23:59 no group.txt",
        "crw-rw-rw-    1 root     root       1,   3 Nov 01 09:00 null",
    ]

    found = [from_list_line(line, NOW) for line in lines]

    assert found[0] is None
    assert found[1] is not None
    assert (found[1].name, found[1].kind, found[1].size_bytes) == (
        "sales.csv",
        "file",
        1234,
    )
    assert found[1].modified_at == datetime(2026, 3, 5, 14, 2, tzinfo=UTC)
    assert found[1].permissions == "-rw-r--r--"
    assert found[2] is not None
    assert (found[2].name, found[2].kind) == ("old reports", "directory")
    assert found[2].modified_at == datetime(2024, 1, 9, tzinfo=UTC)
    assert found[3] is not None and (found[3].name, found[3].kind) == ("data", "link")
    # A time in the future of the server's own year is last year's.
    assert found[4] is not None and found[4].name == "no group.txt"
    assert found[4].modified_at == datetime(2025, 12, 31, 23, 59, tzinfo=UTC)
    assert found[5] is None


def test_a_windows_listing_is_read() -> None:
    folder = from_list_line("03-05-26  02:02PM       <DIR>          My Folder", NOW)
    file = from_list_line("11-19-2026  09:15AM             2048 notes.txt", NOW)

    assert folder is not None and (folder.name, folder.kind) == (
        "My Folder",
        "directory",
    )
    assert folder.modified_at == datetime(2026, 3, 5, 14, 2, tzinfo=UTC)
    assert file is not None and (file.name, file.size_bytes) == ("notes.txt", 2048)


def test_a_line_no_shape_fits_is_left_out() -> None:
    assert from_list_line("something the server says", NOW) is None
    assert moment_of("not a time") is None
