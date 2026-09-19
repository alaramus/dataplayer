"""Running SQL somebody wrote over the files of one connector.

D77 says what a statement may name: its relations are this source's own nodes,
resolved by the one containment rule, and a path is never written. D78 says
what the engine is: an in-memory database per run, given the files it needs and
then locked out of the filesystem, and thrown away when the run ends.

Everything the engine does blocks, so everything the engine does happens on a
worker thread. That is also why cancelling is an interrupt on the connection
rather than a cancelled task: dropping the task would leave the thread reading.
"""

import json
import re
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from threading import Event
from typing import Any

import anyio
import duckdb
from anyio import to_thread

from app.adapters.explorer.arrow import column_type, encoder
from app.adapters.explorer.dialect import REFUSALS, prepare
from app.adapters.explorer.formats import format_of
from app.adapters.explorer.query_readers import (
    QUERY_FORMATS,
    FileReaders,
    Preparation,
    PreparationStopped,
)
from app.adapters.explorer.storage import ROOT, Place, Storage, node_id_of
from app.adapters.protocol import AdapterError
from app.adapters.query import (
    ColumnSummary,
    ExplainNode,
    ExplainRequest,
    ExplainResult,
    GeneratedQuery,
    GenerateQueryRequest,
    MaterialisedResult,
    PreparedScript,
    PreparedStatement,
    QueryDiagnostic,
    QueryEvent,
    QueryLimits,
    QueryMetadata,
    QueryMetadataRequest,
    QueryProfile,
    QueryRequest,
    RelationSummary,
    ResultColumn,
    StatementFinished,
    StatementStarted,
    StatementStatus,
)

# What one statement may do, and what a person may ask for. Read-only work over
# local files, so both are generous compared with a shared server's.
DEFAULT_TIMEOUT_SECONDS = 60
MAX_TIMEOUT_SECONDS = 600

# What the engine is allowed to take while it works. A file source is one
# person's storage on a shared server, so a query that needs more than this
# fails rather than pushing everybody else out of memory or off the disk.
MEMORY_LIMIT = "1GB"
THREADS = 2

# How many rows are pulled from the engine at a time. Small enough that a
# ceiling is noticed early, large enough that a full page is one or two pulls.
BATCH_ROWS = 2048

# How far the editor's list of relations may look, and how much of it it may
# offer. A walk of a tree is unbounded by nature (D76 bounds the search the
# same way), and a completion list nobody can read is not a longer answer.
MAX_SCANNED = 20_000
MAX_RELATIONS = 300
MAX_DEPTH = 12

MAX_MESSAGE_CHARS = 500
_UNSAFE = {ord(char): None for char in ("\r", "\n", "\t", "\x00")}

# A drive letter or a path starting at the root: what a message must never
# carry, because the layout of the server is the one thing this source's node
# ids exist to hide (D78).
_NAMES_A_PATH = re.compile(r"[A-Za-z]:[\\/]|(?:^|[\s\"'(])[\\/]")

# The engine's exception classes, as categories. Anything unlisted is
# "unknown", which is honest: a category per class name would be a guess.
_CATEGORIES: dict[str, str] = {
    "ParserException": "syntax",
    "SyntaxException": "syntax",
    "BinderException": "missing_object",
    "CatalogException": "missing_object",
    "IOException": "missing_object",
    "PermissionException": "permission",
    "ConversionException": "data",
    "InvalidTypeException": "data",
    "TypeMismatchException": "data",
    "OutOfRangeException": "data",
    "ConstraintException": "data",
    "InvalidInputException": "data",
    "OutOfMemoryException": "resource",
    "InterruptException": "cancelled",
}

# What is said when the engine's own words cannot be shown.
_FALLBACKS: dict[str, str] = {
    "syntax": "This statement could not be read",
    "missing_object": "This statement names something that is not there",
    "permission": "This statement asked for something outside this connection",
    "data": "A value in this statement could not be used as its type",
    "resource": "This statement needed more memory than a query may take",
    "cancelled": "Cancelled",
    "timeout": "The statement ran out of time",
    "unknown": "The statement could not be run",
}


