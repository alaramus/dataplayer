"""How to talk to a ClickHouse server, over its HTTP interface (D267).

Knows about requests, statements and the server's errors, and nothing about
what the caller wants; the catalog, the rows and everything after are built
on it.
"""

import asyncio
import json
import logging
import re
import time
import uuid
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlsplit

import httpx

from app.adapters.clickhouse.options import ClickhouseOptions, ClickhouseUserPassword
from app.adapters.clickhouse.pool import client_for, make_client
from app.adapters.clickhouse.types import decode_line
from app.adapters.protocol import AdapterError, ConnectionCheckResult, ErrorKind
from app.adapters.resources import Pooling
from app.core.logs import record_failure, with_ref
from app.core.translation import N_, say

logger = logging.getLogger(__name__)

CHECK_TIMEOUT_SECONDS = 5.0
# How long a plan of several catalog reads may take altogether (D246).
INSPECTION_SECONDS = 5.0

# The oldest this source speaks to (D267): the LTS release from which every
# output setting below exists. An older server refuses a setting it does not
# know, so a source half working is not even possible; the check says why.
OLDEST = (23, 8)

# How every answer is written (D268): JSON lines, the names and the types
# first, numbers bare so that they are read as the text they are, a Decimal
# with all of its scale, a moment in UTC with its `Z`, NaN and infinity as
# words, and an exception in the middle of an answer as plain text, which no
# line of JSON is.
_OUTPUT: dict[str, str] = {
    "default_format": "JSONCompactEachRowWithNamesAndTypes",
    "date_time_output_format": "iso",
    "output_format_json_quote_64bit_integers": "0",
    "output_format_json_quote_decimals": "0",
    "output_format_json_quote_denormals": "1",
    "output_format_decimal_trailing_zeros": "1",
    "output_format_json_validate_utf8": "1",
    "output_format_json_named_tuples_as_objects": "1",
    "http_write_exception_in_output_format": "0",
}

# A read is a read on the server too: readonly 2 refuses a write and still
# lets the request carry the settings above, and a read whose client went
# away is stopped rather than left to run.
_READ: dict[str, str] = {
    "readonly": "2",
    "cancel_http_readonly_queries_on_client_close": "1",
}

# The server's error codes rather than its text, which quotes the user and
# sometimes the statement.
_AUTH_ERRORS = frozenset({192, 193, 194, 195, 516})
UNKNOWN_DATABASE = 81
UNKNOWN_TABLE = 60
ACCESS_DENIED = 497
_TIMEOUT_ERRORS = frozenset({159, 209})
BAD_QUERY_PARAMETER = 457


class ServerError(Exception):
    """The server refused a statement; `code` is its number for why."""

    def __init__(self, code: int, text: str) -> None:
        super().__init__(f"Code {code}: {text}")
        self.code = code


_CODE = re.compile(r"Code: (\d+)\.")

# How an exception halfway through an answer is set apart from the rows, and
# how much of the end of an answer is held back to look for it.
_EXCEPTION_MARK = b"\n__exception__\n"
HELD_BYTES = 64 * 1024


def _server_error(status: int, headers: Mapping[str, str], body: str) -> ServerError:
    code_text = headers.get("x-clickhouse-exception-code")
    if code_text is None:
        found = _CODE.search(body)
        code_text = found.group(1) if found else None
    if code_text is not None and code_text.isdigit():
        return ServerError(int(code_text), body.strip())
    # A 401 that names no code is the server's own refusal of the sign-in.
    return ServerError(516 if status in (401, 403) else 0, body.strip())


@dataclass(frozen=True)
class ServerProfile:
    version: tuple[int, ...]
    # "25.8.33.6": the number and nothing else.
    text: str

    @property
    def supported(self) -> bool:
        return self.version[: len(OLDEST)] >= OLDEST


_VERSION = re.compile(r"(\d+(?:\.\d+)*)")


def read_profile(version: str) -> ServerProfile:
    found = _VERSION.search(version)
    text = found.group(1) if found else "0"
    return ServerProfile(version=tuple(int(part) for part in text.split(".")), text=text)


