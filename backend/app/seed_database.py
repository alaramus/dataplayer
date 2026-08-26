"""Load the development PostgreSQL schema and its sample rows.

This is a development tool, not part of the API or database migrations. The
fixture schema owns only ``demo_lab`` and may therefore be rebuilt on every
development start without touching the application's tables.

    python -m app.seed_database [/app/sql]
"""

import asyncio
import logging
import sys
from pathlib import Path

from app.core.db import engine, loop_factory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

FIXTURE_NAMES = (
    "postgres_complex_schema.sql",
    "postgres_complex_data.sql",
)


def fixture_paths(directory: Path) -> tuple[Path, ...]:
    """Return fixture files in the only order in which they are valid."""
    return tuple(directory / name for name in FIXTURE_NAMES)


async def main(directory: Path) -> None:
    async with engine.connect() as connection:
        connection = await connection.execution_options(isolation_level="AUTOCOMMIT")
        for path in fixture_paths(directory):
            await connection.exec_driver_sql(path.read_text(encoding="utf-8"))
            logger.info("Applied PostgreSQL development fixture: %s", path.name)


if __name__ == "__main__":
    fixture_directory = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/app/sql")
    asyncio.run(main(fixture_directory), loop_factory=loop_factory)
