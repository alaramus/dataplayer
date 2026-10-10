"""A log file as rows: the shapes lines come in, and which one a file is in.

A log is text, and reading it as text is what the editor is for. What it is
*not* is unstructured: a line carries a time, a level and a message, and every
tool that shows logs shows those as columns.

The shape is read off the file rather than declared by it. There is no header
to trust and no extension per format, so the first lines of the file are tried
against each known shape and the one most of them fit wins. A file that fits
none is still shown, as the numbered lines it is.

The columns of a shape are the named groups of its own pattern, in order, so a
shape is one regular expression and nothing else has to agree with it.
"""

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

# How many lines are read to decide what a file is. Enough that a run of
# stack-trace lines at the top cannot speak for the file, small enough that
# deciding costs nothing.
SAMPLE_LINES = 40

# How much of the sample a shape has to fit before it is believed. Not all of
# it: a real log holds continuation lines, blank lines and the occasional line
# written by something else.
AGREEMENT = 0.6

# What a line is called when a file is JSON, one object per line. The columns
# are then the keys, and this module leaves that to the record reader.
JSON_LINES = "json"


@dataclass(frozen=True)
class LogShape:
    """One way a log line is written, and the columns it yields."""

    name: str
    pattern: re.Pattern[str]

    @property
    def columns(self) -> list[str]:
        """The named groups of the pattern, in the order they appear in it.

        Read off the expression rather than written beside it: a shape is one
        regular expression, and a list of names next to it would be a second
        statement to keep in step with the first.
        """
        groups = self.pattern.groupindex
        return sorted(groups, key=lambda name: groups[name])


# The shapes, most particular first: a PostgreSQL line also satisfies the
# looser "time, level, message" of the plain shape, and being told it is a
# PostgreSQL log is worth more than being told it is a log.
SHAPES: tuple[LogShape, ...] = (
    LogShape(
        # [2026-09-03 12:00:00.123] [INFO] (42) app.module: what happened
        name="bracketed",
        pattern=re.compile(
            r"^\[(?P<time>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}[.,]\d+)\] "
            r"\[(?P<level>\w+)\] "
            r"(?:\((?P<id>\d+)\) )?"
            r"(?P<source>[\w\[\]./:_-]+): "
            r"(?P<message>.*)$"
        ),
    ),
    LogShape(
        # 2026-09-03 12:00:00.123 UTC [42] LOG:  what happened
        name="postgres",
        pattern=re.compile(
            r"^(?P<time>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}[.,]\d+) "
            r"(?P<zone>[A-Z]{2,5}) "
            r"\[(?P<pid>\d+)\] "
            r"(?P<level>[A-Z]+):\s+"
            r"(?P<message>.*)$"
        ),
    ),
    LogShape(
        # 2026-09-03T12:00:00.123456789Z what the container wrote
        name="container",
        pattern=re.compile(
            r"^(?P<time>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?) "
            r"(?P<message>.*)$"
        ),
    ),
    LogShape(
        # Sep 03 12:00:00 host service: what happened
        name="syslog",
        pattern=re.compile(
            r"^(?P<time>[A-Z][a-z]{2} [ \d]\d \d{2}:\d{2}:\d{2}) "
            r"(?P<host>\S+) "
            r"(?P<source>[^:]+): "
            r"(?P<message>.*)$"
        ),
    ),
    LogShape(
        # 2026-09-03 12:00:00 INFO what happened
        name="plain",
        pattern=re.compile(
            r"^(?P<time>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?) "
            r"(?P<level>[A-Za-z]+)\s+"
            r"(?P<message>.*)$"
        ),
    ),
)

_BY_NAME = {shape.name: shape for shape in SHAPES}


def shape_named(name: str) -> LogShape | None:
    return _BY_NAME.get(name)


def _sample(source: Iterable[str]) -> list[str]:
    lines: list[str] = []
    for line in source:
        stripped = line.rstrip("\n").rstrip("\r")
        if stripped.strip() == "":
            continue
        lines.append(stripped)
        if len(lines) == SAMPLE_LINES:
            break
    return lines


def _is_json_object(line: str) -> bool:
    try:
        return isinstance(json.loads(line), dict)
    except (ValueError, RecursionError):
        return False


def shape_of(path: Path) -> str | None:
    """What this file's lines look like: a shape's name, `json`, or nothing.

    Nothing means no shape fits, and the caller shows the lines as they are —
    which is the honest answer for a log nobody has taught this module yet.
    """
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return shape_of_lines(handle)


def shape_of_lines(source: Iterable[str]) -> str | None:
    """The same detection for a file handle and a bounded SQL snapshot."""
    lines = _sample(source)
    if not lines:
        return None
    if sum(1 for line in lines if _is_json_object(line)) >= AGREEMENT * len(lines):
        return JSON_LINES
    for shape in SHAPES:
        fitted = sum(1 for line in lines if shape.pattern.match(line) is not None)
        if fitted >= AGREEMENT * len(lines):
            return shape.name
    return None


def parse(shape: LogShape, line: str) -> list[str | None]:
    """One line as the columns of this shape.

    A line that does not fit is not dropped and not an error: a stack trace
    under an exception is part of the log, and it belongs under the message of
    the line it follows. It goes into the last column with the others left
    empty, so a reader can still see it and a sort by time still works.
    """
    found = shape.pattern.match(line)
    columns = shape.columns
    if found is None:
        return [None] * (len(columns) - 1) + [line]
    return [found.group(name) for name in columns]
