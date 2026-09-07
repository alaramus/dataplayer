"""A container run once for its exit code, rather than kept for its port.

`pg_dump` and `pg_restore` are programs, not statements: this application's own
image has neither, and the version of the program has to match the server it
is pointed at — a dump taken by an older `pg_dump` of a newer server is
refused by the program itself, with good reason.

The runtime the phase already built answers both. The program is run in the
image of the server's own major version, once, and what comes back is an exit
code and its output (D87). Nothing is installed into this application's image,
and nothing has to match anything.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Mount:
    """One named volume, at one place inside the container.

    A volume rather than a path on the host, by the same rule a service's data
    directory follows (D80): a path on the host is the thing no part of this
    may choose.
    """

    volume: str
    path: str
    read_only: bool = False


@dataclass(frozen=True)
class ToolRun:
    """One program to run in one container, and what it needs to run it."""

    name: str
    image: str
    argv: tuple[str, ...]
    environment: Mapping[str, str]
    mounts: tuple[Mount, ...]
    network: str | None
    labels: Mapping[str, str]
    full_output: bool = False
    timeout_seconds: float = 3600.0

    def __repr__(self) -> str:
        """The environment holds a password, so it is described rather than
        printed — the rule the container specification follows."""
        keys = ", ".join(sorted(self.environment))
        return (
            f"ToolRun(name={self.name!r}, image={self.image!r}, "
            f"argv={self.argv!r}, environment keys: {keys})"
        )


@dataclass(frozen=True)
class ToolResult:
    """What the program did: its exit code, and the last of what it printed.

    The output is kept because a failed `pg_dump` says why in one line, and
    that line is the difference between "it did not work" and something a
    person can act on. It is the program's own words about the database rather
    than the daemon's about the machine, which is why it may be shown.
    """

    exit_code: int
    output: Sequence[str]
    truncated: bool = False

    @property
    def ok(self) -> bool:
        return self.exit_code == 0
