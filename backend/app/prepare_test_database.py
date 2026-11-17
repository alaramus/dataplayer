"""Make the database the backend suite runs in, beside the application's own.

The suite deletes every user and connection when it ends, so it never runs in
the database a person works in. Its database is the application's with
`_test` after the name — `app_test` beside `app` — on the same server, and the
suite refuses one whose name does not end so.

    python -m app.prepare_test_database

Creates it when it is missing, then brings it to what prestart leaves in the
application's: the migrations, the agent's tables (D139) and `demo_lab`, which
part of the suite reads. Run by `scripts/prestart-dev.sh` on every development
start and by CI; safe to run again.
"""

import asyncio
import logging
import os
import re
import subprocess
import sys
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TEST_SUFFIX = "_test"
# A database name made here is written into CREATE DATABASE, so it is held to
# what needs no quoting rather than quoted.
_PLAIN_NAME = re.compile(r"[a-z_][a-z0-9_]*")


def database_name(url: str) -> str:
    return urlsplit(url).path.lstrip("/")


def suite_database_url(url: str) -> str:
    """The suite's database for the application's: its name with `_test` after
    it, the server, the user and the password the same. A name that already
    ends so is the suite's own."""
    parts = urlsplit(url)
    name = database_name(url)
    if name.endswith(TEST_SUFFIX):
        return url
    return urlunsplit(parts._replace(path=f"/{name}{TEST_SUFFIX}"))


async def _create_if_missing(url: str) -> bool:
    name = database_name(url)
    if not _PLAIN_NAME.fullmatch(name) or not name.endswith(TEST_SUFFIX):
        raise SystemExit(f"Refusing to prepare {name!r}: a test database is a plain name ending in {TEST_SUFFIX}")
    maintenance = urlunsplit(urlsplit(url)._replace(path="/postgres"))
    engine = create_async_engine(maintenance, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            found = await connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": name}
            )
            if found.first() is not None:
                return False
            # The name is checked above; CREATE DATABASE takes no parameter.
            await connection.execute(text(f'CREATE DATABASE "{name}"'))
            return True
    finally:
        await engine.dispose()


def main() -> None:
    from app.core.config import settings
    from app.core.db import loop_factory

    url = suite_database_url(str(settings.DATABASE_URL))
    created = asyncio.run(_create_if_missing(url), loop_factory=loop_factory)
    logger.info("%s %s", "Created" if created else "Found", database_name(url))
    # Each step reads DATABASE_URL afresh, so each is pointed at this database.
    environment = {**os.environ, "DATABASE_URL": url}
    for step in (
        ["-m", "alembic", "upgrade", "head"],
        ["-m", "app.prepare_checkpoints"],
        ["-m", "app.seed_database"],
    ):
        subprocess.run([sys.executable, *step], env=environment, check=True)


if __name__ == "__main__":
    main()
