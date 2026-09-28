"""The log files read back for the panel (D184)."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.system.log_reader import LogEntry, read_page

START = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)


def _write(path: Path, *entries: dict[str, object]) -> None:
    path.write_text("".join(json.dumps(entry) + "\n" for entry in entries), encoding="utf-8")


def _entry(minute: int, process: str, level: str = "INFO", **extra: object) -> dict[str, object]:
    return {
        "time": (START + timedelta(minutes=minute)).isoformat(),
        "process": process,
        "level": level,
        "logger": "app.test",
        "message": f"{process} at {minute}",
        **extra,
    }


def _logs(folder: Path) -> None:
    # Rotation renames: backend.log.1 is older than backend.log.
    _write(
        folder / "backend.log.1",
        _entry(1, "backend"),
        _entry(2, "backend", "ERROR", ref="K7Q3PD"),
    )
    _write(folder / "backend.log", _entry(5, "backend"), _entry(7, "backend", "WARNING"))
    with (folder / "backend.log").open("a", encoding="utf-8") as tail:
        tail.write("not json at all\n")
    _write(folder / "metrics.log", _entry(3, "metrics"), _entry(6, "metrics", "ERROR"))


def _minutes(entries: list[LogEntry]) -> list[int]:
    return [int((entry.time - START).total_seconds() // 60) for entry in entries]


def test_every_process_newest_first_across_rotated_files(tmp_path: Path) -> None:
    _logs(tmp_path)

    page = read_page(tmp_path)

    assert page.kept
    assert _minutes(page.entries) == [7, 6, 5, 3, 2, 1]
    assert not page.more


def test_a_level_keeps_that_and_worse(tmp_path: Path) -> None:
    _logs(tmp_path)

    assert _minutes(read_page(tmp_path, level="warning").entries) == [7, 6, 2]
    assert _minutes(read_page(tmp_path, level="error").entries) == [6, 2]


def test_one_process_and_a_ref_are_found(tmp_path: Path) -> None:
    _logs(tmp_path)

    assert _minutes(read_page(tmp_path, process="metrics").entries) == [6, 3]
    [found] = read_page(tmp_path, text="k7q3pd").entries
    assert found.ref == "K7Q3PD"


def test_a_page_says_there_is_more_and_the_next_starts_before_it(tmp_path: Path) -> None:
    _logs(tmp_path)

    first = read_page(tmp_path, limit=2)
    second = read_page(tmp_path, limit=2, before=first.entries[-1].time)

    assert _minutes(first.entries) == [7, 6]
    assert first.more
    assert _minutes(second.entries) == [5, 3]


def test_following_asks_only_for_what_came_after(tmp_path: Path) -> None:
    _logs(tmp_path)

    newer = read_page(tmp_path, after=START + timedelta(minutes=5))

    assert _minutes(newer.entries) == [7, 6]


def test_no_files_yet_is_an_empty_page(tmp_path: Path) -> None:
    page = read_page(tmp_path)

    assert page.kept
    assert page.entries == []
