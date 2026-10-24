"""How to open a SQLite file of a person's storage, and run work on it (D247).

Knows about the file, connections and driver errors, and nothing about what
the caller wants. The work itself is a plain function run on one connection
inside a worker thread: `sqlite3` blocks.
"""

import asyncio
import contextvars
import logging
import sqlite3
import threading
import time
from collections.abc import Callable, Mapping
from functools import partial
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

# Each of these reaches past the one file (D247). ATTACH is refused for any
# file with a name: VACUUM attaches a nameless temporary one to rebuild the
# file into, and VACUUM INTO attaches the file it writes, by name. One attached
# database is all VACUUM needs, and the limit holds it to that.
_DENIED_FUNCTIONS = frozenset({"load_extension", "fts3_tokenizer"})
_DENIED_PRAGMAS = frozenset({"temp_store_directory", "data_store_directory"})
# Settings this application makes on every connection, which a statement may
# read and may not change: a read's guard, the checks against a crafted file,
# and the foreign keys the file declares being enforced (D253).
_KEPT_PRAGMAS = frozenset(
    {"query_only", "writable_schema", "trusted_schema", "cell_size_check", "foreign_keys"}
)

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
    if action == sqlite3.SQLITE_ATTACH and first != "":
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_FUNCTION and (second or "").lower() in _DENIED_FUNCTIONS:
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_PRAGMA:
        name = (first or "").lower()
        if name in _DENIED_PRAGMAS or (name in _KEPT_PRAGMAS and second is not None):
            return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def _harden(connection: sqlite3.Connection, *, writes: bool) -> None:
    """What every connection is opened with, whatever it is for (D247, D253).

    The authorizer comes last: the settings before it are this application's,
    and it refuses a statement that tries to change them back.
    """
    connection.setlimit(sqlite3.SQLITE_LIMIT_ATTACHED, 1)
    connection.setconfig(sqlite3.SQLITE_DBCONFIG_DEFENSIVE, True)
    connection.setconfig(sqlite3.SQLITE_DBCONFIG_TRUSTED_SCHEMA, False)
    connection.setconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_FTS3_TOKENIZER, False)
    connection.setconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_LOAD_EXTENSION, False)
    connection.execute("PRAGMA cell_size_check = ON")
    connection.execute("PRAGMA foreign_keys = ON")
    if not writes:
        connection.execute("PRAGMA query_only = ON")
    connection.text_factory = _text
    connection.set_authorizer(_authorize)


_UNSAFE = {ord(character): None for character in ("\r", "\n", "\t", "\x00")}


def _sentence(text: str) -> str:
    """SQLite's own refusal, on one line and of a bounded length."""
    return text.translate(_UNSAFE).strip()[:500] or say("The source rejected the change")


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
        code = (getattr(exc, "sqlite_errorcode", None) or 0) & 0xFF
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
    """Statements on one open connection, inside the thread working on it."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def rows(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, Any]]:
        """A statement's rows, by column name."""
        cursor = self._connection.execute(sql, params)
        names = [column[0] for column in cursor.description or []]
        return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]

    def tuples(self, sql: str, params: tuple[object, ...] = ()) -> list[tuple[Any, ...]]:
        """A statement's rows by position: names may repeat, and `rowid` is one."""
        return list(self._connection.execute(sql, params).fetchall())

    def value(self, sql: str, params: tuple[object, ...] = ()) -> Any:
        """The first column of the first row, or nothing when there is no row."""
        row = self._connection.execute(sql, params).fetchone()
        return None if row is None else row[0]