class ResultTooLarge(Exception):
    """A statement succeeded and its result cannot be published (D64)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def quoted(name: str) -> str:
    """One name as this dialect writes it. The browser never composes one."""
    return '"' + name.replace('"', '""') + '"'


class _Engine:
    """One in-memory database, opened for one run and then thrown away.

    The order here is the whole of D78: the relations are registered first,
    because registering them reads the files, and only then is the door shut.
    External access being off is what turns the allowed directory from a list
    into a restriction — on its own it restricts nothing, which was worth
    finding out by trying it — and the lock is what stops a `SET` reopening any
    of it.
    """

    def __init__(self, root: Path) -> None:
        self._root = root
        self._connection: duckdb.DuckDBPyConnection | None = None
        self._interrupted = Event()

    def open(self, relations: dict[str, Path], deadline: float | None = None) -> None:
        preparation = Preparation(
            deadline
            if deadline is not None
            else time.monotonic() + DEFAULT_TIMEOUT_SECONDS,
            self._interrupted,
        )
        preparation.check()
        connection = duckdb.connect(config=_CONFIG)
        self._connection = connection
        connection.execute("SET errors_as_json=true")
        readers = FileReaders(connection, preparation.check)
        for name, path in relations.items():
            connection.register(name, readers.read(path))
        preparation.check()
        connection.execute("SET allowed_directories=?", [[str(self._root)]])
        connection.execute("SET disabled_filesystems=?", ["HTTPFileSystem,S3FileSystem"])
        connection.execute("SET enable_external_access=false")
        connection.execute("SET lock_configuration=true")

    @property
    def connection(self) -> duckdb.DuckDBPyConnection:
        if self._connection is None:
            raise AdapterError("unknown", "The query engine is not open")
        return self._connection

    def interrupt(self) -> None:
        """Stop whatever the engine is doing. Safe from another thread."""
        self._interrupted.set()
        connection = self._connection
        if connection is None:
            return
        try:
            connection.interrupt()
        except duckdb.Error:
            return

    def close(self) -> None:
        connection, self._connection = self._connection, None
        if connection is not None:
            connection.close()


# What every engine starts with, before it is given anything. Extensions are
# neither installed nor loaded, so a statement cannot reach the network by
# asking for a reader that would arrive over it.
_CONFIG: dict[str, Any] = {
    "autoinstall_known_extensions": False,
    "autoload_known_extensions": False,
    "allow_community_extensions": False,
    "allow_unsigned_extensions": False,
    "allow_persistent_secrets": False,
    "enable_macro_dependencies": False,
    "memory_limit": MEMORY_LIMIT,
    "threads": THREADS,
}


def _read(connection: duckdb.DuckDBPyConnection, path: Path) -> duckdb.DuckDBPyRelation:
    """The engine's reader for one file, chosen by what the file is.

    The path is passed as an argument rather than written into SQL: it is the
    server's own answer from `resolve`, and composing it into a statement would
    put a filename with a quote in it back into the parser.
    """
    preparation = Preparation(time.monotonic() + DEFAULT_TIMEOUT_SECONDS)
    return FileReaders(connection, preparation.check).read(path)


class _Bounds:
    """What one run has used so far, against the ceilings D64 fixes."""

    def __init__(self, limits: QueryLimits) -> None:
        self.limits = limits
        self.bytes_used = 0
        self.results = 0


class ExplorerExecution:
    """One run: resolve what it names, open an engine, read, close it."""

    def __init__(self, storage: Storage, request: QueryRequest) -> None:
        self._storage = storage
        self._request = request
        self._engine = _Engine(storage.local_root())
        # The local files the engine reads, held for as long as the run is:
        # a copy of a remote file must outlive every statement that reads it.
        self._held = ExitStack()
        self._cancelled = False
        self._timed_out = False

    def events(self) -> AsyncIterator[QueryEvent]:
        return self._run()

    async def cancel(self) -> None:
        """Ask the engine to stop, and let the run settle by itself.

        Not optimistic, for the same reason PostgreSQL's cancel is not: a
        statement that has already finished reading finishes as a success, and
        the state stays `cancelling` until the run says which it was (D64).
        """
        self._cancelled = True
        await to_thread.run_sync(self._engine.interrupt)

    async def _run(self) -> AsyncIterator[QueryEvent]:
        request = self._request
        limits = request.limits
        if request.mode != "read":
            raise AdapterError(
                "config", "This source reads files and runs nothing that writes"
            )
        if request.search_path:
            raise AdapterError(
                "config", "This source has no schemas, so it has no schema context"
            )
        script = prepare(request.text)
        places = await to_thread.run_sync(relations_of, self._storage, script)
        started = time.monotonic()
        state = _Bounds(limits)
        try:
            relations = await to_thread.run_sync(
                held_locally, self._storage, places, self._held
            )
            deadline = started + min(
                limits.statement_timeout_seconds, limits.script_timeout_seconds
            )
            preparation_status: StatementStatus | None = None
            try:
                await to_thread.run_sync(self._engine.open, relations, deadline)
            except PreparationStopped as stopped_preparing:
                preparation_status = stopped_preparing.status
            except duckdb.InterruptException:
                if not self._cancelled:
                    raise
                preparation_status = "cancelled"
            stopped = False
            for statement in script.statements:
                if stopped:
                    yield StatementFinished(
                        ordinal=statement.ordinal, status="not_run", duration_ms=0
                    )
                    continue
                if preparation_status is not None:
                    yield StatementFinished(
                        ordinal=statement.ordinal,
                        status=preparation_status,
                        duration_ms=_since(started),
                    )
                    stopped = True
                    continue
                if self._cancelled:
                    yield StatementFinished(
                        ordinal=statement.ordinal, status="cancelled", duration_ms=0
                    )
                    stopped = True
                    continue
                if time.monotonic() - started > limits.script_timeout_seconds:
                    yield StatementFinished(
                        ordinal=statement.ordinal, status="timed_out", duration_ms=0
                    )
                    stopped = True
                    continue
                yield StatementStarted(ordinal=statement.ordinal)
                finished = await self._one(statement, state)
                yield finished
                stopped = finished.status != "succeeded"
        finally:
            await to_thread.run_sync(self._engine.close)
            await to_thread.run_sync(self._held.close)

    async def _one(
        self, statement: PreparedStatement, state: _Bounds
    ) -> StatementFinished:
        """One statement, on a worker thread, with a watchdog beside it."""
        if statement.refused is not None or statement.kind != "read":
            # The module that records runs refuses these at admission, in the
            # source's own words, and never sends one here. The adapter says it
            # again anyway: what a source will not do is the source's answer,
            # and a caller that reaches it directly gets the same sentence
            # rather than whatever the engine happens to say (D77).
            return StatementFinished(
                ordinal=statement.ordinal,
                status="failed",
                duration_ms=0,
                diagnostic=QueryDiagnostic(
                    code="dp_not_admitted",
                    category="read_only",
                    message=statement.refused or REFUSALS["unknown"],
                ),
            )
        began = time.monotonic()
        self._timed_out = False
        seconds = self._request.limits.statement_timeout_seconds
        # The watchdog is what a timeout is: the engine has no clock of its
        # own, so a statement is stopped the same way a person stops it.
        outcome: list[StatementFinished] = []
        async with anyio.create_task_group() as group:

            async def watchdog() -> None:
                await anyio.sleep(seconds)
                self._timed_out = True
                await to_thread.run_sync(self._engine.interrupt)

            group.start_soon(watchdog)
            outcome.append(
                await to_thread.run_sync(self._carry_out, statement, state, began)
            )
            group.cancel_scope.cancel()
        return outcome[0]

    def _carry_out(
        self, statement: PreparedStatement, state: _Bounds, began: float
    ) -> StatementFinished:
        """Execute and read one statement. Blocking, and on a worker thread."""
        try:
            values = _values_for(self._request, statement)
            cursor = self._engine.connection.execute(statement.text, values)
            result = _materialise(cursor, state)
            return StatementFinished(
                ordinal=statement.ordinal,
                status="succeeded",
                duration_ms=_since(began),
                row_count=len(result.rows),
                result=result,
            )
        except ResultTooLarge as refusal:
            # The statement ran. Publishing what it produced is what failed,
            # and D64 keeps the two apart.
            return StatementFinished(
                ordinal=statement.ordinal,
                status="succeeded",
                duration_ms=_since(began),
                diagnostic=QueryDiagnostic(
                    code="result_too_large", category="resource", message=refusal.message
                ),
            )
        except duckdb.Error as exc:
            diagnostic = self._diagnostic(exc)
            status: StatementStatus = "failed"
            if diagnostic.category == "cancelled":
                status = "cancelled"
            elif diagnostic.category == "timeout":
                status = "timed_out"
            return StatementFinished(
                ordinal=statement.ordinal,
                status=status,
                duration_ms=_since(began),
                diagnostic=diagnostic,
            )

    def _diagnostic(self, exc: duckdb.Error) -> QueryDiagnostic:
        return diagnostic_of(
            exc,
            root=self._storage.local_root(),
            cancelled=self._cancelled,
            timed_out=self._timed_out,
        )


def relations_of(
    storage: Storage, script: PreparedScript
) -> dict[str, Place]:
    """Every file a script names, resolved before anything is opened.

    One failure refuses the whole run rather than one statement: a script whose
    third statement names a file that is not there would otherwise open and
    read the first two before saying so. Blocking.
    """
    wanted: dict[str, Place] = {}
    for statement in script.statements:
        for name in statement.targets:
            if name not in wanted:
                wanted[name] = resolve_relation(storage, name)
    return wanted


def held_locally(
    storage: Storage, places: dict[str, Place], held: ExitStack
) -> dict[str, Path]:
    """The local file of every relation, kept until `held` closes. Blocking."""
    return {
        name: held.enter_context(storage.local_file(place))
        for name, place in places.items()
    }


def resolve_relation(storage: Storage, name: str) -> Place:
    """One name as a file this source will read, or the reason it is not.

    The containment rule is the storage's, and it is the only one: a name that
    leaves the root is refused here exactly as it is for a listing, a download
    or an upload (D77). Blocking.
    """
    shown = name[:120]
    missing = f"There is no file called {shown} in this connection"
    try:
        place = storage.place(name)
    except ValueError:
        raise AdapterError("config", missing) from None
    entry = storage.entry(place)
    if entry is None or entry.is_directory:
        raise AdapterError("config", missing)
    found = format_of(place.name)
    if found == "workbook":
        raise AdapterError(
            "config",
            f"{shown} is a workbook, and a worksheet is not offered to SQL: "
            "reading one needs an engine extension this source will not download",
        )
    if found not in QUERY_FORMATS:
        raise AdapterError(
            "config",
            "SQL here reads CSV, TSV, Parquet, JSON, JSON lines and logs, "
            f"and {shown} is none of them",
        )
    return place


def diagnostic_of(
    exc: duckdb.Error, *, root: Path, cancelled: bool, timed_out: bool
) -> QueryDiagnostic:
    """Reduce an engine error to what may be shown.

    An interrupt is what a cancel and a timeout both look like from here, and
    which one it was is a fact this application holds rather than something
    read out of a message — the same distinction PostgreSQL's `57014` needs.
    """
    name = type(exc).__name__
    category = _CATEGORIES.get(name, "unknown")
    if category == "cancelled":
        category = "timeout" if timed_out and not cancelled else "cancelled"
    detail = _detail(str(exc))
    subtype = detail.get("error_subtype")
    if subtype in {"COLUMN_NOT_FOUND", "MISSING_ENTRY"}:
        category = "missing_object"
    elif subtype == "SYNTAX_ERROR":
        category = "syntax"
    message = _safe_text(
        detail.get("exception_message") or str(exc), root, _FALLBACKS[category]
    )
    if category in {"cancelled", "timeout"}:
        message = _FALLBACKS[category]
    return QueryDiagnostic(
        code=name,
        category=category,  # type: ignore[arg-type]  # _CATEGORIES answers the union
        message=message,
        position=_position(detail),
    )


def _detail(raw: str) -> dict[str, str]:
    """The engine's own account of an error, when it wrote one.

    `errors_as_json` makes the message a JSON document behind a prefix, which
    is what gives a clean sentence and an offset instead of a printed line with
    a caret under it.
    """
    at = raw.find("{")
    if at < 0:
        return {}
    try:
        document = json.loads(raw[at:])
    except ValueError:
        return {}
    if not isinstance(document, dict):
        return {}
    return {str(key): str(value) for key, value in document.items()}


def _position(detail: dict[str, str]) -> int | None:
    try:
        return max(0, int(detail["position"]))
    except (KeyError, ValueError):
        return None


def _safe_text(value: str, root: Path, fallback: str) -> str:
    """One line, bounded, and with the server's layout taken out of it.

    The root is spelled two ways on Windows and one everywhere else, and both
    are removed. What is left is checked again: anything that still names an
    absolute path is dropped for the standard sentence, because a message is
    not worth leaking where this server keeps its files.
    """
    line = value.splitlines()[0] if value else ""
    for form in {str(root), root.as_posix()}:
        line = line.replace(form, "…")
    line = line.translate(_UNSAFE).strip()[:MAX_MESSAGE_CHARS]
    if not line or _NAMES_A_PATH.search(line):
        return fallback
    return line


def _values_for(
    request: QueryRequest, statement: PreparedStatement
) -> dict[str, str | None]:
    """The bindings this statement uses, and no others.

    The engine refuses a binding a statement did not ask for, which is the
    behaviour wanted: a run carries every parameter the document has, and one
    statement of a script uses some of them.
    """
    wanted = set(statement.parameters)
    return {
        parameter.name: parameter.value
        for parameter in request.parameters
        if parameter.name in wanted
    }


def _materialise(
    cursor: duckdb.DuckDBPyConnection, state: _Bounds
) -> MaterialisedResult:
    """Read the whole result once, within every ceiling D64 states.

    Arrow rather than Python objects: the engine converts a timestamp with a
    zone through a library that is not a dependency here, and the file source
    already renders Arrow values one way for Parquet (D23).
    """
    limits = state.limits
    described = cursor.description or []
    reader = cursor.to_arrow_reader(BATCH_ROWS)
    schema = reader.schema
    spellings = [str(item[1]) for item in described]
    names = [str(item[0]) for item in described]
    columns = [
        ResultColumn(
            id=str(position),
            name=names[position] if position < len(names) else field.name,
            type=column_type(field.type, _spelling(spellings, position)),
        )
        for position, field in enumerate(schema)
    ]
    encoders = [
        encoder(field.type, _spelling(spellings, position))
        for position, field in enumerate(schema)
    ]

    # One row more than the ceiling: the extra row is how truncation is
    # established rather than guessed from a full page.
    wanted = limits.max_result_rows + 1
    raw: list[dict[str, Any]] = []
    for batch in reader:
        raw.extend(batch.to_pylist())
        if len(raw) >= wanted:
            break
    reader.close()

    truncated = len(raw) > limits.max_result_rows
    rows: list[list[str | None]] = []
    used = 0
    for record in raw[: limits.max_result_rows]:
        row: list[str | None] = []
        for position, field in enumerate(schema):
            cell = encoders[position](record.get(field.name))
            size = 0 if cell is None else len(cell.encode())
            if size > limits.max_cell_bytes:
                raise ResultTooLarge(
                    f"A value in {columns[position].name} is larger than one "
                    "cell may be"
                )
            used += size
            if used > limits.max_result_bytes:
                raise ResultTooLarge("This result is larger than one result may be")
            row.append(cell)
        rows.append(row)

    state.bytes_used += used
    state.results += 1
    if state.results > limits.max_run_results:
        raise ResultTooLarge("This run produced more results than one run may hold")
    if state.bytes_used > limits.max_run_bytes:
        raise ResultTooLarge("This run produced more data than one run may hold")
    return MaterialisedResult(
        columns=columns, rows=rows, truncated=truncated, bytes_used=used
    )


def _spelling(spellings: list[str], position: int) -> str | None:
    return spellings[position] if position < len(spellings) else None


def _since(began: float) -> int:
    return int((time.monotonic() - began) * 1000)


class ExplorerQuery:
    """The file source as one that accepts complete SQL (D77)."""

    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    def profile(self) -> QueryProfile:
        return QueryProfile(
            dialect="duckdb",
            parameter_syntax="named_dollar",
            statement_modes=["read"],
            supports_cancel=True,
            default_timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
            max_timeout_seconds=MAX_TIMEOUT_SECONDS,
        )

    def prepare(self, text: str) -> PreparedScript:
        return prepare(text)

    def open(self, request: QueryRequest) -> ExplorerExecution:
        return ExplorerExecution(self._storage, request)

    async def metadata(self, request: QueryMetadataRequest) -> QueryMetadata:
        return await to_thread.run_sync(self._metadata, request)

    async def generate(self, request: GenerateQueryRequest) -> GeneratedQuery:
        return await to_thread.run_sync(self._generate, request)

    async def explain(self, request: ExplainRequest) -> ExplainResult:
        return await to_thread.run_sync(self._explain, request)

    def _metadata(self, request: QueryMetadataRequest) -> QueryMetadata:
        """What the editor may complete to. Blocking."""
        relations, complete = self._listed()
        columns: dict[str, list[ColumnSummary]] = {}
        for name in request.relations[:50]:
            found = self._columns(name)
            if found is not None:
                columns[name] = found
        return QueryMetadata(
            schemas=[], relations=relations, columns=columns, complete=complete
        )

    def _listed(self) -> tuple[list[RelationSummary], bool]:
        """Every file below the root that SQL can read, breadth first."""
        found: list[RelationSummary] = []
        scanned = 0
        queue: list[tuple[Place, int]] = [(ROOT, 0)]
        while queue:
            folder, depth = queue.pop(0)
            try:
                entries = sorted(
                    self._storage.entries(folder), key=lambda entry: entry.name
                )
            except OSError:
                continue
            for entry in entries:
                scanned += 1
                if scanned > MAX_SCANNED:
                    return found, False
                if entry.is_link:
                    continue
                if entry.is_directory:
                    if depth + 1 <= MAX_DEPTH:
                        queue.append((entry.place, depth + 1))
                    continue
                if format_of(entry.name) not in QUERY_FORMATS:
                    continue
                if len(found) >= MAX_RELATIONS:
                    return found, False
                found.append(
                    RelationSummary(
                        schema_name="",
                        name=node_id_of(entry.place) or "",
                        kind="table",
                    )
                )
        return found, True

    def _columns(self, name: str) -> list[ColumnSummary] | None:
        """The columns SQL would see in one file, or nothing if it sees none.

        Asked of the engine rather than of the readers the grid uses, because
        the answer has to be what a statement will actually find: a delimited
        column is text in the grid, where it is edited, and typed here, where
        it is added up (D77).
        """
        try:
            place = self._storage.place(name)
        except ValueError:
            return None
        entry = self._storage.entry(place)
        if entry is None or entry.is_directory or format_of(place.name) not in QUERY_FORMATS:
            return None
        try:
            with self._storage.local_file(place) as path, _describing() as connection:
                relation = _read(connection, path)
                return [
                    ColumnSummary(name=str(column), type_sql=str(type_))
                    for column, type_ in zip(
                        relation.columns, relation.types, strict=False
                    )
                ]
        except (duckdb.Error, AdapterError, PreparationStopped):
            # A file the engine cannot make sense of is one the editor has
            # nothing to say about. Run will report it properly.
            return None

    def _generate(self, request: GenerateQueryRequest) -> GeneratedQuery:
        """A statement about one node, written by the source that owns it."""
        name = quoted(request.node_id)
        if request.kind == "name":
            return GeneratedQuery(text=name)
        if request.kind == "columns":
            return GeneratedQuery(text=", ".join(self._column_names(request.node_id)))
        return GeneratedQuery(text=f"SELECT *\nFROM {name}\nLIMIT 100")

    def _column_names(self, node_id: str) -> list[str]:
        columns = self._columns(node_id)
        if not columns:
            raise ValueError("This node states no columns SQL could read")
        return [quoted(column.name) for column in columns]

    def _explain(self, request: ExplainRequest) -> ExplainResult:
        """The plan the engine would use, without running the statement."""
        script = prepare(request.text)
        if len(script.statements) != 1:
            raise ValueError("Explain takes one statement")
        statement = script.statements[0]
        if statement.refused is not None:
            raise ValueError(statement.refused)
        if statement.kind != "read":
            raise ValueError("Only a read is planned here")

        engine = _Engine(self._storage.local_root())
        held = ExitStack()
        try:
            engine.open(held_locally(self._storage, relations_of(self._storage, script), held))
            values = {
                parameter.name: parameter.value
                for parameter in request.parameters
                if parameter.name in set(statement.parameters)
            }
            raw = engine.connection.execute(
                f"EXPLAIN {statement.text}", values
            ).fetchall()
            planned = engine.connection.execute(
                f"EXPLAIN (FORMAT JSON) {statement.text}", values
            ).fetchall()
        except PreparationStopped:
            raise AdapterError("timeout", "Preparing the log input ran out of time") from None
        except duckdb.Error as exc:
            raise AdapterError(
                "config",
                diagnostic_of(
                    exc,
                    root=self._storage.local_root(),
                    cancelled=False,
                    timed_out=False,
                ).message,
            ) from None
        finally:
            engine.close()
            held.close()
        return _explained(raw, planned)


@contextmanager
def _describing() -> Iterator[duckdb.DuckDBPyConnection]:
    """An engine opened to read a file's header and nothing else.

    No statement from anybody runs on it, so there is nothing to shut the door
    against: what D78 locks down is an engine that is about to be given a
    person's SQL.
    """
    connection = duckdb.connect(config=_CONFIG)
    try:
        yield connection
    finally:
        connection.close()


def _explained(raw: list[Any], planned: list[Any]) -> ExplainResult:
    """The engine's two accounts of a plan, as one answer.

    The printed plan is what a person recognises and the JSON one is what a
    tree is built from; the table the console shows is the tree read as a list,
    which the screen flattens rather than the server inventing a third shape
    (D65).
    """
    document: Any = []
    for row in planned:
        if len(row) >= 2 and str(row[0]) in {"physical_plan", "logical_plan"}:
            try:
                document = json.loads(str(row[1]))
            except ValueError:
                document = []
            break
    top = document[0] if isinstance(document, list) and document else document
    plan = _node(top if isinstance(top, dict) else {}, "0")
    return ExplainResult(
        plan=plan,
        raw="\n".join(str(row[1]) for row in raw if len(row) >= 2),
        rows=plan.rows,
    )


def _node(document: dict[str, Any], identifier: str) -> ExplainNode:
    extra = document.get("extra_info")
    details = (
        {str(key): str(value) for key, value in extra.items()}
        if isinstance(extra, dict)
        else {}
    )
    kind = str(document.get("name", "PLAN"))
    children = document.get("children")
    return ExplainNode(
        id=identifier,
        kind=kind,
        label=kind.replace("_", " ").title(),
        rows=_estimate(details),
        details=details,
        children=[
            _node(child, f"{identifier}.{position}")
            for position, child in enumerate(children if isinstance(children, list) else [])
            if isinstance(child, dict)
        ],
    )


def _estimate(details: dict[str, str]) -> int | None:
    try:
        return int(float(details["Estimated Cardinality"]))
    except (KeyError, ValueError):
        return None
