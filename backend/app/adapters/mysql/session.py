"""How to talk to a MySQL or MariaDB server.

Knows about connections, statements and driver errors, and nothing about what
the caller wants; the catalog, the rows and everything after are built on it.
"""

import asyncio
import logging
import re
import ssl
import time
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import quote, unquote, urlsplit

import aiomysql
import pymysql

from app.adapters.mysql.options import MysqlOptions, MysqlUserPassword
from app.adapters.mysql.pool import PoolExhausted, pool_for
from app.adapters.protocol import AdapterError, ConnectionCheckResult, ErrorKind
from app.adapters.resources import Pooling
from app.core.logs import record_failure, with_ref
from app.core.translation import N_, say

logger = logging.getLogger(__name__)

CHECK_TIMEOUT_SECONDS = 5.0

Flavour = Literal["mysql", "mariadb"]

# The oldest of each that this source speaks to (D228). Below them the
# catalog's own tables lack what it reads — CHECK_CONSTRAINTS arrived in MySQL
# 8.0.16 — and a source half working is worse than one that says no.
OLDEST: dict[Flavour, tuple[int, ...]] = {"mysql": (8, 0, 16), "mariadb": (10, 6)}

# MySQL error numbers rather than their text: the text quotes the user, the
# host and sometimes the statement, and only the number is safe to look at.
_AUTH_ERRORS = frozenset({1044, 1045, 1698, 1251})
_CONFIG_ERRORS = frozenset({1049})
_NETWORK_ERRORS = frozenset({2002, 2003, 2005, 2006, 2013, 2055})

# Encrypted when the server can, and not refused when it cannot: libpq's
# `prefer`, which is what a PostgreSQL connection gets without asking. The
# server's certificate is not verified, so this keeps a password off the wire
# without proving who is on the other end. MySQL 8 signs in with
# caching_sha2_password, which over plain TCP needs the server's public key
# fetched first; over TLS it does not.
_PREFERRED_TLS = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
_PREFERRED_TLS.check_hostname = False
_PREFERRED_TLS.verify_mode = ssl.CERT_NONE

# Every TIMESTAMP is read in UTC and carried with its offset (D230). DATETIME
# is not converted by the server at all, so it is shown as written.
_SESSION_SETUP = "SET time_zone = '+00:00'"


@dataclass(frozen=True)
class ServerProfile:
    """Which server this is and what it numbers itself."""

    flavour: Flavour
    version: tuple[int, ...]
    # "8.4.11", "11.4.13": the number and nothing else.
    text: str

    @property
    def mariadb(self) -> bool:
        return self.flavour == "mariadb"

    @property
    def supported(self) -> bool:
        oldest = OLDEST[self.flavour]
        return self.version[: len(oldest)] >= oldest


_VERSION = re.compile(r"(\d+(?:\.\d+)*)")


def read_profile(version: str) -> ServerProfile:
    """The server's VERSION(), read as a flavour and a number.

    MariaDB writes its name into the string and MySQL does not; a fork that
    calls itself MySQL is spoken to as MySQL.
    """
    found = _VERSION.search(version)
    text = found.group(1) if found else "0"
    flavour: Flavour = "mariadb" if "mariadb" in version.lower() else "mysql"
    return ServerProfile(
        flavour=flavour,
        version=tuple(int(part) for part in text.split(".")),
        text=text,
    )


def classify(
    exc: BaseException, *, fallback_message: str = N_("Connection failed")
) -> tuple[ErrorKind, str]:
    """Reduce a driver exception to a safe (kind, message) pair.

    The exception text never reaches the caller, for the reason PostgreSQL's
    does not; what is not a connection problem is logged in full, masked, and
    answered with a ref (D184).
    """
    if isinstance(exc, TimeoutError):
        return "timeout", say("Connection timed out")
    if isinstance(exc, pymysql.err.MySQLError) and exc.args:
        code = exc.args[0]
        if code in _AUTH_ERRORS:
            return "auth", say("Authentication failed")
        if code in _CONFIG_ERRORS:
            return "config", say("Database does not exist")
        if code in _NETWORK_ERRORS:
            return "network", say("Could not reach the database server")
    if isinstance(exc, OSError | ssl.SSLError):
        return "network", say("Could not reach the database server")
    ref = record_failure(logger, f"MySQL: {fallback_message}", exc)
    return "unknown", with_ref(say(fallback_message), ref)