def classify(
    exc: BaseException, *, fallback_message: str = N_("Connection failed")
) -> tuple[ErrorKind, str]:
    """Reduce a failure to a safe (kind, message) pair, as MySQL's is (D184)."""
    if isinstance(exc, httpx.TimeoutException | TimeoutError):
        return "timeout", say("Connection timed out")
    if isinstance(exc, ServerError):
        if exc.code in _AUTH_ERRORS:
            return "auth", say("Authentication failed")
        if exc.code == UNKNOWN_DATABASE:
            return "config", say("Database does not exist")
        if exc.code == ACCESS_DENIED:
            return "auth", say("The server does not let this user do that")
        if exc.code in _TIMEOUT_ERRORS:
            return "timeout", say("The server did not answer in time")
    if isinstance(exc, httpx.TransportError | OSError):
        return "network", say("Could not reach the database server")
    ref = record_failure(logger, f"ClickHouse: {fallback_message}", exc)
    return "unknown", with_ref(say(fallback_message), ref)


def named_refusal(exc: BaseException, refusals: Mapping[int, str] | None) -> str | None:
    """The caller's own sentence for an error number it anticipated, or nothing."""
    if refusals is None or not isinstance(exc, ServerError):
        return None
    named = refusals.get(exc.code)
    return None if named is None else say(named)


def compose_url(
    *,
    host: str,
    port: int | None = None,
    user: str = "",
    database: str = "",
    secure: bool = False,
) -> str:
    """A ClickHouse address, quoted part by part for the reason MySQL's is."""
    authority = quote(host, safe="")
    if user != "":
        authority = f"{quote(user, safe='')}@{authority}"
    if port is not None:
        authority += f":{port}"
    url = f"clickhouse://{authority}"
    if database != "":
        url += f"/{quote(database, safe='')}"
    return url + "?secure=true" if secure else url


def compose_url_with_password(
    *,
    host: str,
    port: int | None = None,
    user: str = "",
    database: str = "",
    secure: bool = False,
    password: str = "",
) -> str:
    """The same address with the password in it, for somebody to paste (D89)."""
    plain = compose_url(host=host, port=port, user=user, database=database, secure=secure)
    if password == "":
        return plain
    secret = quote(password, safe="")
    if user == "":
        return plain.replace("://", f"://:{secret}@", 1)
    named = quote(user, safe="")
    return plain.replace(f"{named}@", f"{named}:{secret}@", 1)


_SECURE_WORDS = frozenset({"1", "true", "yes", "on"})


def options_from_url(url: str) -> dict[str, Any]:
    """A connection string taken apart into the fields of the form.

    `clickhouse://` and the HTTP interface's own `http://` and `https://`;
    `https` or `?secure=true` is TLS.
    """
    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except ValueError:
        raise ValueError(say("The connection string names no usable port")) from None
    scheme = parts.scheme.lower()
    if scheme not in ("clickhouse", "http", "https"):
        raise ValueError(say("That is not a ClickHouse connection string"))
    if not parts.hostname:
        raise ValueError(say("The connection string names no host"))

    query = parse_qs(parts.query)
    secure = scheme == "https" or any(
        value.lower() in _SECURE_WORDS for value in query.get("secure", [])
    )
    options: dict[str, Any] = {"host": unquote(parts.hostname), "secure": secure}
    if port is not None:
        options["port"] = port
    if parts.username:
        options["user"] = unquote(parts.username)
    database = unquote(parts.path.lstrip("/")) or next(iter(query.get("database", [])), "")
    if database:
        options["database"] = database
    if parts.password:
        options["auth_method"] = "user_password"
        options["password"] = unquote(parts.password)
    else:
        options["auth_method"] = "no_password"
    return options


class Encoded(str):
    """A parameter's value already in the server's text format: an array
    written with its quotes, or a value somebody typed for the console, which
    the server reads as clickhouse-client's `--param_` would (D270)."""


_ESCAPES = {ord("\\"): "\\\\", ord("\t"): "\\t", ord("\n"): "\\n", ord("\r"): "\\r"}


def escaped(value: str) -> str:
    """A value as the text the server reads a parameter in.

    The server reads `param_<name>` in its escaped text format, so a
    backslash, a tab or a line break in a name or a filter would otherwise be
    read as an escape, or end the value early.
    """
    return value.translate(_ESCAPES)


