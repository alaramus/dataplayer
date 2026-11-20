"""A folder's listing as an FTP server sends it, read into entries (D384).

Two formats. MLSD (RFC 3659) is machine-readable and states its facts; a server
that does not speak it — vsftpd, the most common of all — answers LIST, which
is whatever `ls -l` or Windows' `dir` printed, read here by its two usual
shapes. A line that is neither is left out, as a name the path rule refuses is.

Plain functions over text, tested without a server.
"""

import re
import stat
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

Kind = Literal["file", "directory", "link"]


@dataclass(frozen=True)
class Listed:
    name: str
    kind: Kind
    size_bytes: int = 0
    modified_at: datetime | None = None
    permissions: str | None = None


# --- MLSD and MLST -------------------------------------------------------------


def facts_of(text: str) -> tuple[dict[str, str], str]:
    """`type=file;size=3; name` as its facts, named in lower case, and the
    name: everything after the first space, spaces in it kept."""
    head, _, name = text.partition(" ")
    facts: dict[str, str] = {}
    for fact in head.split(";"):
        key, equals, value = fact.partition("=")
        if equals:
            facts[key.strip().lower()] = value
    return facts, name


def from_facts(facts: dict[str, str], name: str) -> Listed | None:
    """One entry of MLSD, or MLST's answer; None for the folder itself, its
    parent, and a type nothing here opens."""
    kind_fact = facts.get("type", "").lower()
    kind: Kind
    if kind_fact == "file":
        kind = "file"
    elif kind_fact == "dir":
        kind = "directory"
    elif kind_fact.startswith("os.unix=slink") or kind_fact.startswith(
        "os.unix=symlink"
    ):
        kind = "link"
    else:
        # `cdir` and `pdir` are the folder and its parent; anything else is a
        # device or a type of one server's own.
        return None
    size = facts.get("size") or facts.get("sizd") or "0"
    return Listed(
        name=name,
        kind=kind,
        size_bytes=int(size) if size.isdigit() and kind == "file" else 0,
        modified_at=moment_of(facts.get("modify")),
        permissions=_mode_text(facts.get("unix.mode"), kind),
    )


def from_mlsd_line(line: str) -> Listed | None:
    facts, name = facts_of(line)
    return from_facts(facts, name) if name else None


def moment_of(value: str | None) -> datetime | None:
    """`YYYYMMDDHHMMSS[.sss]`, which RFC 3659 says is UTC — MDTM's answer too."""
    if value is None:
        return None
    digits = value.strip().split(".")[0]
    try:
        return datetime.strptime(digits, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    except ValueError:
        return None


def _mode_text(mode: str | None, kind: Kind) -> str | None:
    if mode is None:
        return None
    try:
        bits = int(mode, 8)
    except ValueError:
        return None
    type_bits = {"file": stat.S_IFREG, "directory": stat.S_IFDIR, "link": stat.S_IFLNK}[
        kind
    ]
    return stat.filemode(type_bits | (bits & 0o7777))


# --- LIST ------------------------------------------------------------------------

_MONTHS = {
    name: number
    for number, name in enumerate(
        (
            "jan",
            "feb",
            "mar",
            "apr",
            "may",
            "jun",
            "jul",
            "aug",
            "sep",
            "oct",
            "nov",
            "dec",
        ),
        start=1,
    )
}
_UNIX_MODE = re.compile(r"^[-dlbcps][-rwxsStTlL]{9}[.+@]?$")
_DAY = re.compile(r"^\d{1,2}$")
_TIME_OR_YEAR = re.compile(r"^(?:\d{1,2}:\d{2}(?::\d{2})?|\d{4})$")
_TOKEN = re.compile(r"\S+")
_DOS = re.compile(
    r"^(?P<month>\d{2})-(?P<day>\d{2})-(?P<year>\d{2}|\d{4})\s+"
    r"(?P<hour>\d{1,2}):(?P<minute>\d{2})\s*(?P<half>[AaPp][Mm])?\s+"
    r"(?P<size><DIR>|\d+)\s+(?P<name>.+)$"
)


def from_list_line(line: str, now: datetime) -> Listed | None:
    """One line of LIST, in `ls -l`'s shape or in `dir`'s; None for anything
    else — `total 12`, a device, a line no shape fits."""
    line = line.rstrip("\r\n")
    return _unix(line, now) if _UNIX_MODE.match(line.split(" ", 1)[0]) else _dos(line)


def _unix(line: str, now: datetime) -> Listed | None:
    """`-rw-r--r--  1 owner group  1234 Mar  5 14:02 name`.

    Found by the date rather than by counting columns: a server may leave out
    the group, the owner or the count of links, but never the date, and the
    size is the column before it.
    """
    tokens = list(_TOKEN.finditer(line))
    mode = tokens[0].group()
    for at in range(2, len(tokens) - 3):
        month = _MONTHS.get(tokens[at].group().lower())
        if (
            month is None
            or not tokens[at - 1].group().isdigit()
            or not _DAY.match(tokens[at + 1].group())
            or not _TIME_OR_YEAR.match(tokens[at + 2].group())
        ):
            continue
        name = line[tokens[at + 2].end() + 1 :]
        kind: Kind
        if mode[0] == "d":
            kind = "directory"
        elif mode[0] == "l":
            kind = "link"
            name = name.split(" -> ", 1)[0]
        elif mode[0] == "-":
            kind = "file"
        else:
            return None
        if name == "":
            return None
        return Listed(
            name=name,
            kind=kind,
            size_bytes=int(tokens[at - 1].group()) if kind == "file" else 0,
            modified_at=_unix_moment(
                month, int(tokens[at + 1].group()), tokens[at + 2].group(), now
            ),
            permissions=mode[:10],
        )
    return None


def _unix_moment(
    month: int, day: int, time_or_year: str, now: datetime
) -> datetime | None:
    """`ls` prints a time for the last six months and a year before that. A
    time is this year's unless that would be in the future, then last year's.
    The server's own time zone is not said, so it is taken as UTC."""
    try:
        if ":" not in time_or_year:
            return datetime(int(time_or_year), month, day, tzinfo=UTC)
        hour, minute, *_ = (int(part) for part in time_or_year.split(":"))
        moment = datetime(now.year, month, day, hour, minute, tzinfo=UTC)
        if moment > now + timedelta(days=1):
            moment = moment.replace(year=now.year - 1)
        return moment
    except ValueError:
        return None


def _dos(line: str) -> Listed | None:
    """`03-05-26  02:02PM       <DIR>          name`, as IIS and Windows print."""
    found = _DOS.match(line)
    if found is None:
        return None
    year = int(found["year"])
    if year < 100:
        year += 2000 if year < 70 else 1900
    hour = int(found["hour"]) % 12 if found["half"] else int(found["hour"])
    if found["half"] and found["half"].lower() == "pm":
        hour += 12
    try:
        moment: datetime | None = datetime(
            year,
            int(found["month"]),
            int(found["day"]),
            hour,
            int(found["minute"]),
            tzinfo=UTC,
        )
    except ValueError:
        moment = None
    is_directory = found["size"] == "<DIR>"
    return Listed(
        name=found["name"],
        kind="directory" if is_directory else "file",
        size_bytes=0 if is_directory else int(found["size"]),
        modified_at=moment,
    )