def named_refusal(
    exc: BaseException, refusals: Mapping[int, str] | None
) -> str | None:
    """The caller's own sentence for an error number it anticipated, or nothing."""
    if refusals is None or not isinstance(exc, pymysql.err.MySQLError) or not exc.args:
        return None
    named = refusals.get(exc.args[0])
    return None if named is None else say(named)


def compose_url(
    *, host: str, port: int | None = None, user: str = "", database: str = ""
) -> str:
    """A MySQL address, from as many of its parts as there are.

    The one place that writes the grammar, quoted part by part for the reason
    PostgreSQL's is: a user named `ann@corp` would otherwise move the host.
    """
    authority = quote(host, safe="")
    if user != "":
        authority = f"{quote(user, safe='')}@{authority}"
    if port is not None:
        authority += f":{port}"
    if database == "":
        return f"mysql://{authority}"
    return f"mysql://{authority}/{quote(database, safe='')}"


def compose_url_with_password(
    *,
    host: str,
    port: int | None = None,
    user: str = "",
    database: str = "",
    password: str = "",
) -> str:
    """The same address with the password in it, for somebody to paste (D89)."""
    plain = compose_url(host=host, port=port, user=user, database=database)
    if password == "":
        return plain
    secret = quote(password, safe="")
    if user == "":
        return plain.replace("://", f"://:{secret}@", 1)
    named = quote(user, safe="")
    return plain.replace(f"{named}@", f"{named}:{secret}@", 1)


_SCHEMES = ("mysql", "mariadb")


def options_from_url(url: str) -> dict[str, Any]:
    """A connection string taken apart into the fields of the form.

    `mariadb://` is read as `mysql://`, since one source speaks to both. A
    password in the string decides the variant, as it does for PostgreSQL.
    """
    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except ValueError:
        raise ValueError(say("The connection string names no usable port")) from None
    if parts.scheme.lower() not in _SCHEMES:
        raise ValueError(say("That is not a MySQL connection string"))
    if not parts.hostname:
        raise ValueError(say("The connection string names no host"))

    options: dict[str, Any] = {"host": unquote(parts.hostname)}
    if port is not None:
        options["port"] = port
    if parts.username:
        options["user"] = unquote(parts.username)
    database = unquote(parts.path.lstrip("/"))
    if database:
        options["database"] = database
    if parts.password:
        options["auth_method"] = "user_password"
        options["password"] = unquote(parts.password)
    else:
        options["auth_method"] = "no_password"
    return options


def quoted_name(*parts: str) -> str:
    """A name quoted for MySQL, each part apart: `db`.`table`, to be read.

    Backticks rather than double quotes, which are a string literal unless the
    server runs with ANSI_QUOTES: a filter written with them compares two
    constants and quietly matches everything or nothing.
    """
    return ".".join("`" + part.replace("`", "``") + "`" for part in parts)


def identifier(*parts: str) -> str:
    """The same name, to be sent inside a statement.

    A `%` is doubled because every statement here is sent with parameters, and
    the driver formats the whole text with `%` whether or not a placeholder is
    in it: a column named `100%` would otherwise break the statement.
    """
    return quoted_name(*parts).replace("%", "%%")


