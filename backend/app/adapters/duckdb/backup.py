"""What copies a DuckDB file out, and what puts it back (D87, D401).

DuckDB has no online backup a script can reach without DuckDB itself, and the
tool image must not carry a version of its own (D87): the file is the backup.
Before the program is named, the connection opens the file and runs
CHECKPOINT, which writes the log into it; the program, a short script in the
image SQLite's backup runs in (D260), then copies it byte by byte, and
refuses while a `.wal` lies beside it, since another program is writing.

A restore is written beside the file and moved into place, so a reader never
sees half of it; it too is refused while the file has a log beside it.

Nothing here runs anything. It says what to run; a job runs it.
"""

from collections.abc import Sequence

from app.adapters.duckdb.session import DuckdbSession
from app.adapters.protocol import AdapterError, BackupAvailability, BackupProgram
from app.core.translation import say

IMAGE = "python:3.14-slim"

# DuckDB's magic: eight bytes of checksum, then these four (checked on 2.0.0).
_MAGIC_AT = 8
_MAGIC = b"DUCK"

# One script for the three: copy the file out, copy a backup in, or say whether
# a backup is a DuckDB file. A refusal is a line the job reads, not a traceback.
_SCRIPT = """
import os, shutil, sys
what, source, target = sys.argv[1], sys.argv[2], sys.argv[3:]
def head(path):
    with open(path, "rb") as file:
        return file.read(12)
if what == "check":
    print("ok" if head(source)[8:12] == b"DUCK" else "not a DuckDB file")
    sys.exit(0)
guarded = source if what == "out" else target[0]
if os.path.exists(guarded + ".wal"):
    print("in use", file=sys.stderr)
    sys.exit(3)
if what == "out":
    shutil.copyfile(source, target[0])
else:
    making = target[0] + ".restoring"
    shutil.copyfile(source, making)
    os.replace(making, target[0])
"""


class DuckdbBackup:
    """How a DuckDB file is copied out and put back."""

    def __init__(self, session: DuckdbSession) -> None:
        self._session = session

    async def backup_availability(self) -> BackupAvailability:
        check = await self._session.check()
        if not check.ok:
            return BackupAvailability(available=False, reason=check.message)
        return BackupAvailability(available=True)

    async def backup_program(self, *, into: str) -> BackupProgram:
        """The file, its log written into it first, copied into a new one."""
        database = await self._database()
        await self._session.read(lambda reading: reading.value("CHECKPOINT"))
        return BackupProgram(
            image=IMAGE,
            argv=("python", "-I", "-c", _SCRIPT, "out", database, into),
            environment={},
        )

    async def restore_program(self, *, from_file: str) -> BackupProgram:
        """The backup, written over the file.

        Every table, view and row the file holds is replaced by the backup's,
        which is why the route that asks for it insists on being told so.
        """
        return BackupProgram(
            image=IMAGE,
            argv=("python", "-I", "-c", _SCRIPT, "in", from_file, await self._database()),
            environment={},
            writes_storage=True,
        )

    async def restore_inventory_program(self, *, from_file: str) -> BackupProgram:
        """Whether the backup begins as a DuckDB file does."""
        return BackupProgram(
            image=IMAGE,
            argv=("python", "-I", "-c", _SCRIPT, "check", from_file),
            environment={},
        )

    def validate_restore_inventory(self, lines: Sequence[str]) -> None:
        said = [line.strip() for line in lines if line.strip()]
        if not said or said[0] != "ok":
            raise ValueError(say("This file is not a DuckDB backup"))

    def restore_archive_reason(self, head: bytes) -> str | None:
        if head[_MAGIC_AT : _MAGIC_AT + len(_MAGIC)] == _MAGIC:
            return None
        return say("This file is not a DuckDB backup")

    async def _database(self) -> str:
        offer = await self.backup_availability()
        if not offer.available:
            raise ValueError(offer.reason)
        try:
            return self._session.path()
        except AdapterError as exc:
            raise ValueError(exc.message) from None
