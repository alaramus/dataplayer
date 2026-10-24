"""How to open a SQLite file of a person's storage, and run work on it (D247).

Knows about the file, connections and driver errors, and nothing about what
the caller wants. The work itself is a plain function run on one connection
inside a worker thread: `sqlite3` blocks, and a connection belongs to the
thread that opened it.
"""

import asyncio
import contextvars
import logging
import sqlite3
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.adapters.file.storage import LocalStorage
from app.adapters.protocol import AdapterError, ConnectionCheckResult, ErrorKind
from app.adapters.sqlite.options import SqliteOptions
from app.core.logs import record_failure, with_ref
from app.core.translation import N_, say

logger = logging.getLogger(__name__)

# The oldest library this source reads with: `pragma_table_list` and STRICT
# tables arrived in 3.37.
OLDEST = (3, 37, 0)
# How long a statement waits for another connection's lock before giving up.
BUSY_SECONDS = 5.0
# How long several catalog reads may take altogether, as on PostgreSQL (D246).
INSPECTION_SECONDS = 5.0
# How many virtual machine steps pass between two looks at the clock.
_PROGRESS_STEPS = 1000

# Each of these reaches past the one file (D247). ATTACH and VACUUM INTO are
# also refused by the limit on attached databases; the authorizer says no
# before the limit is reached, for ATTACH and for DETACH.
_DENIED_FUNCTIONS = frozenset({"load_extension", "fts3_tokenizer"})
_DENIED_PRAGMAS = frozenset({"temp_store_directory", "data_store_directory"})

# Primary result codes, the low byte of an extended one.
_BUSY = frozenset({sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED})
_NOT_A_DATABASE = frozenset({sqlite3.SQLITE_NOTADB})
_DAMAGED = frozenset({sqlite3.SQLITE_CORRUPT})
_UNOPENABLE = frozenset({sqlite3.SQLITE_CANTOPEN})
_UNWRITABLE = frozenset({sqlite3.SQLITE_READONLY, sqlite3.SQLITE_PERM})


class Undecodable(bytes):
    """Text stored in the file that is not UTF-8, kept as its bytes (D250)."""


def _text(raw: bytes) -> str | Undecodable:
    try:
        return raw.decode()
    except UnicodeDecodeError:
        return Undecodable(raw)


def _authorize(
    action: int, first: str | None, second: str | None, _db: str | None, _trigger: str | None
) -> int:
    if action in (sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH):
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_FUNCTION and (second or "").lower() in _DENIED_FUNCTIONS:
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_PRAGMA and (first or "").lower() in _DENIED_PRAGMAS:
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def _harden(connection: sqlite3.Connection) -> None:
    """What every connection is opened with, whatever it is for (D247)."""
    connection.setlimit(sqlite3.SQLITE_LIMIT_ATTACHED, 0)
    connection.setconfig(sqlite3.SQLITE_DBCONFIG_DEFENSIVE, True)
    connection.setconfig(sqlite3.SQLITE_DBCONFIG_TRUSTED_SCHEMA, False)
    connection.setconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_FTS3_TOKENIZER, False)
    connection.setconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_LOAD_EXTENSION, False)
    connection.set_authorizer(_authorize)
    connection.execute("PRAGMA cell_size_check = ON")
    connection.text_factory = _text


def library_version() -> str:
    return sqlite3.sqlite_version


def library_supported() -> bool:
    return sqlite3.sqlite_version_info >= OLDEST


def classify(
    exc: BaseException, *, fallback_message: str = N_("Query failed")
) -> tuple[ErrorKind, str]:
    """Reduce a driver exception to a safe (kind, message) pair.

    By the result code rather than the text, for the reason a server's errors
    are read by number: the text can quote the statement and the data.
    """
    if isinstance(exc, sqlite3.Error):
        code = (exc.sqlite_errorcode or 0) & 0xFF
        if code in _BUSY:
            return "locked", say("The database file is locked by another connection")
        if code == sqlite3.SQLITE_INTERRUPT:
            return "timeout", say("The database did not answer in time")
        if code in _NOT_A_DATABASE:
            return "config", say("The file is not a SQLite database")
        if code in _DAMAGED:
            return "config", say("The database file is damaged")
        if code in _UNOPENABLE:
            return "config", say("The database file cannot be opened")
        if code in _UNWRITABLE:
            return "config", say("The database file cannot be written")
    ref = record_failure(logger, f"SQLite: {fallback_message}", exc)
    return "unknown", with_ref(say(fallback_message), ref)


