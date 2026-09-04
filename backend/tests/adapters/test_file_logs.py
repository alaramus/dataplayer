"""A log file read as the columns its own lines are written in.

The shape is read off the file: there is no header to trust and no extension
per format, so the answer has to come from the lines themselves.
"""

from pathlib import Path

import pytest

from app.adapters.content import EditorContentRequest
from app.adapters.file import logs
from app.adapters.file.content import FileContent
from app.adapters.file.formats import format_of, offers_source, representations_of
from app.adapters.file.readers import LogReader
from app.adapters.file.session import FileSession

POSTGRES = (
    "2026-09-03 12:00:00.123 UTC [42] LOG:  database system is ready\n"
    "2026-09-03 12:00:01.456 UTC [43] ERROR:  relation orders does not exist\n"
)
BRACKETED = (
    "[2026-09-03 12:00:00.123] [INFO] (42) app.module: started\n"
    "[2026-09-03 12:00:01.999] [ERROR] (42) app.module: failed [handler]\n"
)
CONTAINER = (
    "2026-09-03T12:00:00.123456789Z listening on 8080\n"
    "2026-09-03T12:00:01.000000000Z request served\n"
)
SYSLOG = (
    "Sep 03 12:00:00 host sshd: accepted publickey\n"
    "Sep 03 12:00:05 host cron: session opened\n"
)
PLAIN = "2026-09-03 12:00:00 INFO  started up\n2026-09-03 12:00:01 WARNING disk filling\n"
JSON_LINES = (
    '{"time": "12:00", "level": "info", "msg": "hello"}\n'
    '{"time": "12:01", "level": "warn", "msg": "hm"}\n'
)


def _log(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "server.log"
    path.write_text(text, encoding="utf-8")
    return path


def test_a_log_is_read_as_text_and_offered_as_a_table() -> None:
    """Text first, because that is what a log is; a table second, because a log
    line is not shapeless."""
    assert format_of("server.log") == "log"
    assert [one.kind for one in representations_of("server.log")] == ["text", "table"]
    # A .txt keeps the one it had: it is as likely to be a note as a log.
    assert [one.kind for one in representations_of("notes.txt")] == ["text"]


async def test_the_text_a_log_offers_is_text_it_will_actually_show(
    tmp_path: Path,
) -> None:
    """The two lists were separate, and they drifted the moment a log arrived:
    its first representation was text, and opening it answered that the file
    offered no source editing while its table worked."""
    _log(tmp_path, POSTGRES)
    content = FileContent(FileSession(tmp_path))

    document = await content.read_editor_content(
        EditorContentRequest(node_id="server.log")
    )

    assert document.text.startswith("2026-09-03 12:00:00.123 UTC")
    assert document.writable is True


def test_what_has_a_source_view_is_read_off_what_it_offers() -> None:
    """One statement instead of two lists that can disagree."""
    for named in ["server.log", "notes.txt", "readme.md", "a.json", "a.jsonl"]:
        assert offers_source(named) is True, named
    # A table and nothing else, or no viewer at all: neither has text to show.
    for named in ["rows.csv", "budget.xlsx", "photo.png", "bundle.zip"]:
        assert offers_source(named) is False, named


@pytest.mark.parametrize(
    ("text", "shape", "columns", "first"),
    [
        (
            POSTGRES,
            "postgres",
            ["time", "zone", "pid", "level", "message"],
            ["2026-09-03 12:00:00.123", "UTC", "42", "LOG", "database system is ready"],
        ),
        (
            BRACKETED,
            "bracketed",
            ["time", "level", "id", "source", "message"],
            ["2026-09-03 12:00:00.123", "INFO", "42", "app.module", "started"],
        ),
        (
            CONTAINER,
            "container",
            ["time", "message"],
            ["2026-09-03T12:00:00.123456789Z", "listening on 8080"],
        ),
        (
            SYSLOG,
            "syslog",
            ["time", "host", "source", "message"],
            ["Sep 03 12:00:00", "host", "sshd", "accepted publickey"],
        ),
        (
            PLAIN,
            "plain",
            ["time", "level", "message"],
            ["2026-09-03 12:00:00", "INFO", "started up"],
        ),
    ],
)
def test_each_shape_is_recognised_and_taken_apart(
    tmp_path: Path,
    text: str,
    shape: str,
    columns: list[str],
    first: list[str],
) -> None:
    path = _log(tmp_path, text)

    assert logs.shape_of(path) == shape
    page = LogReader().read(path, 10, 0)
    assert [column.name for column in page.columns] == columns
    assert page.rows[0] == first


def test_a_particular_shape_wins_over_a_looser_one(tmp_path: Path) -> None:
    """A PostgreSQL line also satisfies "time, level, message", and being told
    which server wrote it is worth more than being told it is a log."""
    assert logs.shape_of(_log(tmp_path, POSTGRES)) == "postgres"


def test_lines_of_json_objects_become_their_own_keys(tmp_path: Path) -> None:
    path = _log(tmp_path, JSON_LINES)

    assert logs.shape_of(path) == logs.JSON_LINES
    page = LogReader().read(path, 10, 0)
    assert [column.name for column in page.columns] == ["time", "level", "msg"]
    assert page.rows[0] == ["12:00", "info", "hello"]


def test_a_log_of_no_known_shape_is_still_shown(tmp_path: Path) -> None:
    """As the numbered lines it is: a log nobody has taught this module yet is
    still a log somebody wants to look at."""
    path = _log(tmp_path, "just some notes\nnothing structured here\n")

    assert logs.shape_of(path) is None
    page = LogReader().read(path, 10, 0)
    assert [column.name for column in page.columns] == ["line_no", "line"]
    assert page.rows[0] == ["1", "just some notes"]


def test_a_continuation_line_keeps_its_place_under_the_message(
    tmp_path: Path,
) -> None:
    """A stack trace under an exception is part of the log. Dropping it would
    lose the half of the entry that says what went wrong."""
    path = _log(
        tmp_path,
        "2026-09-03 12:00:00.1 UTC [1] ERROR:  boom\n"
        "  STATEMENT:  SELECT 1\n"
        "2026-09-03 12:00:02.1 UTC [1] LOG:  fine\n",
    )

    rows = LogReader().read(path, 10, 0).rows

    assert len(rows) == 3
    assert rows[1] == [None, None, None, None, "  STATEMENT:  SELECT 1"]


def test_a_shape_names_its_columns_once() -> None:
    """The columns are the named groups of the pattern: one statement rather
    than an expression and a list of names beside it. Every group is named, or
    a column would exist that nothing can be read into."""
    for shape in logs.SHAPES:
        assert shape.columns[-1] == "message"
        assert len(shape.columns) == shape.pattern.groups


def test_a_page_of_a_log_is_a_page(tmp_path: Path) -> None:
    path = _log(
        tmp_path,
        "".join(
            f"2026-09-03 12:00:0{n}.1 UTC [1] LOG:  line {n}\n" for n in range(5)
        ),
    )

    page = LogReader().read(path, 2, 2)

    assert [row[-1] for row in page.rows] == ["line 2", "line 3"]
    assert page.has_more is True


def test_an_empty_log_has_no_shape_and_no_rows(tmp_path: Path) -> None:
    path = _log(tmp_path, "")

    assert logs.shape_of(path) is None
    assert LogReader().read(path, 10, 0).rows == []
