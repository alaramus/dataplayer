"""Put sample files into a user's personal directory, and tidy up after tests.

A development tool, not part of the API: a fresh directory is empty, so there
would be nothing to look at or to run an end-to-end scenario against. It also
removes the directories of users that no longer exist, which is what the test
suite leaves behind every time it empties the shared development database.

    python -m app.seed_storage [email]
"""

import asyncio
import logging
import sys
import uuid

from app.adapters.explorer.samples import write_samples
from app.adapters.sqlite.samples import SAMPLE_FILE, write_sample_database
from app.core.config import settings
from app.core.db import async_session_maker, loop_factory
from app.users import crud, storage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def remove_orphan_homes(*, keep: set[uuid.UUID]) -> list[uuid.UUID]:
    """Delete the home directories of users that no longer exist.

    The test suite shares the development database and empties the user table,
    so every run strands a full directory under an id nobody can log in as.

    This decides *which* homes go; `storage.remove_home` is what takes one
    away, so where a home lives and how it is removed keep one definition. Only
    a real directory named after a user id is a candidate: anything else under
    the root was put there for a reason this script does not know, and guessing
    about it is the one destructive mistake it could make.
    """
    root = settings.USER_STORAGE_ROOT
    if not root.is_dir():
        return []

    removed: list[uuid.UUID] = []
    for entry in sorted(root.iterdir()):
        if entry.is_symlink() or not entry.is_dir():
            logger.info("Not a home directory, left alone: %s", entry.name)
            continue
        try:
            user_id = uuid.UUID(entry.name)
        except ValueError:
            logger.info("Name is not a user id, left alone: %s", entry.name)
            continue
        if user_id in keep:
            continue
        storage.remove_home(user_id)
        removed.append(user_id)
        logger.info("Removed the home of a user that no longer exists: %s", entry.name)
    return removed


async def main(email: str) -> None:
    async with async_session_maker() as session:
        user = await crud.get_user_by_email(session=session, email=email)
        live_ids = await crud.get_all_user_ids(session=session)
    if user is None:
        logger.error("No such user: %s", email)
        raise SystemExit(1)

    removed = remove_orphan_homes(keep=live_ids)
    logger.info("Removed %d orphaned home directories", len(removed))

    home = storage.home_dir(user.id)
    write_samples(home)
    write_sample_database(home / SAMPLE_FILE)
    logger.info("Sample files written to %s", home)


if __name__ == "__main__":
    address = sys.argv[1] if len(sys.argv) > 1 else settings.FIRST_SUPERUSER
    asyncio.run(main(address), loop_factory=loop_factory)