class Handle:
    """One open connection, worked on from worker threads, one call at a time.

    The connection may move between threads because two calls never use it at
    once: the lock is that promise. A statement stops at its next look at the
    clock once its time is up or somebody stops it, which `stop` does from any
    task.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._lock = asyncio.Lock()
        self._deadline: float | None = None
        self._stopped = threading.Event()
        # Whether the last call was stopped by its clock rather than by `stop`.
        self.timed_out = False
        connection.set_progress_handler(self._tick, _PROGRESS_STEPS)

    def _tick(self) -> int:
        if self._stopped.is_set():
            return 1
        if self._deadline is not None and time.monotonic() > self._deadline:
            self.timed_out = True
            return 1
        return 0

    def stop(self) -> None:
        """Stop what runs now, and every call after it until `resume`."""
        self._stopped.set()

    def resume(self) -> None:
        self._stopped.clear()

    async def call[T](
        self, work: Callable[[sqlite3.Connection], T], *, seconds: float | None = None
    ) -> T:
        """Run `work` on the connection in a worker thread.

        A request that goes away stops the statement rather than leaving it to
        run to its end in a thread nobody waits for.
        """
        async with self._lock:
            self.timed_out = False
            self._deadline = None if seconds is None else time.monotonic() + seconds
            # run_in_executor carries no context variables, and the request's
            # language is one: a refusal worded in the thread would be English.
            context = contextvars.copy_context()
            future = asyncio.get_running_loop().run_in_executor(
                None, context.run, work, self._connection
            )
            try:
                return await asyncio.shield(future)
            except asyncio.CancelledError:
                self._stopped.set()
                # Nothing of the thread is wanted, its failure included, which
                # is read so that it is not reported as never retrieved.
                await asyncio.wait([future])
                if not future.cancelled():
                    future.exception()
                raise
            finally:
                self._deadline = None

    async def close(self) -> None:
        # A statement still running is stopped first, so closing does not
        # wait for it to finish.
        self._stopped.set()
        await self.call(lambda connection: connection.close())


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

    def _open(self, *, writes: bool, busy_seconds: float) -> sqlite3.Connection:
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
            timeout=busy_seconds,
            autocommit=True,
            # A handle is worked on from more than one worker thread, never
            # from two at once (`Handle`).
            check_same_thread=False,
        )
        try:
            _harden(connection, writes=writes)
        except BaseException:
            connection.close()
            raise
        return connection

    async def handle(
        self,
        *,
        writes: bool,
        busy_seconds: float = BUSY_SECONDS,
        fallback_message: str = N_("Query failed"),
    ) -> Handle:
        """A connection kept open by the caller, who closes it."""
        context = contextvars.copy_context()
        try:
            connection = await asyncio.get_running_loop().run_in_executor(
                None,
                context.run,
                partial(self._open, writes=writes, busy_seconds=busy_seconds),
            )
        except AdapterError:
            raise
        except sqlite3.Error as exc:
            error_kind, message = classify(exc, fallback_message=fallback_message)
            raise AdapterError(error_kind, message) from None
        return Handle(connection)

    async def read[T](
        self,
        work: Callable[[Reading], T],
        *,
        seconds: float | None = None,
        fallback_message: str = N_("Query failed"),
    ) -> T:
        """Run `work` on a connection that cannot write, and hand back its answer."""
        handle = await self.handle(writes=False, fallback_message=fallback_message)
        try:
            return await handle.call(
                lambda connection: work(Reading(connection)), seconds=seconds
            )
        except AdapterError:
            raise
        except sqlite3.Error as exc:
            error_kind, message = classify(exc, fallback_message=fallback_message)
            raise AdapterError(error_kind, message) from None
        finally:
            await handle.close()

    async def write[T](
        self,
        work: Callable[[sqlite3.Connection], T],
        *,
        refusals: Mapping[int, str] | None = None,
    ) -> T:
        """Run `work` as one transaction that holds the file's write lock from
        its first statement, committed when it returns (D254).

        IMMEDIATE, so nobody writes between what `work` reads and what it
        changes. A constraint the change breaks is the caller's to hear, as a
        ValueError naming it; anything else is the source failing.
        """

        def job(connection: sqlite3.Connection) -> T:
            connection.execute("BEGIN IMMEDIATE")
            try:
                answer = work(connection)
            except BaseException:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise
            connection.execute("COMMIT")
            return answer

        handle = await self.handle(writes=True, fallback_message=N_("Update failed"))
        try:
            return await handle.call(job)
        except sqlite3.Error as exc:
            extended = getattr(exc, "sqlite_errorcode", None) or 0
            named = (refusals or {}).get(extended)
            if named is not None:
                raise ValueError(say(named)) from None
            if extended & 0xFF == sqlite3.SQLITE_CONSTRAINT:
                raise ValueError(say("The source rejected the change")) from None
            error_kind, message = classify(exc, fallback_message=N_("Update failed"))
            raise AdapterError(error_kind, message) from None
        finally:
            await handle.close()

    async def restructure[T](
        self,
        work: Callable[[sqlite3.Connection], T],
        *,
        refusals: Mapping[int, str] | None = None,
    ) -> T:
        """Run `work` as one structure change, with foreign keys off for it (D255).

        A table is rebuilt by dropping the old one, and with foreign keys on
        that drop acts on every row pointing at it. They are switched off
        outside the transaction, as SQLite requires, by this application
        rather than by a statement: the authorizer is lifted for that one
        pragma and put back before the work runs.

        What SQLite refuses is said in its own sentence, as the console says
        it (D253): it names the view, the trigger or the column in the way.
        """

        def own(connection: sqlite3.Connection, statement: str) -> None:
            connection.set_authorizer(None)
            try:
                connection.execute(statement)
            finally:
                connection.set_authorizer(_authorize)

        def job(connection: sqlite3.Connection) -> T:
            own(connection, "PRAGMA foreign_keys = OFF")
            try:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    answer = work(connection)
                except BaseException:
                    if connection.in_transaction:
                        connection.execute("ROLLBACK")
                    raise
                connection.execute("COMMIT")
                return answer
            finally:
                own(connection, "PRAGMA foreign_keys = ON")

        handle = await self.handle(writes=True, fallback_message=N_("The structure could not be changed"))
        try:
            return await handle.call(job)
        except sqlite3.Error as exc:
            extended = getattr(exc, "sqlite_errorcode", None) or 0
            named = (refusals or {}).get(extended)
            if named is not None:
                raise ValueError(say(named)) from None
            if isinstance(exc, sqlite3.OperationalError | sqlite3.IntegrityError) and extended & 0xFF in (
                sqlite3.SQLITE_ERROR,
                sqlite3.SQLITE_CONSTRAINT,
            ):
                raise ValueError(_sentence(str(exc))) from None
            error_kind, message = classify(exc, fallback_message=N_("The structure could not be changed"))
            raise AdapterError(error_kind, message) from None
        finally:
            await handle.close()

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
