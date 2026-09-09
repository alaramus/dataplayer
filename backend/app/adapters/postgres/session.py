import asyncio
import time
import uuid
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager, nullcontext
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import psycopg
from psycopg import errors as e
from psycopg import sql
from psycopg.rows import dict_row
from psycopg_pool import PoolTimeout

from app.adapters.postgres.inspection import InspectionReader
from app.adapters.postgres.options import PostgresOptions, PostgresUserPassword
from app.adapters.postgres.pool import pool_for
from app.adapters.protocol import AdapterError, ConnectionCheckResult, ErrorKind
from app.adapters.resources import Pooling

CHECK_TIMEOUT_SECONDS = 5.0

# How this application introduces itself to the server it connects to.
APPLICATION_NAME = "dataplayer"

# Order matters: `role "x" does not exist` matches both sets, and it is a
# credentials problem rather than a configuration one.
_AUTH_MARKERS = ("password", "authentication", "role", "permission denied")
_CONFIG_MARKERS = ("does not exist",)


def classify(
    exc: BaseException, *, fallback_message: str = "Connection failed"
) -> tuple[ErrorKind, str]:
    """Reduce a driver exception to a safe (kind, message) pair.

    The exception text never reaches the caller: psycopg includes the
    connection string, password and all, in it.

    fallback_message covers everything that is not a connection problem. It is
    a parameter because "Connection failed" is misleading when the connection
    was fine and the query was not.
    """
    # ConnectionTimeout subclasses OperationalError, so it is checked first.
    if isinstance(exc, TimeoutError | psycopg.errors.ConnectionTimeout):
        return "timeout", "Connection timed out"
    if isinstance(exc, psycopg.OperationalError):
        text = str(exc).lower()
        if any(marker in text for marker in _AUTH_MARKERS):
            return "auth", "Authentication failed"
        if any(marker in text for marker in _CONFIG_MARKERS):
            return "config", "Database does not exist"
        return "network", "Could not reach the database server"
    return "unknown", fallback_message


def named_refusal(
    exc: BaseException, refusals: Mapping[str, str] | None
) -> str | None:
    """The caller's own sentence for a refusal it anticipated, or nothing.

    A SQLSTATE is safe to look at and the message beside it is not: PostgreSQL
    writes the offending value into the text of exactly the errors worth
    explaining. So the code is matched here and the wording belongs to whoever
    asked — only the caller knows that `42804` means "remove the default" in
    one command and something else in another.
    """
    if refusals is None or not isinstance(exc, psycopg.Error):
        return None
    return refusals.get(exc.sqlstate or "")


def compose_url(
    *, host: str, port: int | None = None, user: str = "", database: str = ""
) -> str:
    """A PostgreSQL address, from as many of its parts as there are.

    The one place that writes the grammar. Both the address of a finished
    connection and the one shown while a form is still being filled in come
    through here, so the two cannot drift apart in the quoting — which is how
    this would go wrong, and quietly. A part that is not there is left out
    rather than written empty: `postgresql://db:5432` is an address a person
    reads, and `postgresql://@db:5432/` is a puzzle.

    Quoted with `quote` rather than formatted in: a user named `ann@corp` or a
    database named `a/b` would otherwise move the host or invent a path, and
    this string is meant to be pasted into other tools.
    """
    authority = quote(host, safe="")
    if user != "":
        authority = f"{quote(user, safe='')}@{authority}"
    if port is not None:
        authority += f":{port}"
    if database == "":
        return f"postgresql://{authority}"
    return f"postgresql://{authority}/{quote(database, safe='')}"


