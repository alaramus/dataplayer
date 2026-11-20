"""How to open a DuckDB file of a person's storage, and run work on it (D387, D388).

Knows about the file, the engine's configuration and driver errors, and
nothing about what the caller wants. The work itself is a plain function run
on one connection inside a worker thread: `duckdb` blocks.
"""

import asyncio
import contextvars
import logging
import os
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import duckdb

from app.adapters.duckdb.options import DuckdbOptions
from app.adapters.home_file import HomeFile
from app.adapters.protocol import AdapterError, ConnectionCheckResult, ErrorKind
from app.core.logs import record_failure, with_ref
from app.core.translation import N_, say

logger = logging.getLogger(__name__)

# How long several catalog reads may take altogether, as on PostgreSQL (D246).
INSPECTION_SECONDS = 5.0

# The same for every open of every file: DuckDB refuses a second open of a
# file in this process with a configuration other than the first's (D387).
# There is no temp directory, so a sort too big for memory fails rather than
# spilling beside the file into the person's storage (D388).
_CONFIG: dict[str, str | bool | int | float | list[str]] = {
    "autoinstall_known_extensions": False,
    "autoload_known_extensions": False,
    "allow_community_extensions": False,
    "allow_unsigned_extensions": False,
    # `INSTALL` downloads from the network whatever external access says, into
    # `~/.duckdb/extensions` — which is the person's storage once `~` is their
    # home (checked on 2.0.0). A directory outside every allowed one is refused
    # before anything is fetched. It is never made.
    "extension_directory": str(Path(tempfile.gettempdir()) / "dataplayer-no-extensions"),
    "memory_limit": "1GB",
    "threads": 2,
    "temp_directory": "",
}
_NETWORK_FILESYSTEMS = "HTTPFileSystem,S3FileSystem"

# Two opens of one file share DuckDB's instance, and the first one seals its
# configuration: the look at whether it is sealed and the sealing are one step.
_SEALING = threading.Lock()


def library_version() -> str:
    return duckdb.__version__


def _seal(connection: duckdb.DuckDBPyConnection, home: Path) -> None:
    """Lock the engine to the owner's home before anything of the file runs (D388).

    Each setting is global, so a second connection to the same instance has
    them too; `allowed_directories` cannot be given at opening at all.
    """
    sealed = connection.execute("SELECT current_setting('lock_configuration')").fetchone()
    if sealed is not None and sealed[0]:
        return
    connection.execute("SET GLOBAL TimeZone = 'UTC'")
    connection.execute("SET GLOBAL home_directory = ?", [str(home)])
    connection.execute("SET allowed_directories = ?", [[str(home) + os.sep]])
    connection.execute("SET disabled_filesystems = ?", [_NETWORK_FILESYSTEMS])
    connection.execute("SET enable_external_access = false")
    connection.execute("SET lock_configuration = true")


def _is_a_file(connection: duckdb.DuckDBPyConnection) -> bool:
    """Whether DuckDB opened the file as a database.

    Handed a path ending in `.csv` or `.parquet`, DuckDB opens an empty
    database in memory instead of refusing (checked on 2.0.0).
    """
    row = connection.execute(
        "SELECT path FROM duckdb_databases() WHERE database_name = current_database()"
    ).fetchone()
    return row is not None and row[0] is not None


def classify(
    exc: BaseException, *, fallback_message: str = N_("Query failed")
) -> tuple[ErrorKind, str]:
    """Reduce a driver exception to a safe (kind, message) pair.

    By the exception's class, and for a lock by its text, which is read and
    never shown: DuckDB's messages name paths of the server.
    """
    if isinstance(exc, duckdb.InterruptException):
        return "timeout", say("The database did not answer in time")
    if isinstance(exc, duckdb.ConnectionException) or (
        isinstance(exc, duckdb.IOException) and "lock" in str(exc).lower()
    ):
        return "locked", say("The database file is in use by another program")
    if isinstance(exc, duckdb.PermissionException):
        return "config", say("The database reaches past your personal storage, which is refused")
    ref = record_failure(logger, f"DuckDB: {fallback_message}", exc)
    return "unknown", with_ref(say(fallback_message), ref)


class Reading:
    """Statements on one open connection, inside the thread working on it."""

    def __init__(self, connection: duckdb.DuckDBPyConnection) -> None:
        self._connection = connection

    def rows(self, sql: str, params: list[object] | None = None) -> list[dict[str, Any]]:
        """A statement's rows, by column name."""
        cursor = self._connection.execute(sql, params or [])
        names = [column[0] for column in cursor.description or []]
        return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]

    def tuples(self, sql: str, params: list[object] | None = None) -> list[tuple[Any, ...]]:
        """A statement's rows by position: a page's names may repeat."""
        return list(self._connection.execute(sql, params or []).fetchall())

    def value(self, sql: str, params: list[object] | None = None) -> Any:
        """The first column of the first row, or nothing when there is no row."""
        row = self._connection.execute(sql, params or []).fetchone()
        return None if row is None else row[0]


