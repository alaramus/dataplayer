"""Put sample files into a user's personal directory.

A development tool, not part of the API: this sub-project has no way to write
files, so a fresh directory would otherwise be empty and there would be
nothing to look at or to run an end-to-end scenario against.

    python -m app.seed_storage [email]
"""

import asyncio
import logging
import sys
from pathlib import Path

from app.core.config import settings
from app.core.db import async_session_maker, loop_factory
from app.users import crud, storage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# More than one page of the default size, so paging is exercised.
SAMPLE_ROWS = 250


def write_samples(home: Path) -> None:
    """Write one file of every outcome a reader can produce."""
    home.mkdir(mode=0o700, parents=True, exist_ok=True)

    rows = "\n".join(
        f"{index},city-{index},{index * 1000}" for index in range(1, SAMPLE_ROWS + 1)
    )
    (home / "sample.csv").write_text(
        f"id,name,population\n{rows}\n", encoding="utf-8"
    )
    (home / "sample.tsv").write_text(
        "id\tname\n1\tone\n2\ttwo\n", encoding="utf-8"
    )
    (home / "notes.txt").write_text(
        "\n".join(f"line {index}" for index in range(1, 21)) + "\n", encoding="utf-8"
    )
    # Binary on purpose: it must show up in the tree and refuse to be read.
    (home / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00sample")

    reports = home / "reports"
    reports.mkdir(exist_ok=True)
    (reports / "q3.csv").write_text("quarter,revenue\nQ3,1200\n", encoding="utf-8")
    (home / "empty").mkdir(exist_ok=True)


async def main(email: str) -> None:
    async with async_session_maker() as session:
        user = await crud.get_user_by_email(session=session, email=email)
    if user is None:
        logger.error("No such user: %s", email)
        raise SystemExit(1)

    home = storage.home_dir(user.id)
    write_samples(home)
    logger.info("Sample files written to %s", home)


if __name__ == "__main__":
    address = sys.argv[1] if len(sys.argv) > 1 else settings.FIRST_SUPERUSER
    asyncio.run(main(address), loop_factory=loop_factory)