def compose_url_with_password(
    *,
    host: str,
    port: int | None = None,
    user: str = "",
    database: str = "",
    password: str = "",
) -> str:
    """The same address with the password in it, for somebody to paste.

    Deliberately a second function rather than an argument to the first, so
    that "does this string carry a secret" is answered by which one was
    called. There is exactly one caller: the window that shows a started
    service's credentials once (D89).

    The password is quoted the way every other part is, so a generated one
    holding a character with meaning in a URL still parses on the other side.
    """
    plain = compose_url(host=host, port=port, user=user, database=database)
    if password == "":
        return plain
    secret = quote(password, safe="")
    if user == "":
        return plain.replace("://", f"://:{secret}@", 1)
    return plain.replace(f"{quote(user, safe='')}@", f"{quote(user, safe='')}:{secret}@", 1)


def options_from_url(url: str) -> dict[str, Any]:
    """A connection string taken apart into the fields of the form.

    The inverse of `connection_string`, and it lives here for the same reason
    that does: what a PostgreSQL address is made of is psycopg's rule, and
    stating it a second time on the client would be the defect ENGINEERING.md
    names. Nothing is opened.

    Three details, each of which is a bug if missed: libpq calls the database
    `dbname`, it answers with the port as a string, and it leaves `password`
    out rather than empty when the string carries none. The last one decides
    the variant.

    A string that names no host is refused: a connection string that does not
    say where to connect is not one, and libpq reads the empty string as an
    empty set of settings, which would silently blank the form.
    """
    try:
        parsed = psycopg.conninfo.conninfo_to_dict(url)
    except psycopg.Error:
        # The driver's message quotes the string back, and the string may
        # carry a password.
        raise ValueError("That is not a PostgreSQL connection string") from None

    host = parsed.get("host")
    if not isinstance(host, str) or host == "":
        raise ValueError("The connection string names no host")

    options: dict[str, Any] = {"host": host}
    for source, target in (("dbname", "database"), ("user", "user")):
        value = parsed.get(source)
        if isinstance(value, str) and value != "":
            options[target] = value

    port = parsed.get("port")
    if isinstance(port, str) and port != "":
        try:
            options["port"] = int(port)
        except ValueError:
            raise ValueError("The connection string names no usable port") from None

    password = parsed.get("password")
    if isinstance(password, str) and password != "":
        options["auth_method"] = "user_password"
        options["password"] = password
    else:
        options["auth_method"] = "no_auth"
    return options


# How long a rehearsal waits for the locks the real statement would take. It
# takes them for real, so it is not left waiting behind whoever is reading the
# table: a question about what would happen must not become an outage.
REHEARSAL_LOCK_TIMEOUT = "2s"


@dataclass(frozen=True)
class Rehearsal:
    """What the server said about a statement that was rolled back."""

    # One line per thing the server named, in its own words.
    said: list[str]
    # The caller's sentence for a refusal it anticipated, or nothing. Not an
    # error: a rehearsal that ends in a refusal has answered the question.
    refused: str | None


def _detail_lines(diagnostic: e.Diagnostic) -> list[str]:
    """The objects a diagnostic named, one per line.

    DETAIL only, and never read for meaning: PostgreSQL puts the list of
    objects there and writes only a count in the primary message. This is the
    field a refusal is allowed to pass on — the primary message of a failure
    is about the failure rather than about what was asked, and the text of an
    exception is what carries the connection string.
    """
    detail = diagnostic.message_detail
    if not detail:
        return []
    return [line.strip() for line in detail.splitlines() if line.strip()]


def _lines(diagnostic: e.Diagnostic) -> list[str]:
    """The same, falling back to the primary message of a notice.

    A notice about a single object writes it in the primary message and leaves
    DETAIL empty; a notice is the server describing what it did, so there is
    nothing there that a failure's text would carry.
    """
    lines = _detail_lines(diagnostic)
    if lines:
        return lines
    primary = diagnostic.message_primary
    return [primary] if primary else []