class _Call:
    """One open, its work and its close, which the event loop may stop."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._connection: duckdb.DuckDBPyConnection | None = None
        self._stopped = False
        # Whether the work was stopped by its clock rather than by its caller.
        self.timed_out = False

    def opened(self, connection: duckdb.DuckDBPyConnection) -> None:
        with self._lock:
            self._connection = connection
            stopped = self._stopped
        if stopped:
            connection.interrupt()

    def stop(self, *, timed_out: bool = False) -> None:
        """Interrupt the statement running now; `interrupt` works from any thread."""
        with self._lock:
            self._stopped = True
            self.timed_out = self.timed_out or timed_out
            connection = self._connection
        if connection is not None:
            connection.interrupt()

    @property
    def stopped(self) -> bool:
        with self._lock:
            return self._stopped


class DuckdbSession:
    """How to reach one database file of one person's storage."""

    def __init__(self, options: DuckdbOptions, home_dir: Path) -> None:
        self._options = options
        self._home_file = HomeFile(home_dir, options.path, create=options.create)

    @property
    def options(self) -> DuckdbOptions:
        return self._options

    def _open(self) -> duckdb.DuckDBPyConnection:
        """The file opened and sealed, each time anew (D387).

        Held open, the file would be locked against every other program for as
        long as the server lives.
        """
        path = self._home_file.to_open()
        with _SEALING:
            try:
                connection = duckdb.connect(str(path), config=_CONFIG)
            except duckdb.Error as exc:
                error_kind, message = classify(exc)
                if error_kind == "unknown":
                    # Not a database, written by a newer DuckDB, damaged, or a
                    # SQLite file whose reader is an extension this engine will
                    # not load: what the file is, never the driver's text.
                    raise AdapterError(
                        "config", say("The file is not a DuckDB database this server can read")
                    ) from None
                raise AdapterError(error_kind, message) from None
            try:
                _seal(connection, self._home_file.home)
                if not _is_a_file(connection):
                    raise AdapterError(
                        "config", say("The file is not a DuckDB database this server can read")
                    )
            except BaseException:
                connection.close()
                raise
        return connection

    async def read[T](
        self,
        work: Callable[[Reading], T],
        *,
        seconds: float | None = None,
        fallback_message: str = N_("Query failed"),
    ) -> T:
        """Run `work` on the file in a worker thread, and hand back its answer.

        A request that goes away interrupts the statement rather than leaving
        it to run to its end in a thread nobody waits for.
        """
        call = _Call()

        def job() -> T:
            connection = self._open()
            try:
                call.opened(connection)
                if call.stopped:
                    raise duckdb.InterruptException("stopped before it started")
                return work(Reading(connection))
            finally:
                connection.close()

        loop = asyncio.get_running_loop()
        # run_in_executor carries no context variables, and the request's
        # language is one: a refusal worded in the thread would be English.
        context = contextvars.copy_context()
        future = loop.run_in_executor(None, context.run, job)
        timer = (
            None if seconds is None else loop.call_later(seconds, lambda: call.stop(timed_out=True))
        )
        try:
            return await asyncio.shield(future)
        except asyncio.CancelledError:
            call.stop()
            # Nothing of the thread is wanted, its failure included, which is
            # read so that it is not reported as never retrieved.
            await asyncio.wait([future])
            if not future.cancelled():
                future.exception()
            raise
        except (AdapterError, ValueError):
            raise
        except duckdb.Error as exc:
            error_kind, message = classify(exc, fallback_message=fallback_message)
            raise AdapterError(error_kind, message) from None
        finally:
            if timer is not None:
                timer.cancel()

    async def inspection[T](self, work: Callable[[Reading], T]) -> T:
        """Several catalog reads on one connection, under one clock (D246)."""
        return await self.read(work, seconds=INSPECTION_SECONDS)

    async def check(self) -> ConnectionCheckResult:
        started = time.perf_counter()
        try:
            await self.read(
                lambda reading: reading.value("SELECT count(*) FROM duckdb_tables()"),
                seconds=INSPECTION_SECONDS,
                fallback_message=N_("Connection failed"),
            )
        except AdapterError as exc:
            return ConnectionCheckResult(ok=False, message=exc.message, error_kind=exc.error_kind)
        latency_ms = int((time.perf_counter() - started) * 1000)
        return ConnectionCheckResult(
            ok=True, message=say("Connection successful"), latency_ms=latency_ms
        )