def quoted_name(*parts: str) -> str:
    """A name quoted for ClickHouse, each part apart: `db`.`table`.

    Inside backticks the server reads a backslash as an escape, so it is
    doubled before the backtick is escaped. A `{` needs nothing: a parameter's
    braces are read only outside quotes.
    """
    return ".".join(
        "`" + part.replace("\\", "\\\\").replace("`", "\\`") + "`" for part in parts
    )


@dataclass(frozen=True)
class Answer:
    """What a statement answered: its columns, their types, and its rows."""

    names: list[str]
    types: list[str]
    rows: list[list[Any]]

    def dicts(self) -> list[dict[str, Any]]:
        return [dict(zip(self.names, row, strict=True)) for row in self.rows]


def _parse(body: str) -> Answer:
    lines = [line for line in body.splitlines() if line.strip()]
    if not lines:
        return Answer(names=[], types=[], rows=[])
    try:
        decoded = [decode_line(line) for line in lines]
    except ValueError:
        raise ServerError(0, body[-2000:]) from None
    if len(decoded) < 2:
        raise ServerError(0, body[-2000:])
    names = [str(name) for name in decoded[0]]
    types = [str(type_) for type_ in decoded[1]]
    return Answer(names=names, types=types, rows=decoded[2:])


class ClickhouseSession:
    """How to talk to one ClickHouse server."""

    def __init__(self, options: ClickhouseOptions, pooling: Pooling | None = None) -> None:
        self._options = options
        self._pooling = pooling
        self._profile: ServerProfile | None = None

    @property
    def options(self) -> ClickhouseOptions:
        return self._options

    def _password(self) -> str:
        if not isinstance(self._options, ClickhouseUserPassword):
            return ""
        return self._options.password.get_secret_value()

    def _base_url(self) -> str:
        options = self._options
        scheme = "https" if options.secure else "http"
        host = f"[{options.host}]" if ":" in options.host else options.host
        return f"{scheme}://{host}:{options.port}/"

    def connection_string(self) -> str:
        options = self._options
        return compose_url(
            host=options.host,
            port=options.port,
            user=options.user,
            database=options.database,
            secure=options.secure,
        )

    def database(self) -> str:
        """The database the connection names, or nothing when it names none."""
        return self._options.database

    @asynccontextmanager
    async def _client(self) -> AsyncIterator[httpx.AsyncClient]:
        """A client to send on: the connector's kept one when there is one."""
        kept = None
        if self._pooling is not None:
            options = self._options
            # What makes two clients different, and nothing about the request.
            fingerprint = (
                f"{options.host}:{options.port}:{options.secure}:{options.user}:"
                f"{self._password()}"
            )
            kept = await client_for(self._pooling, fingerprint, verify=options.secure)
        if kept is not None:
            yield kept.client
            return
        client = make_client(verify=self._options.secure, read_timeout=None)
        try:
            yield client
        finally:
            await client.aclose()

    def _request_params(
        self,
        settings: Mapping[str, str],
        *,
        read: bool,
        query_id: str | None,
    ) -> dict[str, str]:
        """The settings a request carries in its address, and nothing else.

        The address is what a client library logs and a proxy keeps; the
        statement and the values bound in it travel in the body (`_form`).
        """
        sent: dict[str, str] = {**_OUTPUT, **(_READ if read else {})}
        if self._options.database:
            sent["database"] = self._options.database
        # After the connection's database, so a run may name another (D270).
        sent.update(settings)
        if query_id is not None:
            sent["query_id"] = query_id
        return sent

    @staticmethod
    def _form(sql: str, params: Mapping[str, str]) -> list[tuple[str, tuple[None, str]]]:
        """The statement and its parameters as the fields of a multipart body.

        In the body rather than the address, which httpx writes into its log
        at INFO: a filter's value and a search's words stay out of every log.
        """
        fields: list[tuple[str, tuple[None, str]]] = [("query", (None, sql))]
        for name, value in params.items():
            text = value if isinstance(value, Encoded) else escaped(value)
            fields.append((f"param_{name}", (None, text)))
        return fields

    async def _send(
        self,
        client: httpx.AsyncClient,
        sql: str,
        params: Mapping[str, str],
        settings: Mapping[str, str],
        *,
        read: bool,
        query_id: str | None = None,
    ) -> str:
        response = await client.post(
            self._base_url(),
            params=self._request_params(settings, read=read, query_id=query_id),
            files=self._form(sql, params),
            auth=httpx.BasicAuth(self._options.user, self._password()),
        )
        body = response.text
        if response.status_code != 200:
            raise _server_error(response.status_code, response.headers, body)
        return body

    async def check(self) -> ConnectionCheckResult:
        started = time.perf_counter()
        client = make_client(verify=self._options.secure, read_timeout=CHECK_TIMEOUT_SECONDS)
        try:
            body = await self._send(
                client, "SELECT version() AS version", {}, {}, read=True
            )
            version = str(_parse(body).rows[0][0])
        except Exception as exc:
            error_kind, message = classify(exc)
            return ConnectionCheckResult(ok=False, message=message, error_kind=error_kind)
        finally:
            await client.aclose()
        profile = read_profile(version)
        if not profile.supported:
            return ConnectionCheckResult(
                ok=False,
                message=say(
                    "ClickHouse {version} is older than this source supports ({oldest})",
                    version=profile.text,
                    oldest=".".join(str(part) for part in OLDEST),
                ),
                error_kind="config",
            )
        latency_ms = int((time.perf_counter() - started) * 1000)
        return ConnectionCheckResult(
            ok=True, message=say("Connection successful"), latency_ms=latency_ms
        )

    async def profile(self) -> ServerProfile:
        """Which server this is; asked once per session and kept."""
        if self._profile is None:
            answer = await self.answer("SELECT version()")
            self._profile = read_profile(str(answer.rows[0][0]))
        return self._profile

    async def answer(
        self,
        sql: str,
        params: Mapping[str, str] | None = None,
        *,
        settings: Mapping[str, str] | None = None,
        refusals: Mapping[int, str] | None = None,
        server_errors: bool = False,
        read: bool = True,
    ) -> Answer:
        """Run a read and hand back its whole answer.

        `params` are the statement's `{name:Type}` parameters, sent apart from
        the text as the server's own parameters: a value is never in the
        statement. The answer is buffered by the server, so a failure halfway
        is a refusal rather than half a page. `server_errors` hands the
        server's refusal back as it is, for a caller that shows its sentence;
        `read` off is for a statement that acts and answers, as KILL does.
        """
        try:
            async with self._client() as client:
                body = await self._send(
                    client,
                    sql,
                    params or {},
                    {"wait_end_of_query": "1", **(settings or {})},
                    read=read,
                    query_id=str(uuid.uuid4()),
                )
        except httpx.PoolTimeout:
            raise AdapterError(
                "unknown", say("All connections to this source are busy")
            ) from None
        except Exception as exc:
            if server_errors and isinstance(exc, ServerError):
                raise
            named = named_refusal(exc, refusals)
            if named is not None:
                raise ValueError(named) from None
            error_kind, message = classify(exc, fallback_message=N_("Query failed"))
            raise AdapterError(error_kind, message) from None
        try:
            return _parse(body)
        except ServerError as exc:
            error_kind, message = classify(exc, fallback_message=N_("Query failed"))
            raise AdapterError(error_kind, message) from None

    async def query(
        self,
        sql: str,
        params: Mapping[str, str] | None = None,
        *,
        refusals: Mapping[int, str] | None = None,
    ) -> list[dict[str, Any]]:
        """Run a read and hand back its rows, by column name."""
        return (await self.answer(sql, params, refusals=refusals)).dicts()

    @asynccontextmanager
    async def inspection(self) -> AsyncIterator[ClickhouseSession]:
        """One clock for several catalog reads (D246).

        Over HTTP there is no connection for them to share; the kept client
        reuses one anyway, and a read past the clock is cancelled with its
        request, which stops it on the server.
        """
        try:
            async with asyncio.timeout(INSPECTION_SECONDS):
                yield self
        except TimeoutError:
            raise AdapterError("timeout", say("The server did not answer in time")) from None


    async def run_statement(
        self,
        sql: str,
        params: Mapping[str, str],
        settings: Mapping[str, str],
        *,
        read: bool,
        query_id: str,
        row_limit: int,
    ) -> Ran:
        """One statement somebody wrote, its answer read a line at a time.

        At most `row_limit` rows are kept and one more says there were more;
        the request is then closed, which stops a read on the server. A change
        waits for its end on the server, so its count of written rows is the
        whole count.
        """
        sent = dict(settings)
        if not read:
            sent["wait_end_of_query"] = "1"
        async with self._client() as client:
            async with client.stream(
                "POST",
                self._base_url(),
                params=self._request_params(sent, read=read, query_id=query_id),
                files=self._form(sql, params),
                auth=httpx.BasicAuth(self._options.user, self._password()),
            ) as response:
                if response.status_code != 200:
                    body = (await response.aread()).decode(errors="replace")
                    raise _server_error(response.status_code, response.headers, body)
                written = _written_rows(response.headers.get("x-clickhouse-summary"))
                lines: list[Any] = []
                more = False
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        decoded = decode_line(line)
                    except ValueError:
                        # An exception halfway through an answer arrives as
                        # its text, which no line of JSON is (D268).
                        rest = line + (await response.aread()).decode(errors="replace")
                        raise _server_error(500, {}, rest) from None
                    if len(lines) >= row_limit + 2:
                        more = True
                        break
                    lines.append(decoded)
        if not lines:
            return Ran(names=[], types=[], rows=[], truncated=False, written_rows=written)
        return Ran(
            names=[str(name) for name in lines[0]],
            types=[str(type_) for type_ in lines[1]] if len(lines) > 1 else [],
            rows=lines[2:],
            truncated=more,
            written_rows=written,
        )

    async def command(
        self,
        sql: str,
        params: Mapping[str, str],
        *,
        settings: Mapping[str, str] | None = None,
        refusals: Mapping[int, str] | None = None,
        data: bytes | AsyncIterator[bytes] | None = None,
        passing: frozenset[int] = frozenset(),
    ) -> int | None:
        """Run a change and answer how many rows it wrote, where the server says.

        With `data` the statement travels in the address and the rows in the
        body, as an `INSERT … FORMAT` takes them. The change is waited for to
        its end, so a failure is a refusal of the whole of it. An error whose
        code is in `passing` is handed back as it is, for a caller with
        another way to do the same.
        """
        sent = {"wait_end_of_query": "1", **(settings or {})}
        query = self._request_params(sent, read=False, query_id=str(uuid.uuid4()))
        try:
            async with self._client() as client:
                if data is None:
                    response = await client.post(
                        self._base_url(),
                        params=query,
                        files=self._form(sql, params),
                        auth=httpx.BasicAuth(self._options.user, self._password()),
                    )
                else:
                    # The rows are the body, so the statement is in the
                    # address: names only, as an INSERT here binds nothing.
                    if params:
                        raise ValueError("An insert with rows binds no parameters")
                    response = await client.post(
                        self._base_url(),
                        params={**query, "query": sql},
                        content=data,
                        auth=httpx.BasicAuth(self._options.user, self._password()),
                    )
                if response.status_code != 200:
                    raise _server_error(response.status_code, response.headers, response.text)
                return _written_rows(response.headers.get("x-clickhouse-summary"))
        except ServerError as exc:
            if exc.code in passing:
                raise
            raise refused_change(exc, refusals) from None
        except httpx.PoolTimeout:
            raise AdapterError("unknown", say("All connections to this source are busy")) from None
        except (httpx.TransportError, OSError) as exc:
            error_kind, message = classify(exc, fallback_message=N_("Update failed"))
            raise AdapterError(error_kind, message) from None

    async def stream(
        self, sql: str, params: Mapping[str, str], *, batch_size: int
    ) -> AsyncIterator[list[list[Any]]]:
        """Every row of a read, a batch at a time, never held whole.

        The answer is not buffered by the server: it arrives as it is read, and
        a reader that stops early closes the request, which stops the read on
        the server. An exception halfway arrives as its text (D268).
        """
        try:
            async with self._client() as client:
                async with client.stream(
                    "POST",
                    self._base_url(),
                    params=self._request_params({}, read=True, query_id=str(uuid.uuid4())),
                    files=self._form(sql, params),
                    auth=httpx.BasicAuth(self._options.user, self._password()),
                ) as response:
                    if response.status_code != 200:
                        body = (await response.aread()).decode(errors="replace")
                        raise _server_error(response.status_code, response.headers, body)
                    seen = 0
                    batch: list[list[Any]] = []
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            decoded = decode_line(line)
                        except ValueError:
                            rest = line + (await response.aread()).decode(errors="replace")
                            raise _server_error(500, {}, rest) from None
                        seen += 1
                        # The names and the types come first.
                        if seen <= 2:
                            continue
                        batch.append(decoded)
                        if len(batch) >= batch_size:
                            yield batch
                            batch = []
                    if batch:
                        yield batch
        except httpx.PoolTimeout:
            raise AdapterError("unknown", say("All connections to this source are busy")) from None
        except AdapterError:
            raise
        except Exception as exc:
            error_kind, message = classify(exc, fallback_message=N_("Export failed"))
            raise AdapterError(error_kind, message) from None

    async def stream_bytes(
        self, sql: str, params: Mapping[str, str], settings: Mapping[str, str]
    ) -> AsyncIterator[bytes]:
        """A read's answer as the bytes the server writes, in its own format.

        A failure halfway arrives inside the answer, after a line saying
        `__exception__`; so the last `HELD_BYTES` are held back until the
        answer ends, and an answer ending in an exception is a failure rather
        than rows. Nothing held back has been handed on.
        """
        held = b""
        try:
            async with self._client() as client:
                async with client.stream(
                    "POST",
                    self._base_url(),
                    params=self._request_params(settings, read=True, query_id=str(uuid.uuid4())),
                    files=self._form(sql, params),
                    auth=httpx.BasicAuth(self._options.user, self._password()),
                ) as response:
                    if response.status_code != 200:
                        body = (await response.aread()).decode(errors="replace")
                        raise _server_error(response.status_code, response.headers, body)
                    async for chunk in response.aiter_bytes():
                        held += chunk
                        if len(held) > HELD_BYTES:
                            cut = len(held) - HELD_BYTES
                            yield held[:cut]
                            held = held[cut:]
            # The line break before the mark may have gone with the rows
            # already handed on, or be the answer's very start.
            framed = b"\n" + held
            marker = framed.rfind(_EXCEPTION_MARK)
            if marker >= 0 and _CODE.search(framed[marker:].decode(errors="replace")):
                raise _server_error(500, {}, framed[marker + len(_EXCEPTION_MARK) :].decode(errors="replace"))
            if held:
                yield held
        except httpx.PoolTimeout:
            raise AdapterError("unknown", say("All connections to this source are busy")) from None
        except AdapterError:
            raise
        except ServerError as exc:
            error_kind, message = classify(exc, fallback_message=N_("The rows could not be read"))
            raise AdapterError(error_kind, message) from None
        except (httpx.TransportError, OSError) as exc:
            error_kind, message = classify(exc, fallback_message=N_("The rows could not be read"))
            raise AdapterError(error_kind, message) from None

    async def kill_query(self, query_id: str) -> None:
        """Stop one statement, from a request of its own.

        Failing to kill is not reported: the statement then ends by itself,
        and its own outcome says so.
        """
        try:
            async with self._client() as client:
                await self._send(
                    client,
                    "KILL QUERY WHERE query_id = {id:String} ASYNC",
                    {"id": query_id},
                    {},
                    read=False,
                )
        except Exception:
            # The statement may have finished first, which is the outcome anyway.
            pass


@dataclass(frozen=True)
class Ran:
    """What one statement of the console answered."""

    names: list[str]
    types: list[str]
    rows: list[list[Any]]
    truncated: bool
    written_rows: int | None


def _written_rows(summary: str | None) -> int | None:
    if not summary:
        return None
    try:
        return int(json.loads(summary)["written_rows"])
    except (ValueError, KeyError, TypeError):
        return None


def refused_change(exc: ServerError, refusals: Mapping[int, str] | None) -> Exception:
    """A server's refusal of a change, as the caller's ValueError or the source failing.

    What is about reaching the server or who is asking is the source failing;
    anything else the server refused is about the change, and is said so.
    """
    named = named_refusal(exc, refusals)
    if named is not None:
        return ValueError(named)
    if exc.code in (*_AUTH_ERRORS, ACCESS_DENIED, UNKNOWN_DATABASE, *_TIMEOUT_ERRORS):
        error_kind, message = classify(exc, fallback_message=N_("Update failed"))
        return AdapterError(error_kind, message)
    return ValueError(say("The source rejected the change"))