class Transaction:
    """Statements inside one open transaction.

    Deliberately thin: it exists so that a caller can run several changes as
    one, not so that it can grow a second query interface. Its errors are the
    session's errors, raised where the caller can still abandon the block.
    """

    def __init__(
        self,
        connection: psycopg.AsyncConnection[Any],
        refusals: Mapping[str, str] | None,
    ) -> None:
        self._connection = connection
        self._refusals = refusals

    async def change(
        self, sql: str, params: tuple[object, ...]
    ) -> list[dict[str, Any]]:
        cursor = await self._connection.cursor(row_factory=dict_row).execute(sql, params)
        return await cursor.fetchall()

    async def schema_change(self, sql: str) -> None:
        """Validated DDL inside this transaction, fetching nothing.

        `change` cannot stand in for it: a statement that produces no result
        makes `fetchall` raise, and the failure would be about the cursor
        rather than about the source. PostgreSQL rolls DDL back like anything
        else, which is what lets a relation and its first rows arrive together
        or not at all (D45).
        """
        await self._connection.execute(sql)

    async def change_many(
        self, sql: str, rows: Sequence[tuple[object, ...]]
    ) -> None:
        """One statement, run for every row, pipelined by the driver.

        Not one statement with a row list in it: PostgreSQL resolves the types
        of the parameters in a multi-row VALUES from the list itself, so text
        stays text and assigning it to an integer column is refused. A
        single-row VALUES is resolved against the target's own columns
        instead, which is the coercion every other write in this adapter
        relies on.
        """
        await self._connection.cursor().executemany(sql, rows)