class Reading:
    """Statements on one open connection, inside the thread that opened it."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def rows(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, Any]]:
        """A statement's rows, by column name."""
        cursor = self._connection.execute(sql, params)
        names = [column[0] for column in cursor.description or []]
        return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]

    def value(self, sql: str, params: tuple[object, ...] = ()) -> Any:
        """The first column of the first row, or nothing when there is no row."""
        row = self._connection.execute(sql, params).fetchone()
        return None if row is None else row[0]


class _Clock:
    """What stops a statement: a deadline passed, or the request gone."""

    def __init__(self, seconds: float | None) -> None:
        self._deadline = None if seconds is None else time.monotonic() + seconds
        self.cancelled = threading.Event()

    def __call__(self) -> int:
        if self.cancelled.is_set():
            return 1
        if self._deadline is not None and time.monotonic() > self._deadline:
            return 1
        return 0


class SqliteSession:
    """How to reach one database file of one person's storage."""

    def __init__(self, options: SqliteOptions, home_dir: Path) -> None:
        self._options = options
        self._storage = LocalStorage(home_dir)

    @property
    def options(self) -> SqliteOptions:
        return self._options

    def file_name(self) -> str:
        return self._options.parts[-1]

    def _file(self) -> Path:
        """Where the file is, judged by the file source's own rule (D8).

        Judged on every open rather than once, so a link put in place of the
        file afterwards is caught as well.
        """
        try:
            return self._storage.path_of(self._storage.place(self._options.path))
        except ValueError:
            raise AdapterError(
                "config", say("The path must stay inside your personal storage")
            ) from None

    def _open(self, *, writes: bool) -> sqlite3.Connection:
        path = self._file()
        if path.is_dir():
            raise AdapterError("config", say("The path names a folder, not a file"))
        if not path.exists():
            if not self._options.create:
                raise AdapterError("config", say("The database file does not exist"))
            if not path.parent.is_dir():
                raise AdapterError(
                    "config", say("The folder for the database file does not exist")
                )
        # rwc makes the file on first open, and only where the person asked.
        mode = "rwc" if self._options.create else "rw"
        connection = sqlite3.connect(
            f"{path.as_uri()}?mode={mode}",
            uri=True,
            timeout=BUSY_SECONDS,
            autocommit=True,
        )
        try:
            _harden(connection)
            if not writes:
                connection.execute("PRAGMA query_only = ON")
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
        """Run `work` on a connection that cannot write, and hand back its answer.

        A request that goes away stops the statement rather than leaving it to
        run to its end in a thread nobody waits for.
        """
        clock = _Clock(seconds)

        def job() -> T:
            connection = self._open(writes=False)
            try:
                connection.set_progress_handler(clock, _PROGRESS_STEPS)
                return work(Reading(connection))
            finally:
                connection.close()

        # run_in_executor carries no context variables, and the request's
        # language is one: a refusal worded in the thread would be English.
        context = contextvars.copy_context()
        future = asyncio.get_running_loop().run_in_executor(None, context.run, job)
        try:
            return await asyncio.shield(future)
        except asyncio.CancelledError:
            clock.cancelled.set()
            # The thread finishes at its next look at the clock; nothing of it
            # is wanted, its failure included, which is read so that it is not
            # reported as never retrieved.
            await asyncio.wait([future])
            if not future.cancelled():
                future.exception()
            raise
        except AdapterError:
            raise
        except sqlite3.Error as exc:
            error_kind, message = classify(exc, fallback_message=fallback_message)
            raise AdapterError(error_kind, message) from None

    async def inspection[T](self, work: Callable[[Reading], T]) -> T:
        """Several catalog reads on one connection, under one clock (D246)."""
        return await self.read(work, seconds=INSPECTION_SECONDS)

    async def check(self) -> ConnectionCheckResult:
        if not library_supported():
            return ConnectionCheckResult(
                ok=False,
                message=say(
                    "SQLite {version} is older than this source supports ({oldest})",
                    version=library_version(),
                    oldest=".".join(str(part) for part in OLDEST),
                ),
                error_kind="config",
            )
        started = time.perf_counter()
        try:
            # The header is read at the first statement, not at opening: this
            # is what finds a file that is not a database.
            await self.read(
                lambda reading: reading.value("SELECT count(*) FROM sqlite_schema"),
                seconds=INSPECTION_SECONDS,
                fallback_message=N_("Connection failed"),
            )
        except AdapterError as exc:
            return ConnectionCheckResult(
                ok=False, message=exc.message, error_kind=exc.error_kind
            )
        latency_ms = int((time.perf_counter() - started) * 1000)
        return ConnectionCheckResult(
            ok=True, message=say("Connection successful"), latency_ms=latency_ms
        )
