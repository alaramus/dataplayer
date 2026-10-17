"""A private bounded snapshot shared by archive inspection and restore (D122)."""

import logging
import tempfile
import uuid
from pathlib import Path

from app.adapters.explorer.storage import is_plain_name
from app.adapters.file.storage import LocalStorage
from app.core.config import settings
from app.core.translation import say
from app.jobs.runner import JobFailed
from app.users import storage

MAX_RESTORE_BYTES = 2 * 1024 * 1024 * 1024
RESTORE_PREFIX = ".dataplayer-restore-"
logger = logging.getLogger(__name__)


def snapshot(owner_id: uuid.UUID, filename: str) -> Path:
    if not is_plain_name(filename):
        raise JobFailed(say("The backup name is not a plain file name"))
    try:
        home = LocalStorage(storage.home_dir(owner_id))
        source = home.path_of(home.unlinked_place(f"backups/{filename}"))
        if not source.is_file() or source.stat().st_size > MAX_RESTORE_BYTES:
            raise JobFailed(say("The backup is missing or exceeds the 2 GiB restore limit"))
        with source.open("rb") as incoming:
            if incoming.read(5) != b"PGDMP":
                raise JobFailed(say("Restore requires a PostgreSQL custom archive"))
            incoming.seek(0)
            # A sibling of personal homes, inaccessible through their file sources.
            with tempfile.NamedTemporaryFile(
                prefix=RESTORE_PREFIX, suffix=".dump",
                dir=settings.USER_STORAGE_ROOT, delete=False,
            ) as outgoing:
                staged = Path(outgoing.name)
                try:
                    copied = 0
                    while block := incoming.read(1024 * 1024):
                        copied += len(block)
                        if copied > MAX_RESTORE_BYTES:
                            raise JobFailed(say("The backup exceeds the 2 GiB restore limit"))
                        outgoing.write(block)
                except BaseException:
                    outgoing.close()
                    staged.unlink(missing_ok=True)
                    raise
        return staged
    except (OSError, ValueError):
        raise JobFailed(say("The backup could not be read safely")) from None


def remove_stranded_snapshots() -> None:
    root = settings.USER_STORAGE_ROOT.resolve()
    for entry in root.glob(f"{RESTORE_PREFIX}*.dump"):
        if entry.is_file() and not entry.is_symlink() and entry.parent.resolve() == root:
            try:
                entry.unlink(missing_ok=True)
            except OSError:
                logger.warning("An interrupted restore snapshot could not be removed")
