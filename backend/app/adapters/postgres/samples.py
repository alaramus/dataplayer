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

A database with TimescaleDB in it is filled with a different schema instead of
that one: the same kind of story — sites, meters, sensors and what they read —
told in hypertables, chunks, compression, continuous aggregates and policies,
with a few empty tables left with a time column in them, which is what the
conversion action turns into hypertables. A server somebody started for the
extension opening on a schema that says nothing about it demonstrates the
wrong thing.

Which schema it is, is asked of the database rather than of the template that
started it — a source is what it holds, discovered while it is open (D119,
D120) — so a PostgreSQL that gains the extension later is filled the same way.
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

# And what a database holding the extension gets instead of them. Two files
# rather than one because the second holds what cannot run inside a
# transaction: a refresh and a conversion to the columnstore are procedures
# that commit, and a script of several statements is one transaction to the
# driver whatever autocommit says.
TIMESCALE_SCRIPT_NAMES = (
    "timescale_schema.sql",
    "timescale_settle.sql",
)

# The schema the scripts own, and the only thing they touch. They drop it
# first, so running them twice is running them once.
SAMPLE_SCHEMA = "demo_lab"

SCRIPT_DIRECTORY = Path(__file__).parent / "sample_data"


def script_paths(directory: Path = SCRIPT_DIRECTORY) -> tuple[Path, ...]:
    return tuple(directory / name for name in SCRIPT_NAMES)


def timescale_script_paths(directory: Path = SCRIPT_DIRECTORY) -> tuple[Path, ...]:
    return tuple(directory / name for name in TIMESCALE_SCRIPT_NAMES)


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
        async with self._session.acquire() as connection:
            await connection.set_autocommit(True)
            # Asked before anything is read, because the answer says which
            # schema this database is getting.
            holds_timescale = await self._has_timescale(connection)
            for path in timescale_script_paths() if holds_timescale else script_paths():
                script = await to_thread.run_sync(_read, path)
                # No parameters at all, deliberately: psycopg treats a literal
                # `%` as a placeholder the moment any are supplied, and these
                # scripts contain them.
                await connection.execute(script)
            tables = await self._count_tables(connection)
            hypertables = await self._count_hypertables(connection) if holds_timescale else 0
        counted = f"{SAMPLE_SCHEMA}: {tables} tables"
        if hypertables == 0:
            return counted
        subject = "hypertable" if hypertables == 1 else "hypertables"
        return f"{counted}, including {hypertables} {subject}"

    async def _has_timescale(self, connection: psycopg.AsyncConnection[Any]) -> bool:
        """Whether this database holds the extension, asked of the database.

        Not of the service template that started it and not of the image: a
        connection is opened to databases nobody here started, and one of them
        can gain the extension after it was made (D120).
        """
        cursor = await connection.execute(
            "SELECT 1 FROM pg_extension WHERE extname = %s", ("timescaledb",)
        )
        return await cursor.fetchone() is not None

    async def _count_hypertables(self, connection: psycopg.AsyncConnection[Any]) -> int:
        cursor = await connection.execute(
            "SELECT count(*) FROM timescaledb_information.hypertables "
            "WHERE hypertable_schema = %s",
            (SAMPLE_SCHEMA,),
        )
        row = await cursor.fetchone()
        return int(row[0]) if row else 0

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
