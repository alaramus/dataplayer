"""Personal file storage of a user.

Every user owns one directory and nothing outside it. Adapters never compute
this path themselves: they are handed the resolved root, so the boundary has a
single definition and cannot be widened by a request.
"""

import os
import shutil
import uuid
from pathlib import Path

from app.core.config import settings


def home_dir(user_id: uuid.UUID) -> Path:
    return settings.USER_STORAGE_ROOT / str(user_id)


def create_home(user_id: uuid.UUID) -> Path:
    """Create the user's directory if it is not there yet.

    Idempotent: called both when a user is created and when the first
    superuser is bootstrapped, which may already exist.
    """
    home = home_dir(user_id)
    home.mkdir(mode=0o700, parents=True, exist_ok=True)
    return home


def remove_home(user_id: uuid.UUID) -> None:
    """Delete the user's directory and everything in it.

    Idempotent: a user whose directory was never created, or was removed
    already, is not an error.

    A symlink is left in place rather than followed. The server never creates
    one, `shutil.rmtree` refuses to recurse through it anyway, and deleting
    what it points at would reach outside the root — the boundary this module
    exists to hold. Blocking work: the caller runs it in a thread.
    """
    home = home_dir(user_id)
    if home.is_symlink() or not home.is_dir():
        return
    shutil.rmtree(home)


def used_bytes(directory: Path) -> int:
    """What the files below a directory take, links not followed (D324).

    Walked each time rather than kept: a SQLite file grows and a program in a
    container writes without telling the server. Blocking work.
    """
    total = 0
    pending = [directory]
    while pending:
        try:
            listing = os.scandir(pending.pop())
        except OSError:
            continue
        with listing:
            for item in listing:
                try:
                    if item.is_dir(follow_symlinks=False):
                        pending.append(Path(item.path))
                    elif item.is_file(follow_symlinks=False):
                        total += item.stat(follow_symlinks=False).st_size
                except OSError:
                    continue
    return total
