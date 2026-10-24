"""What copies a SQLite file out, and what puts it back (D87, D260).

SQLite has no dump program a version must match: its online backup copies
the database page by page under its own locks, so the copy is one state of
the file even while somebody writes to it. Python's `sqlite3` reaches that
API, so the program is a short script in the official Python image, the
family this application's own image is built from.

The file is in the owner's storage, and the tool's container mounts that
storage where this application has it (D87), so the file's path here is its
path there. A restore writes that file, which is why its program asks for
the storage to be writable.

Nothing here runs anything. It says what to run; a job runs it.
"""

from collections.abc import Sequence

from app.adapters.protocol import AdapterError, BackupAvailability, BackupProgram
from app.adapters.sqlite.session import SqliteSession
from app.core.translation import say

IMAGE = "python:3.14-slim"

# What every SQLite database file begins with.
_HEADER = b"SQLite format 3\x00"

# One script for the three: copy the file out, copy a backup in, or say
# whether a backup reads whole. A file is opened by URI, so it is read only
# where it is only read and never created where it should already be.
_SCRIPT = """
import pathlib, sqlite3, sys
def open_(path, mode):
    return sqlite3.connect(pathlib.Path(path).as_uri() + "?mode=" + mode, uri=True)
what, source, target = sys.argv[1], sys.argv[2], sys.argv[3:]
reading = open_(source, "ro")
if what == "check":
    print(reading.execute("PRAGMA quick_check(1)").fetchone()[0])
    print(reading.execute("SELECT count(*) FROM sqlite_schema WHERE type = 'table'").fetchone()[0])
else:
    writing = open_(target[0], "rwc" if what == "out" else "rw")
    reading.backup(writing)
    writing.close()
reading.close()
"""


class SqliteBackup:
    """How a SQLite file is copied out and put back."""

    def __init__(self, session: SqliteSession) -> None:
        self._session = session

    async def backup_availability(self) -> BackupAvailability:
        check = await self._session.check()
        if not check.ok:
            return BackupAvailability(available=False, reason=check.message)
        return BackupAvailability(available=True)

    async def backup_program(self, *, into: str) -> BackupProgram:
        """The file, copied by SQLite's online backup into a new one."""
        return BackupProgram(
            image=IMAGE,
            argv=("python", "-I", "-c", _SCRIPT, "out", await self._database(), into),
            environment={},
        )

    async def restore_program(self, *, from_file: str) -> BackupProgram:
        """The backup, copied over the file page by page.

        Every table, index and row the file holds is replaced by the
        backup's, which is why the route that asks for it insists on being
        told so.
        """
        return BackupProgram(
            image=IMAGE,
            argv=(
                "python",
                "-I",
                "-c",
                _SCRIPT,
                "in",
                from_file,
                await self._database(),
            ),
            environment={},
            writes_storage=True,
        )

    async def restore_inventory_program(self, *, from_file: str) -> BackupProgram:
        """SQLite's own check of the backup, and how many tables it holds."""
        return BackupProgram(
            image=IMAGE,
            argv=("python", "-I", "-c", _SCRIPT, "check", from_file),
            environment={},
        )

    def validate_restore_inventory(self, lines: Sequence[str]) -> None:
        """A whole database, or a refusal before the file is written over."""
        said = [line.strip() for line in lines if line.strip()]
        if not said or said[0] != "ok":
            raise ValueError(say("This backup is damaged and cannot be restored"))

    def restore_archive_reason(self, head: bytes) -> str | None:
        if head.startswith(_HEADER):
            return None
        return say("This file is not a SQLite backup")

    async def _database(self) -> str:
        offer = await self.backup_availability()
        if not offer.available:
            raise ValueError(offer.reason)
        try:
            return self._session.path()
        except AdapterError as exc:
            raise ValueError(exc.message) from None
