"""Something worth looking at, put into an empty server.

A database this application started for somebody is empty, and an empty
database demonstrates nothing: the catalog has one schema in it, the grid has
no rows to page through, and every screen the application is made of says
"nothing here". So a server started automatically is filled.

What it is filled with is the schema this project already uses to develop
against — enums, domains, composite types, generated columns, arrays, ranges,
partitions, foreign keys and a few hundred rows — and it is the same two files
rather than a second copy of them. They ship inside this package, next to the
driver that runs them, because the same script is now both a development
fixture and something the application does at a user's request.
"""

from pathlib import Path
from typing import Any

import psycopg
from anyio import to_thread

from app.adapters.postgres.session import PostgresSession

# In the only order in which they are valid: the schema, then the rows.
SCRIPT_NAMES = (
    "postgres_complex_schema.sql",
    "postgres_complex_data.sql",
)

# The schema the scripts own, and the only thing they touch. They drop it
# first, so running them twice is running them once.
SAMPLE_SCHEMA = "demo_lab"

SCRIPT_DIRECTORY = Path(__file__).parent / "sample_data"


def script_paths(directory: Path = SCRIPT_DIRECTORY) -> tuple[Path, ...]:
    return tuple(directory / name for name in SCRIPT_NAMES)


class PostgresSamples:
    """Filling a PostgreSQL server with the sample schema.

    Not an action and not a route: it is offered only where this server has
    just started the database itself (D80). Running somebody else's script
    against somebody else's server is what the query console is for, with the
    unlock and the confirmation that go with it.
    """

    def __init__(self, session: PostgresSession) -> None:
        self._session = session

    async def install_sample_data(self) -> str:
        """Run the scripts, and say what is now there.

        Each file is one statement to the driver — they are written as scripts
        with their own `BEGIN`/`COMMIT` — so nothing here splits SQL, and the
        text is this repository's own rather than anything a client sent.
        """
        scripts = [
            await to_thread.run_sync(_read, path) for path in script_paths()
        ]
        async with self._session.acquire() as connection:
            await connection.set_autocommit(True)
            for script in scripts:
                # No parameters at all, deliberately: psycopg treats a literal
                # `%` as a placeholder the moment any are supplied, and these
                # scripts contain them.
                await connection.execute(script)
            tables = await self._count_tables(connection)
        return f"{SAMPLE_SCHEMA}: {tables} tables"

    async def _count_tables(self, connection: psycopg.AsyncConnection[Any]) -> int:
        cursor = await connection.execute(
            "SELECT count(*) FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = %s AND c.relkind IN ('r', 'p')",
            (SAMPLE_SCHEMA,),
        )
        row = await cursor.fetchone()
        return int(row[0]) if row else 0


def _read(path: Path) -> str:
    """One script, off the disk in a worker thread."""
    return path.read_text(encoding="utf-8")