class PostgresSession:
    """How to talk to a PostgreSQL server.

    Knows about connections, queries and driver errors, and nothing about what
    the caller wants: catalogs, fetching and everything after are built on top
    of this rather than inside it. In the old application both lived in one
    class, which reached 1243 lines even though backups, monitoring and
    extensions had already been moved out of it.
    """

    def __init__(
        self, options: PostgresOptions, pooling: Pooling | None = None
    ) -> None:
        self._options = options
        # Absent for a draft being checked, and for a session a test builds by
        # hand: then every query connects on its own, as everything did before
        # sub-project 4b.
        self._pooling = pooling

    def conninfo(self) -> str:
        options = self._options
        parts: dict[str, Any] = {
            "host": options.host,
            "port": options.port,
            "dbname": options.database,
            "user": options.user,
            # Without this psycopg waits about two minutes on an unreachable
            # host. asyncio.wait_for below would drop the wait, but the
            # connection would keep hanging inside the driver, so the limit is
            # set on both sides.
            "connect_timeout": int(CHECK_TIMEOUT_SECONDS),
            # Since connections now outlive a request, someone looking at
            # pg_stat_activity should be able to tell whose they are.
            "application_name": APPLICATION_NAME,
        }
        # The one place in the driver that knows there are variants at all. A
        # server configured with `trust` is not sent an empty password; it is
        # sent no password, which is a different conninfo.
        if isinstance(options, PostgresUserPassword):
            parts["password"] = options.password.get_secret_value()
        return psycopg.conninfo.make_conninfo(**parts)

    def conninfo_without_password(self) -> str:
        """Where this connects, for a program that is given the password apart.

        `pg_dump` takes a connection string as an argument and its password
        from the environment, and an argument is visible to anything that can
        list processes — so the two are separated here rather than at the call
        site, where somebody would eventually put them back together.
        """
        options = self._options
        return psycopg.conninfo.make_conninfo(
            host=options.host,
            port=options.port,
            dbname=options.database,
            user=options.user,
            application_name=APPLICATION_NAME,
        )

    def connection_string(self) -> str:
        """The same address as `conninfo`, as a URL and without the password.

        Written by `compose_url`, which is also what a form still being filled
        in is shown: one grammar, so the two cannot disagree.
        """
        options = self._options
        return compose_url(
            host=options.host,
            port=options.port,
            user=options.user,
            database=options.database,
        )

    async def check(self) -> ConnectionCheckResult:
        started = time.perf_counter()
        try:
            connection = await asyncio.wait_for(
                psycopg.AsyncConnection.connect(self.conninfo()),
                CHECK_TIMEOUT_SECONDS,
            )
            async with connection:
                await connection.execute("SELECT 1")
        except Exception as exc:
            error_kind, message = classify(exc)
            return ConnectionCheckResult(
                ok=False, message=message, error_kind=error_kind
            )
        latency_ms = int((time.perf_counter() - started) * 1000)
        return ConnectionCheckResult(
            ok=True, message="Connection successful", latency_ms=latency_ms
        )

    @asynccontextmanager
    async def _connection(self) -> AsyncIterator[psycopg.AsyncConnection[Any]]:
        """A connection to work on: from the pool when there is one."""
        if self._pooling is None:
            connection = await asyncio.wait_for(
                psycopg.AsyncConnection.connect(self.conninfo()),
                CHECK_TIMEOUT_SECONDS,
            )
            async with connection:
                yield connection
            return

        pool = await pool_for(self._pooling, self.conninfo())
        async with pool.connection() as connection:
            yield connection

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[psycopg.AsyncConnection[Any]]:
        """One connection, for a caller that owns its transaction.

        Everything else here runs a statement and hands back rows. A user's own
        query needs more than that: its own transaction, its own session
        settings, and something to cancel — so it borrows the connection and
        does the rest itself.
        """
        async with self._connection() as connection:
            yield connection

    async def query(
        self,
        sql: str,
        params: tuple[object, ...] | None = None,
        *,
        refusals: Mapping[str, str] | None = None,
        inspection: bool = False,
    ) -> list[dict[str, Any]]:
        """Run a read-only query.

        params stays None when there is nothing to bind: psycopg treats a
        supplied sequence, even an empty one, as a signal that the statement is
        parameterised, and then a literal % — as in LIKE 'pg_toast%' — is read
        as a placeholder.

        refusals names the SQLSTATEs this caller expects and what to say about
        each. A query can be refused for a reason that is about the request
        rather than about the source being unwell — asking whether one type
        converts to another, for instance — and that is a ValueError, not a
        502.
        """
        try:
            async with self._connection() as connection:
                boundary = connection.transaction() if inspection else nullcontext()
                async with boundary:
                    if inspection:
                        await connection.execute("SET TRANSACTION READ ONLY")
                        await connection.execute("SET LOCAL statement_timeout = '5s'")
                    cursor = await connection.cursor(row_factory=dict_row).execute(
                        sql, params
                    )
                    return await cursor.fetchall()
        except PoolTimeout:
            error_kind, message = await self._why_no_connection()
            raise AdapterError(error_kind, message) from None
        except Exception as exc:
            named = named_refusal(exc, refusals)
            if named is not None:
                raise ValueError(named) from None
            error_kind, message = classify(exc, fallback_message="Query failed")
            raise AdapterError(error_kind, message) from None

    @asynccontextmanager
    async def inspection(self) -> AsyncIterator[InspectionReader]:
        """Keep a multi-query plan on one bounded, read-only snapshot."""
        try:
            async with asyncio.timeout(5):
                async with self._connection() as connection:
                    async with connection.transaction():
                        await connection.execute(
                            "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
                        )
                        await connection.execute("SET LOCAL statement_timeout = '5s'")
                        yield InspectionReader(connection)
        except PoolTimeout:
            error_kind, message = await self._why_no_connection()
            raise AdapterError(error_kind, message) from None
        except psycopg.Error as exc:
            error_kind, message = classify(exc, fallback_message="Source inspection failed")
            raise AdapterError(error_kind, message) from None

    async def describe(self, sql: str) -> list[tuple[str, int]]:
        """The name and type OID of each column a statement returns.

        Asked of the server rather than declared beside the statement: a list
        of columns written by hand drifts from its statement the first time one
        of them changes (D55). The statement is executed, so a caller bounds it
        with LIMIT 0.
        """
        try:
            async with self._connection() as connection:
                cursor = await connection.execute(sql)
                return [
                    (column.name, column.type_code)
                    for column in cursor.description or []
                ]
        except PoolTimeout:
            error_kind, message = await self._why_no_connection()
            raise AdapterError(error_kind, message) from None
        except Exception as exc:
            error_kind, message = classify(exc, fallback_message="Describe failed")
            raise AdapterError(error_kind, message) from None

    async def stream_query(
        self,
        sql: str,
        params: tuple[object, ...] | None,
        *,
        batch_size: int,
    ) -> AsyncIterator[list[dict[str, Any]]]:
        """Read one query through a server-side cursor, one bounded batch at a time."""
        try:
            async with self._connection() as connection:
                async with connection.transaction():
                    async with connection.cursor(
                        name=f"dataplayer_export_{uuid.uuid4().hex}",
                        row_factory=dict_row,
                    ) as cursor:
                        await cursor.execute(sql, params)
                        while rows := await cursor.fetchmany(batch_size):
                            yield rows
        except PoolTimeout:
            error_kind, message = await self._why_no_connection()
            raise AdapterError(error_kind, message) from None
        except Exception as exc:
            error_kind, message = classify(exc, fallback_message="Export failed")
            raise AdapterError(error_kind, message) from None

    async def change(
        self,
        sql: str,
        params: tuple[object, ...],
        *,
        refusals: Mapping[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """Run a data change and keep rejected values separate from failures."""
        try:
            async with self._connection() as connection:
                cursor = await connection.cursor(row_factory=dict_row).execute(
                    sql, params
                )
                return await cursor.fetchall()
        except PoolTimeout:
            error_kind, message = await self._why_no_connection()
            raise AdapterError(error_kind, message) from None
        except (psycopg.DataError, psycopg.IntegrityError) as exc:
            # Constraint and conversion messages may quote source data and
            # schema details. The status is useful; the driver text is not.
            raise ValueError(
                named_refusal(exc, refusals) or "The source rejected the new value"
            ) from None
        except Exception as exc:
            error_kind, message = classify(exc, fallback_message="Update failed")
            raise AdapterError(error_kind, message) from None

    @asynccontextmanager
    async def transaction(
        self, *, refusals: Mapping[str, str] | None = None
    ) -> AsyncIterator[Transaction]:
        """Several statements on one connection, committed together or not at all.

        The one thing `change` cannot do. D26 got all-or-nothing out of a
        single statement with a CTE, which works while every row is being
        treated the same way; setting a different value in each row cannot be
        written that way without composing per-column casts into the
        statement, which is the boundary D2c draws.

        Leaving the block by any route other than the end rolls back, because
        the connection's own context manager commits only on a clean exit.
        """
        try:
            async with self._connection() as connection:
                async with connection.transaction():
                    yield Transaction(connection, refusals)
        except PoolTimeout:
            error_kind, message = await self._why_no_connection()
            raise AdapterError(error_kind, message) from None
        except (
            psycopg.DataError,
            psycopg.IntegrityError,
            psycopg.InternalError,
            psycopg.ProgrammingError,
        ) as exc:
            raise ValueError(
                named_refusal(exc, refusals) or "The source rejected the change"
            ) from None
        except psycopg.Error as exc:
            named = named_refusal(exc, refusals)
            if named is not None:
                raise ValueError(named) from None
            error_kind, message = classify(exc, fallback_message="Update failed")
            raise AdapterError(error_kind, message) from None

    async def schema_change(
        self, sql: str, *, refusals: Mapping[str, str] | None = None
    ) -> None:
        """Run validated DDL without pretending it returns rows.

        refusals names the SQLSTATEs this caller expects, so a refusal it
        anticipated arrives as its own sentence instead of the one below, which
        is all that can honestly be said about a code nobody claimed.
        """
        try:
            async with self._connection() as connection:
                await connection.execute(sql)
        except PoolTimeout:
            error_kind, message = await self._why_no_connection()
            raise AdapterError(error_kind, message) from None
        except (
            psycopg.DataError,
            psycopg.IntegrityError,
            psycopg.InternalError,
            psycopg.ProgrammingError,
        ) as exc:
            raise ValueError(
                named_refusal(exc, refusals) or "The source rejected the schema change"
            ) from None
        except Exception as exc:
            named = named_refusal(exc, refusals)
            if named is not None:
                raise ValueError(named) from None
            error_kind, message = classify(exc, fallback_message="Schema change failed")
            raise AdapterError(error_kind, message) from None

    async def rehearse(
        self, *statements: str, refusals: Mapping[str, str] | None = None
    ) -> Rehearsal:
        """Run statements, keep what the server said about them, and roll back.

        The only honest way to ask PostgreSQL what a cascade would take with
        it. The rules live in `pg_depend`, and restating them here would be a
        second implementation of them — wrong the first time an extension adds
        a kind of dependency, and wrong in the worst place, since the answer is
        read by somebody deciding whether to destroy something. So the drop is
        performed and then not kept, and what comes back is the server's own
        account of it.

        `force_rollback` is psycopg's, so nothing is committed by any route out
        of the block, including a clean one. Two kinds of answer are kept: the
        notices a successful statement raised, and, for a code the caller
        anticipated, the DETAIL of the refusal — which for a refused drop is
        the list of what stands in the way. Only that field, and only for a
        named code: the text of an exception is what carries the connection
        string, and none of it is passed on.

        A rehearsal takes the same locks the real statement would, so it is
        held to `REHEARSAL_LOCK_TIMEOUT` rather than left to wait behind
        whoever is reading the table.

        Several statements are run in the order they were given, in the one
        transaction, because that is the only way to rehearse something that is
        performed that way: dropping a view and the table under it succeeds
        together and is refused apart, and a preview that ran them apart would
        be an answer to a different question.
        """
        said: list[str] = []
        refused: str | None = None

        def keep(diagnostic: e.Diagnostic) -> None:
            said.extend(_lines(diagnostic))

        try:
            async with self._connection() as connection:
                connection.add_notice_handler(keep)
                try:
                    async with connection.transaction(force_rollback=True):
                        await connection.execute(
                            sql.SQL("SET LOCAL lock_timeout = {}")
                            .format(sql.Literal(REHEARSAL_LOCK_TIMEOUT))
                            .as_string()
                        )
                        for statement in statements:
                            await connection.execute(statement)
                except psycopg.Error as exc:
                    named = named_refusal(exc, refusals)
                    if named is None:
                        raise
                    refused = named
                    said = _detail_lines(exc.diag)
                finally:
                    connection.remove_notice_handler(keep)
        except PoolTimeout:
            error_kind, message = await self._why_no_connection()
            raise AdapterError(error_kind, message) from None
        except Exception as exc:
            error_kind, message = classify(exc, fallback_message="Rehearsal failed")
            raise AdapterError(error_kind, message) from None
        return Rehearsal(said=said, refused=refused)

    async def _why_no_connection(self) -> tuple[ErrorKind, str]:
        """Ask the server once, on the failure path, what is actually wrong.

        A pool that cannot connect reports only that it had nothing to hand
        out; the reason the attempt failed stays inside it. Reporting a typo in
        a password as an unreachable host would send the user to check the
        wrong thing, so one direct attempt buys the real answer. Nothing on the
        successful path pays for this.
        """
        try:
            connection = await asyncio.wait_for(
                psycopg.AsyncConnection.connect(self.conninfo()),
                CHECK_TIMEOUT_SECONDS,
            )
            async with connection:
                pass
        except Exception as exc:
            return classify(exc, fallback_message="Query failed")
        # The server is reachable and the credentials work, so the wait was for
        # a free connection rather than for the server.
        return "unknown", "All connections to this source are busy"