class MysqlSession:
    """How to talk to one MySQL or MariaDB server."""

    def __init__(self, options: MysqlOptions, pooling: Pooling | None = None) -> None:
        self._options = options
        self._pooling = pooling
        self._profile: ServerProfile | None = None

    @property
    def options(self) -> MysqlOptions:
        return self._options

    def _password(self) -> str:
        if not isinstance(self._options, MysqlUserPassword):
            return ""
        # aiomysql encodes the password as Latin-1, which cannot hold most of
        # the world's letters; the server compares the UTF-8 bytes. Handing it
        # those bytes spelt as Latin-1 makes its encoding produce them back.
        return self._options.password.get_secret_value().encode().decode("latin-1")

    def _connect_arguments(self) -> dict[str, Any]:
        options = self._options
        return {
            "host": options.host,
            "port": options.port,
            "user": options.user,
            "password": self._password(),
            "db": options.database or None,
            "charset": "utf8mb4",
            "autocommit": True,
            "connect_timeout": CHECK_TIMEOUT_SECONDS,
            "init_command": _SESSION_SETUP,
            "ssl": _PREFERRED_TLS,
        }

    def connection_string(self) -> str:
        options = self._options
        return compose_url(
            host=options.host,
            port=options.port,
            user=options.user,
            database=options.database,
        )

    def database(self) -> str:
        """The database the connection names, or nothing when it names none."""
        return self._options.database

    async def _direct(self) -> aiomysql.Connection:
        return await asyncio.wait_for(
            aiomysql.connect(**self._connect_arguments()), CHECK_TIMEOUT_SECONDS
        )

    @asynccontextmanager
    async def _connection(self) -> AsyncIterator[aiomysql.Connection]:
        """A connection to work on: from the pool when there is one."""
        pool = None
        if self._pooling is not None:
            options = self._options
            # What makes two pools different, and nothing about the request.
            fingerprint = (
                f"{options.host}:{options.port}:{options.user}:{options.database}:"
                f"{self._password()}"
            )
            pool = await pool_for(self._pooling, fingerprint, self._connect_arguments())
        if pool is None:
            connection = await self._direct()
            try:
                yield connection
            finally:
                connection.close()
            return
        async with pool.connection() as connection:
            yield connection

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[aiomysql.Connection]:
        """One connection, for a caller that owns its transaction and settings."""
        try:
            async with self._connection() as connection:
                yield connection
        except PoolExhausted:
            raise AdapterError("timeout", say("No connection was free for this query")) from None

    async def kill_query(self, thread_id: int) -> None:
        """Stop the statement one connection is running, from a second one.

        The connection under the statement is busy reading its answer, so the
        request cannot travel on it. Failing to kill is not reported: the
        statement then ends by itself, and its own outcome says so.
        """
        try:
            connection = await self._direct()
        except Exception:
            return
        try:
            async with connection.cursor() as cursor:
                await cursor.execute("KILL QUERY %s", (int(thread_id),))
        except Exception:
            # The statement may have finished first, which is the outcome anyway.
            pass
        finally:
            connection.close()

    async def profile(self) -> ServerProfile:
        """Which server this is; asked once per session and kept."""
        if self._profile is None:
            rows = await self.query("SELECT VERSION() AS version")
            self._profile = read_profile(str(rows[0]["version"]))
        return self._profile

    async def check(self) -> ConnectionCheckResult:
        started = time.perf_counter()
        try:
            connection = await self._direct()
            try:
                async with connection.cursor() as cursor:
                    await cursor.execute("SELECT VERSION()", ())
                    version = (await cursor.fetchone())[0]
            finally:
                connection.close()
        except Exception as exc:
            error_kind, message = classify(exc)
            return ConnectionCheckResult(ok=False, message=message, error_kind=error_kind)
        profile = read_profile(str(version))
        if not profile.supported:
            oldest = ".".join(str(part) for part in OLDEST[profile.flavour])
            return ConnectionCheckResult(
                ok=False,
                message=say(
                    "{server} {version} is older than this source supports ({oldest})",
                    server="MariaDB" if profile.mariadb else "MySQL",
                    version=profile.text,
                    oldest=oldest,
                ),
                error_kind="config",
            )
        latency_ms = int((time.perf_counter() - started) * 1000)
        return ConnectionCheckResult(
            ok=True, message=say("Connection successful"), latency_ms=latency_ms
        )

    async def query(
        self,
        sql: str,
        params: tuple[object, ...] = (),
        *,
        refusals: Mapping[int, str] | None = None,
    ) -> list[dict[str, Any]]:
        """Run a read and hand back its rows, by column name.

        `params` is always passed to the driver, even empty, so that a `%` in
        the text means the same thing in every statement: see `identifier`.
        """
        try:
            async with self._connection() as connection:
                async with connection.cursor(aiomysql.DictCursor) as cursor:
                    await cursor.execute(sql, params)
                    rows: list[dict[str, Any]] = list(await cursor.fetchall())
                    return rows
        except PoolExhausted:
            error_kind, message = await self._why_no_connection()
            raise AdapterError(error_kind, message) from None
        except Exception as exc:
            named = named_refusal(exc, refusals)
            if named is not None:
                raise ValueError(named) from None
            error_kind, message = classify(exc, fallback_message=N_("Query failed"))
            raise AdapterError(error_kind, message) from None

    async def _why_no_connection(self) -> tuple[ErrorKind, str]:
        """Ask the server once, on the failure path, what is actually wrong."""
        try:
            connection = await self._direct()
            connection.close()
        except Exception as exc:
            return classify(exc, fallback_message=N_("Query failed"))
        return "unknown", say("All connections to this source are busy")
