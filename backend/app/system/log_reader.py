"""The log files read back, newest first, for the log panel (D184).

Each process writes its own file of JSON lines and rotates it by renaming, so a
process's history is `backend.log`, `backend.log.1`, … newest first. Reading
starts at the end of the newest and walks back, and stops at a page, at the
entry it was told to stop before, or at a ceiling of bytes: a panel asking for
errors among fifty megabytes of requests gets an answer, not a stall.
"""

from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError

from app.core.logs import PROCESSES, ProcessName

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
LevelChoice = Literal["all", "warning", "error"]
ProcessChoice = Literal["all", "backend", "metrics", "search-keeper"]

_RANK: dict[str, int] = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
_FLOOR: dict[LevelChoice, int] = {"all": 0, "warning": 30, "error": 40}

# Read per process per request, whatever the page asked for.
SCAN_CEILING_BYTES = 32 * 1024 * 1024
_CHUNK = 64 * 1024
# More than LOG_FILE_COUNT allows, so a smaller count set later still finds
# the files an earlier, larger one left behind.
_MAX_FILES = 50


class LogEntry(BaseModel):
    time: datetime
    process: ProcessName
    level: LogLevel
    logger: str
    message: str
    ref: str | None = None
    request: str | None = None
    exception: str | None = None


class LogPage(BaseModel):
    # False when this server keeps no files (LOG_DIR unset): there is nothing
    # to read, and the panel says where the log is instead.
    kept: bool
    entries: list[LogEntry]
    # Reading stopped at the page or at the ceiling: older entries may match.
    more: bool


def read_page(
    folder: Path,
    *,
    level: LevelChoice = "all",
    process: ProcessChoice = "all",
    text: str | None = None,
    before: datetime | None = None,
    after: datetime | None = None,
    limit: int = 200,
) -> LogPage:
    """The newest `limit` entries that match, from every process asked for."""
    floor = _FLOOR[level]
    needle = (text or "").strip().lower()
    before = _aware(before)
    after = _aware(after)

    def matches(entry: LogEntry) -> bool:
        if _RANK[entry.level] < floor:
            return False
        if needle == "":
            return True
        fields = (entry.message, entry.logger, entry.ref, entry.request, entry.exception)
        return any(needle in field.lower() for field in fields if field)

    found: list[LogEntry] = []
    more = False
    for name in PROCESSES if process == "all" else (process,):
        entries, stopped = _newest_first(folder, name, matches, before, after, limit)
        found += entries
        more = more or stopped
    found.sort(key=lambda entry: entry.time, reverse=True)
    if len(found) > limit:
        found = found[:limit]
        more = True
    return LogPage(kept=True, entries=found, more=more)


def _newest_first(
    folder: Path,
    process: ProcessName,
    matches: Callable[[LogEntry], bool],
    before: datetime | None,
    after: datetime | None,
    limit: int,
) -> tuple[list[LogEntry], bool]:
    found: list[LogEntry] = []
    scanned = 0
    for path in _files(folder, process):
        for line in _lines_backwards(path):
            scanned += len(line) + 1
            if scanned > SCAN_CEILING_BYTES:
                return found, True
            entry = _parsed(line)
            if entry is None:
                continue
            if before is not None and entry.time >= before:
                continue
            if after is not None and entry.time <= after:
                return found, False
            if matches(entry):
                found.append(entry)
                if len(found) == limit:
                    return found, True
    return found, False


def _files(folder: Path, process: ProcessName) -> Iterator[Path]:
    yield folder / f"{process}.log"
    for number in range(1, _MAX_FILES):
        candidate = folder / f"{process}.log.{number}"
        if not candidate.exists():
            return
        yield candidate


def _lines_backwards(path: Path) -> Iterator[bytes]:
    """The file's lines from its last to its first.

    A file renamed away by a rotation between opening and reading is simply
    read as it was; one that is gone is nothing.
    """
    try:
        handle = path.open("rb")
    except FileNotFoundError:
        return
    with handle:
        position = handle.seek(0, 2)
        rest = b""
        while position > 0:
            step = min(_CHUNK, position)
            position -= step
            handle.seek(position)
            block = handle.read(step) + rest
            lines = block.split(b"\n")
            rest = lines[0]
            for line in reversed(lines[1:]):
                if line.strip():
                    yield line
        if rest.strip():
            yield rest


def _parsed(line: bytes) -> LogEntry | None:
    try:
        return LogEntry.model_validate_json(line)
    except ValidationError:
        return None


def _aware(moment: datetime | None) -> datetime | None:
    if moment is None or moment.tzinfo is not None:
        return moment
    return moment.replace(tzinfo=UTC)
