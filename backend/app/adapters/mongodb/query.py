"""Running shell syntax somebody wrote on a MongoDB server (D296).

Every statement is one call on the driver, built from what the shell reader
returned; nothing is evaluated. A read is a read because the call made is one
that only reads — the class comes from the method, and the server has no
read-only session to enforce it with.

MongoDB holds no transaction here: a change is kept the moment it ends, so, as
on ClickHouse (D271), a run that changes anything holds that one statement and
the `use` lines before it, and there is no manual mode. A statement's time
limit is the driver's own (`pymongo.timeout`), which the server is told as
`maxTimeMS`; Stop cancels the call and kills what the server is still doing by
the comment the call carried.
"""

import asyncio
import contextlib
import json
import re
import time
import uuid
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import pymongo
from bson.errors import BSONError
from pymongo import IndexModel, ReturnDocument
from pymongo.errors import (
    BulkWriteError,
    ConnectionFailure,
    OperationFailure,
    PyMongoError,
    ServerSelectionTimeoutError,
)

from app.adapters import jsontext
from app.adapters.content import json_tree
from app.adapters.database_ids import database_id, parse, relation_id
from app.adapters.mongodb.catalog import SYSTEM_DATABASES
from app.adapters.mongodb.relation import MongodbRelation
from app.adapters.mongodb.session import Client, MongodbSession, classify
from app.adapters.mongodb.shell import (
    DATABASE_METHODS,
    Operation,
    Read,
    prepare,
    read_script,
)
from app.adapters.mongodb.values import (
    FieldSample,
    column_type,
    joined,
    read_cell,
    relaxed_json,
    tag_of,
)
from app.adapters.protocol import AdapterError
from app.adapters.query import (
    GeneratedQuery,
    GenerateQueryRequest,
    MaterialisedResult,
    PreparedScript,
    QueryDiagnostic,
    QueryEvent,
    QueryLimits,
    QueryMetadata,
    QueryMetadataRequest,
    QueryProfile,
    QueryRequest,
    RelationSummary,
    ResultColumn,
    SchemaEffect,
    StatementFinished,
    StatementStarted,
    StatementStatus,
)
from app.core.translation import N_, say

DEFAULT_TIMEOUT_SECONDS = 30
MAX_TIMEOUT_SECONDS = 300
MAX_MESSAGE_CHARS = 500
# How much longer this module waits than the driver's own limit before it
# cancels the call itself.
_GRACE_SECONDS = 5

# The categories of a failure, by the server's error code. Unlisted is `unknown`.
_CATEGORIES: dict[int, str] = {
    2: "data",
    9: "syntax",
    13: "permission",
    14: "data",
    26: "missing_object",
    27: "missing_object",
    40: "data",
    48: "data",
    50: "timeout",
    52: "data",
    59: "syntax",
    66: "data",
    67: "data",
    72: "syntax",
    85: "data",
    86: "data",
    121: "data",
    166: "data",
    168: "syntax",
    292: "resource",
    11000: "data",
    11601: "cancelled",
    15998: "syntax",
    16410: "syntax",
    40324: "syntax",
}

_ADMITTED: dict[str, frozenset[str]] = {
    "read": frozenset({"read"}),
    "auto_commit": frozenset({"read", "dml", "ddl", "maintenance"}),
}

_CHANGES = frozenset({"dml", "ddl", "maintenance"})

_UNSAFE = {ord(char): None for char in ("\r", "\n", "\t", "\x00")}

_NO_DATABASE = N_(
    'This connection names no database; start with "use <database>" '
    'or write db.getSiblingDB("<database>")'
)


class ResultTooLarge(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class Refused(Exception):
    """An option or an argument the call cannot take, found as it is built."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass
class Outcome:
    result: MaterialisedResult | None = None
    command_tag: str | None = None
    affected_rows: int | None = None


def _safe_text(value: Any, fallback: str) -> str:
    if not isinstance(value, str) or not value:
        return fallback
    return value.translate(_UNSAFE).strip()[:MAX_MESSAGE_CHARS] or fallback


def diagnostic_of(exc: OperationFailure, *, cancelled: bool, timed_out: bool) -> QueryDiagnostic:
    """A failure reduced to what may be shown (D64).

    The server's own sentence is passed on, as PostgreSQL's primary message
    is: it is about the statement somebody wrote. A write's first error stands
    for the write.
    """
    code = exc.code
    details = exc.details or {}
    message = details.get("errmsg")
    if isinstance(exc, BulkWriteError):
        first = (details.get("writeErrors") or [{}])[0]
        code = first.get("code", code)
        message = first.get("errmsg")
    category = _CATEGORIES.get(code or 0, "unknown")
    text = _safe_text(message, say("The statement could not be run"))
    if cancelled or category == "cancelled":
        category, text = "cancelled", say("Cancelled")
    elif timed_out or category == "timeout":
        category, text = "timeout", say("The statement ran out of time")
    return QueryDiagnostic(
        code=str(code or "unknown"),
        category=category,  # type: ignore[arg-type]  # the table above holds the union's members
        message=text,
    )


def _items(value: Any) -> Any:
    """A key document as the driver's list of pairs; a name stays a name."""
    return list(value.items()) if isinstance(value, Mapping) else value


def _options(given: Any, allowed: Mapping[str, str], method: str) -> dict[str, Any]:
    """The shell's option document as the driver's keywords, refusing the rest."""
    if given is None:
        return {}
    if not isinstance(given, Mapping):
        raise Refused(say("The options of {method} are a document", method=method))
    out: dict[str, Any] = {}
    for name, value in given.items():
        keyword = allowed.get(name)
        if keyword is None:
            raise Refused(say("{method} does not take the option {name}", method=method, name=name))
        out[keyword] = value
    return out


def _seconds(limits: QueryLimits, options: dict[str, Any]) -> float:
    """The statement's limit, or the shell's own `maxTimeMS` when it is shorter."""
    asked = options.pop("maxTimeMS", None)
    seconds = float(limits.statement_timeout_seconds)
    if isinstance(asked, (int, float)) and not isinstance(asked, bool) and asked > 0:
        seconds = min(seconds, asked / 1000)
    return seconds


_FIND_OPTIONS = {
    "sort": "sort",
    "limit": "limit",
    "skip": "skip",
    "projection": "projection",
    "hint": "hint",
    "collation": "collation",
    "comment": "comment",
    "maxTimeMS": "maxTimeMS",
    "batchSize": "batch_size",
    "allowDiskUse": "allow_disk_use",
}
_AGGREGATE_OPTIONS = {
    "allowDiskUse": "allowDiskUse",
    "collation": "collation",
    "hint": "hint",
    "let": "let",
    "comment": "comment",
    "batchSize": "batchSize",
    "maxTimeMS": "maxTimeMS",
    "bypassDocumentValidation": "bypassDocumentValidation",
}
_COUNT_OPTIONS = {
    "limit": "limit",
    "skip": "skip",
    "hint": "hint",
    "collation": "collation",
    "maxTimeMS": "maxTimeMS",
}
_UPDATE_OPTIONS = {
    "upsert": "upsert",
    "arrayFilters": "array_filters",
    "collation": "collation",
    "hint": "hint",
    "let": "let",
    "bypassDocumentValidation": "bypass_document_validation",
}
_REPLACE_OPTIONS = {key: value for key, value in _UPDATE_OPTIONS.items() if key != "arrayFilters"}
_DELETE_OPTIONS = {"collation": "collation", "hint": "hint", "let": "let"}
_FIND_AND_OPTIONS = {
    "projection": "projection",
    "sort": "sort",
    "upsert": "upsert",
    "returnDocument": "returnDocument",
    "returnNewDocument": "returnNewDocument",
    "arrayFilters": "array_filters",
    "collation": "collation",
    "hint": "hint",
    "let": "let",
    "bypassDocumentValidation": "bypass_document_validation",
    "maxTimeMS": "maxTimeMS",
}


def _returned(options: dict[str, Any]) -> None:
    after = options.pop("returnDocument", None) == "after"
    after = options.pop("returnNewDocument", None) is True or after
    options["return_document"] = ReturnDocument.AFTER if after else ReturnDocument.BEFORE


def _sorted(options: dict[str, Any]) -> None:
    for name in ("sort", "hint"):
        if name in options:
            options[name] = _items(options[name])


def _limit(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise Refused(say("A limit is a whole number"))
    # A negative limit is the shell's one batch of that many.
    return abs(int(value))


def _effect(operation: Operation, database: str) -> SchemaEffect | None:
    """What a change means for the catalog on screen (D66).

    A database that did not exist before is a new row at the root, so making a
    collection reloads the root as well as its database.
    """
    verb = operation.verb
    if verb == "dropDatabase":
        return SchemaEffect(reload_node_ids=[None])
    if verb in ("createCollection", "createView", "drop", "renameCollection"):
        return SchemaEffect(reload_node_ids=[None, database_id(database)])
    if verb in ("createIndex", "createIndexes", "dropIndex", "dropIndexes"):
        assert operation.collection is not None  # these are collection methods
        return SchemaEffect(relation_node_ids=[relation_id(database, operation.collection)])
    # A command, and a pipeline whose `$out` or `$merge` may name another
    # database: nothing here can say which nodes they reached.
    if verb in ("runCommand", "adminCommand", "aggregate"):
        return SchemaEffect(scope="connection")
    return None


def document_result(document: Any, limits: QueryLimits) -> MaterialisedResult:
    """One document as the tree the console draws (D296)."""
    text = relaxed_json(document)
    size = len(text.encode())
    if size > limits.max_result_bytes:
        raise ResultTooLarge(say("This result is larger than one result may be"))
    return MaterialisedResult(
        columns=[], rows=[], bytes_used=size, document=json_tree(jsontext.load(text))
    )


def rows_result(
    documents: Sequence[Mapping[str, Any]], limits: QueryLimits, *, truncated: bool = False
) -> MaterialisedResult:
    """Documents as rows: their top-level fields, `_id` first, as a page has (D284)."""
    sample = FieldSample()
    sample.read(documents)
    fields = sample.ordered()
    columns = [
        ResultColumn(id=str(position), name=found.name, type=column_type(found.tag))
        for position, found in enumerate(fields)
    ]
    rows: list[list[str | None]] = []
    used = 0
    for document in documents:
        row: list[str | None] = []
        for column in columns:
            cell = read_cell(document.get(column.name))
            size = 0 if cell is None else len(cell.encode())
            if size > limits.max_cell_bytes:
                raise ResultTooLarge(
                    say("A value in {column} is larger than one cell may be", column=column.name)
                )
            used += size
            if used > limits.max_result_bytes:
                raise ResultTooLarge(say("This result is larger than one result may be"))
            row.append(cell)
        rows.append(row)
    return MaterialisedResult(columns=columns, rows=rows, truncated=truncated, bytes_used=used)


def values_result(values: list[Any], name: str, limits: QueryLimits) -> MaterialisedResult:
    """Values that are not documents — `distinct`, a count — as one column."""
    tag = None
    for value in values:
        tag = joined(tag, tag_of(value))
    rows = rows_result([{name: value} for value in values], limits)
    rows.columns = [ResultColumn(id="0", name=name, type=column_type(tag))]
    return rows


async def _collected(cursor: Any, limits: QueryLimits) -> tuple[list[Any], bool]:
    """At most the ceiling of rows; one more establishes truncation (D64)."""
    documents: list[Any] = []
    try:
        async for document in cursor:
            if len(documents) == limits.max_result_rows:
                return documents, True
            documents.append(document)
    finally:
        await cursor.close()
    return documents, False


class MongodbExecution:
    """One run: its statements one after another, each kept as it ends."""

    def __init__(self, session: MongodbSession, request: QueryRequest) -> None:
        self._session = session
        self._request = request
        self._cancelled = False
        self._call: asyncio.Future[Outcome] | None = None
        self._comment: str | None = None
        self._run_bytes = 0
        self._run_results = 0

    def events(self) -> AsyncIterator[QueryEvent]:
        return self._run()

    async def cancel(self) -> None:
        """Stop what this run is doing; it reports the outcome itself (D64)."""
        self._cancelled = True
        call = self._call
        if call is not None and not call.done():
            call.cancel()
            await self._kill()

    async def _kill(self) -> None:
        """Ask the server to stop the operation carrying this run's comment.

        The server goes on with a call the driver has stopped waiting for, so
        it is killed by name. Best effort: a user without the right to list
        operations is still stopped by the time limit the server was told.
        """
        comment = self._comment
        if comment is None:
            return
        with contextlib.suppress(Exception):
            async with self._session.client() as client:
                with pymongo.timeout(5):
                    cursor = await client.admin.aggregate(
                        [{"$currentOp": {}}, {"$match": {"command.comment": comment}}]
                    )
                    for operation in await cursor.to_list():
                        await client.admin.command("killOp", op=operation["opid"])

    async def _run(self) -> AsyncIterator[QueryEvent]:
        reads = read_script(self._request.text)
        started = time.monotonic()
        limits = self._request.limits
        database = next((name for name in self._request.search_path if name), None)
        database = database or self._session.database() or None
        alone = sum(1 for read in reads if read.operation is None or read.operation.verb != "use") <= 1
        stopped = False
        for read in reads:
            ordinal = read.statement.ordinal
            if stopped:
                yield StatementFinished(ordinal=ordinal, status="not_run", duration_ms=0)
                continue
            if self._cancelled:
                yield StatementFinished(ordinal=ordinal, status="cancelled", duration_ms=0)
                stopped = True
                continue
            if time.monotonic() - started > limits.script_timeout_seconds:
                yield StatementFinished(ordinal=ordinal, status="timed_out", duration_ms=0)
                stopped = True
                continue
            yield StatementStarted(ordinal=ordinal)
            finished = await self._one(read, database, limits, alone=alone)
            if finished.status == "succeeded" and read.operation is not None and read.operation.verb == "use":
                database = read.operation.database
            yield finished
            stopped = finished.status != "succeeded"

    def _refused(self, read: Read, alone: bool) -> QueryDiagnostic | None:
        statement = read.statement
        mode = self._request.mode
        if statement.refused is not None or read.operation is None:
            return QueryDiagnostic(
                code="dp_not_admitted",
                category="syntax",
                message=statement.refused or say("The statement could not be run"),
            )
        if statement.kind not in _ADMITTED.get(mode, frozenset()):
            if mode == "read":
                message = say("A {kind} statement cannot run in a read", kind=statement.kind)
            else:
                message = say("A {kind} statement is not run here", kind=statement.kind)
            return QueryDiagnostic(code="dp_not_admitted", category="read_only", message=message)
        if statement.kind in _CHANGES and not alone:
            return QueryDiagnostic(
                code="dp_not_admitted",
                category="read_only",
                message=say(
                    "MongoDB keeps a change the moment it is made and cannot undo it, "
                    "so a change cannot share a run with other statements; run it on its own"
                ),
            )
        return None

    async def _one(
        self, read: Read, database: str | None, limits: QueryLimits, *, alone: bool
    ) -> StatementFinished:
        statement = read.statement
        refused = self._refused(read, alone)
        if refused is not None:
            return StatementFinished(
                ordinal=statement.ordinal, status="failed", duration_ms=0, diagnostic=refused
            )
        operation = read.operation
        assert operation is not None  # refused above when there is none
        target = operation.database or database
        if operation.verb == "adminCommand":
            target = "admin"
        listing_databases = operation.verb == "show" and operation.args == ("databases",)
        if target is None and operation.verb != "use" and not listing_databases:
            return StatementFinished(
                ordinal=statement.ordinal,
                status="failed",
                duration_ms=0,
                diagnostic=QueryDiagnostic(
                    code="dp_no_database", category="missing_object", message=say(_NO_DATABASE)
                ),
            )
        began = time.monotonic()
        self._comment = f"dataplayer:{uuid.uuid4()}"
        timed_out = False
        call = asyncio.ensure_future(self._carry_out(operation, target or "", limits))
        self._call = call
        try:
            done, _ = await asyncio.wait(
                {call}, timeout=limits.statement_timeout_seconds + _GRACE_SECONDS
            )
            if not done:
                timed_out = True
                call.cancel()
                await self._kill()
            outcome = await call
        except asyncio.CancelledError:
            if call.cancelled() and (self._cancelled or timed_out):
                return self._stopped(statement.ordinal, began, timed_out)
            raise
        except ResultTooLarge as refusal:
            return StatementFinished(
                ordinal=statement.ordinal,
                status="succeeded",
                duration_ms=self._since(began),
                diagnostic=QueryDiagnostic(
                    code="result_too_large", category="resource", message=refusal.message
                ),
            )
        except Refused as refusal:
            return self._failed(statement.ordinal, began, "dp_refused", "syntax", refusal.message)
        except OperationFailure as exc:
            diagnostic = diagnostic_of(exc, cancelled=self._cancelled, timed_out=timed_out)
            status: StatementStatus = "failed"
            if diagnostic.category == "cancelled":
                status = "cancelled"
            elif diagnostic.category == "timeout":
                status = "timed_out"
            return StatementFinished(
                ordinal=statement.ordinal,
                status=status,
                duration_ms=self._since(began),
                diagnostic=diagnostic,
            )
        except (BSONError, OverflowError) as exc:
            del exc
            return self._failed(
                statement.ordinal, began, "dp_bson", "data", say("A value here cannot be stored in BSON")
            )
        except PyMongoError as exc:
            if exc.timeout and not isinstance(exc, ServerSelectionTimeoutError):
                return self._stopped(statement.ordinal, began, timed_out=True)
            if (self._cancelled or timed_out) and isinstance(exc, ConnectionFailure):
                return self._stopped(statement.ordinal, began, timed_out)
            error_kind, message = classify(exc, fallback_message=N_("The query could not be run"))
            raise AdapterError(error_kind, message) from None
        finally:
            self._call = None
        if self._cancelled or timed_out:
            return self._stopped(statement.ordinal, began, timed_out)
        result = outcome.result
        if result is not None:
            self._count(result)
        effect = None
        if statement.kind == "ddl" or (operation.verb == "aggregate" and statement.kind == "dml"):
            effect = _effect(operation, target or "")
        return StatementFinished(
            ordinal=statement.ordinal,
            status="succeeded",
            duration_ms=self._since(began),
            command_tag=outcome.command_tag,
            row_count=None if result is None or result.document is not None else len(result.rows),
            affected_rows=outcome.affected_rows,
            result=result,
            effect=effect,
        )

    def _count(self, result: MaterialisedResult) -> None:
        limits = self._request.limits
        self._run_bytes += result.bytes_used
        self._run_results += 1
        if self._run_results > limits.max_run_results:
            raise ResultTooLarge(say("This run produced more results than one run may hold"))
        if self._run_bytes > limits.max_run_bytes:
            raise ResultTooLarge(say("This run produced more data than one run may hold"))

    def _failed(
        self, ordinal: int, began: float, code: str, category: str, message: str
    ) -> StatementFinished:
        return StatementFinished(
            ordinal=ordinal,
            status="failed",
            duration_ms=self._since(began),
            diagnostic=QueryDiagnostic(
                code=code,
                category=category,  # type: ignore[arg-type]  # callers pass members of the union
                message=message,
            ),
        )

    def _stopped(self, ordinal: int, began: float, timed_out: bool) -> StatementFinished:
        cancelled = self._cancelled and not timed_out
        return StatementFinished(
            ordinal=ordinal,
            status="cancelled" if cancelled else "timed_out",
            duration_ms=self._since(began),
            diagnostic=QueryDiagnostic(
                code="11601" if cancelled else "50",
                category="cancelled" if cancelled else "timeout",
                message=say("Cancelled") if cancelled else say("The statement ran out of time"),
            ),
        )

    @staticmethod
    def _since(began: float) -> int:
        return int((time.monotonic() - began) * 1000)

    async def _carry_out(self, operation: Operation, database: str, limits: QueryLimits) -> Outcome:
        async with self._session.client() as client:
            return await _Call(client, operation, database, limits, self._comment).run()


class _Call:
    """One operation carried out on one client."""

    def __init__(
        self,
        client: Client,
        operation: Operation,
        database: str,
        limits: QueryLimits,
        comment: str | None,
    ) -> None:
        self.client = client
        self.operation = operation
        self.database = database
        self.limits = limits
        self.comment = comment

    def arg(self, index: int, default: Any = None) -> Any:
        args = self.operation.args
        return args[index] if len(args) > index else default

    async def run(self) -> Outcome:
        operation = self.operation
        verb = operation.verb
        if verb == "use":
            return Outcome(command_tag=say("switched to db {name}", name=operation.database))
        if verb == "show":
            return await self._show()
        if operation.collection is None:
            return await self._database_level()
        if operation.explain is not None:
            return await self._explain()
        method = getattr(self, f"_{verb}")
        result: Outcome = await method()
        return result

    def _timed(self, options: dict[str, Any] | None = None) -> Any:
        return pymongo.timeout(_seconds(self.limits, options if options is not None else {}))

    @property
    def collection(self) -> Any:
        assert self.operation.collection is not None  # a collection method
        return self.client[self.database][self.operation.collection]

    def comment_of(self, options: dict[str, Any]) -> Any:
        """The comment a call carries; the shell's own when it set one, which
        Stop then cannot find the operation by."""
        return options.pop("comment", self.comment)

    async def _show(self) -> Outcome:
        with self._timed():
            if self.arg(0) == "databases":
                listing = await self.client.list_databases(comment=self.comment)
                found = await listing.to_list()
                documents = [
                    {"name": one["name"], "sizeOnDisk": one.get("sizeOnDisk"), "empty": one.get("empty")}
                    for one in found
                ]
                return Outcome(result=rows_result(documents, self.limits))
            names = await self.client[self.database].list_collection_names(comment=self.comment)
        return Outcome(result=values_result(sorted(names), "name", self.limits))

    async def _database_level(self) -> Outcome:
        operation = self.operation
        verb = operation.verb
        database = self.client[self.database]
        with self._timed():
            if verb in ("runCommand", "adminCommand"):
                first = self.arg(0)
                command = {first: 1} if isinstance(first, str) else dict(first)
                target = self.client.admin if verb == "adminCommand" else database
                answer = await target.command(command, comment=self.comment)
                return Outcome(result=document_result(answer, self.limits))
            if verb == "getCollectionNames":
                names = await database.list_collection_names(filter=self.arg(0), comment=self.comment)
                return Outcome(result=values_result(sorted(names), "name", self.limits))
            if verb == "getCollectionInfos":
                options = _options(
                    self.arg(1),
                    {"nameOnly": "nameOnly", "authorizedCollections": "authorizedCollections"},
                    verb,
                )
                cursor = await database.list_collections(filter=self.arg(0), comment=self.comment, **options)
                documents, truncated = await _collected(cursor, self.limits)
                return Outcome(result=rows_result(documents, self.limits, truncated=truncated))
            if verb == "stats":
                scale = self.arg(0)
                if isinstance(scale, Mapping):
                    scale = scale.get("scale")
                extra = {} if scale is None else {"scale": scale}
                answer = await database.command("dbStats", comment=self.comment, **extra)
                return Outcome(result=document_result(answer, self.limits))
            if verb == "createCollection":
                options = dict(self.arg(1) or {})
                options.pop("maxTimeMS", None)
                await database.create_collection(self.arg(0), comment=self.comment, **options)
                return Outcome(command_tag=say("Created collection {name}", name=self.arg(0)))
            if verb == "createView":
                options = dict(self.arg(3) or {})
                view: dict[str, Any] = {"create": self.arg(0), "viewOn": self.arg(1), "pipeline": self.arg(2)}
                view.update(options)
                await database.command(view, comment=self.comment)
                return Outcome(command_tag=say("Created view {name}", name=self.arg(0)))
            if verb == "dropDatabase":
                await self.client.drop_database(self.database, comment=self.comment)
                return Outcome(command_tag=say("Dropped database {name}", name=self.database))
        raise Refused(say("The statement could not be run"))

    async def _explain(self) -> Outcome:
        operation = self.operation
        name = operation.collection
        if operation.verb == "find":
            inner: dict[str, Any] = {"find": name, "filter": self.arg(0, {})}
            if self.arg(1) is not None:
                inner["projection"] = self.arg(1)
            options = _options(self.arg(2), _FIND_OPTIONS, "find")
            for modifier, args in operation.cursor:
                if modifier in _FIND_OPTIONS and args:
                    options[_FIND_OPTIONS[modifier]] = args[0]
            for key, value in options.items():
                if key in ("sort", "limit", "skip", "projection", "hint", "collation"):
                    inner[key] = value
        else:
            inner = {"aggregate": name, "pipeline": self.arg(0, []), "cursor": {}}
            options = _options(self.arg(1), _AGGREGATE_OPTIONS, "aggregate")
            options.pop("comment", None)
            options.pop("batchSize", None)
            inner.update({key: value for key, value in options.items() if key != "maxTimeMS"})
        with self._timed(options):
            answer = await self.client[self.database].command(
                {"explain": inner, "verbosity": operation.explain}, comment=self.comment
            )
        return Outcome(result=document_result(answer, self.limits))

    async def _find(self) -> Outcome:
        options = _options(self.arg(2), _FIND_OPTIONS, "find")
        for modifier, args in self.operation.cursor:
            if modifier in ("toArray", "pretty"):
                continue
            keyword = _FIND_OPTIONS[modifier]
            options[keyword] = args[0] if args else True
        projection = options.pop("projection", self.arg(1))
        if "limit" in options:
            options["limit"] = _limit(options["limit"])
        _sorted(options)
        options["comment"] = self.comment_of(options)
        with self._timed(options):
            cursor = self.collection.find(self.arg(0, {}), projection, **options)
            documents, truncated = await _collected(cursor, self.limits)
        return Outcome(result=rows_result(documents, self.limits, truncated=truncated))

    async def _findOne(self) -> Outcome:  # noqa: N802 — named for the shell's method
        options = _options(self.arg(2), _FIND_OPTIONS, "findOne")
        projection = options.pop("projection", self.arg(1))
        _sorted(options)
        options["comment"] = self.comment_of(options)
        with self._timed(options):
            found = await self.collection.find_one(self.arg(0, {}), projection, **options)
        return Outcome(result=rows_result([] if found is None else [found], self.limits))

    async def _aggregate(self) -> Outcome:
        pipeline = list(self.arg(0, []))
        options = _options(self.arg(1), _AGGREGATE_OPTIONS, "aggregate")
        let = options.pop("let", None)
        comment = self.comment_of(options)
        writes = bool(pipeline) and isinstance(pipeline[-1], Mapping) and (
            "$out" in pipeline[-1] or "$merge" in pipeline[-1]
        )
        with self._timed(options):
            cursor = await self.collection.aggregate(pipeline, let=let, comment=comment, **options)
            documents, truncated = await _collected(cursor, self.limits)
        if writes:
            return Outcome(command_tag=say("The pipeline wrote its output"))
        return Outcome(result=rows_result(documents, self.limits, truncated=truncated))

    async def _countDocuments(self) -> Outcome:  # noqa: N802 — named for the shell's method
        options = _options(self.arg(1), _COUNT_OPTIONS, "countDocuments")
        with self._timed(options):
            count = await self.collection.count_documents(self.arg(0, {}), comment=self.comment, **options)
        return Outcome(result=values_result([count], "count", self.limits))

    async def _estimatedDocumentCount(self) -> Outcome:  # noqa: N802 — named for the shell's method
        options = _options(self.arg(0), {"maxTimeMS": "maxTimeMS"}, "estimatedDocumentCount")
        with self._timed(options):
            count = await self.collection.estimated_document_count(comment=self.comment)
        return Outcome(result=values_result([count], "count", self.limits))

    async def _distinct(self) -> Outcome:
        options = _options(self.arg(2), {"collation": "collation", "maxTimeMS": "maxTimeMS"}, "distinct")
        with self._timed(options):
            values = await self.collection.distinct(
                self.arg(0), self.arg(1), comment=self.comment, **options
            )
        if len(values) > self.limits.max_result_rows:
            return Outcome(result=_truncated(values_result(values[: self.limits.max_result_rows], "value", self.limits)))
        return Outcome(result=values_result(values, "value", self.limits))

    async def _getIndexes(self) -> Outcome:  # noqa: N802 — named for the shell's method
        with self._timed():
            cursor = await self.collection.list_indexes(comment=self.comment)
            documents, truncated = await _collected(cursor, self.limits)
        return Outcome(result=rows_result(documents, self.limits, truncated=truncated))

    async def _insertOne(self) -> Outcome:  # noqa: N802 — named for the shell's method
        options = _options(
            self.arg(1), {"bypassDocumentValidation": "bypass_document_validation"}, "insertOne"
        )
        with self._timed():
            done = await self.collection.insert_one(self.arg(0), comment=self.comment, **options)
        answer = {"acknowledged": done.acknowledged, "insertedId": done.inserted_id}
        return Outcome(result=document_result(answer, self.limits), command_tag="insertOne", affected_rows=1)

    async def _insertMany(self) -> Outcome:  # noqa: N802 — named for the shell's method
        options = _options(
            self.arg(1),
            {"ordered": "ordered", "bypassDocumentValidation": "bypass_document_validation"},
            "insertMany",
        )
        with self._timed():
            done = await self.collection.insert_many(self.arg(0), comment=self.comment, **options)
        answer = {
            "acknowledged": done.acknowledged,
            "insertedIds": {str(index): one for index, one in enumerate(done.inserted_ids)},
        }
        return Outcome(
            result=document_result(answer, self.limits),
            command_tag="insertMany",
            affected_rows=len(done.inserted_ids),
        )

    async def _update(self, many: bool, replace: bool) -> Outcome:
        verb = self.operation.verb
        options = _options(self.arg(2), _REPLACE_OPTIONS if replace else _UPDATE_OPTIONS, verb)
        collection = self.collection
        with self._timed():
            if replace:
                done = await collection.replace_one(self.arg(0), self.arg(1), comment=self.comment, **options)
            elif many:
                done = await collection.update_many(self.arg(0), self.arg(1), comment=self.comment, **options)
            else:
                done = await collection.update_one(self.arg(0), self.arg(1), comment=self.comment, **options)
        upserted = 0 if done.upserted_id is None else 1
        answer = {
            "acknowledged": done.acknowledged,
            "insertedId": done.upserted_id,
            "matchedCount": done.matched_count,
            "modifiedCount": done.modified_count,
            "upsertedCount": upserted,
        }
        return Outcome(
            result=document_result(answer, self.limits),
            command_tag=verb,
            affected_rows=done.modified_count + upserted,
        )

    async def _updateOne(self) -> Outcome:  # noqa: N802 — named for the shell's method
        return await self._update(many=False, replace=False)

    async def _updateMany(self) -> Outcome:  # noqa: N802 — named for the shell's method
        return await self._update(many=True, replace=False)

    async def _replaceOne(self) -> Outcome:  # noqa: N802 — named for the shell's method
        return await self._update(many=False, replace=True)

    async def _delete(self, many: bool) -> Outcome:
        verb = self.operation.verb
        options = _options(self.arg(1), _DELETE_OPTIONS, verb)
        collection = self.collection
        with self._timed():
            if many:
                done = await collection.delete_many(self.arg(0), comment=self.comment, **options)
            else:
                done = await collection.delete_one(self.arg(0), comment=self.comment, **options)
        answer = {"acknowledged": done.acknowledged, "deletedCount": done.deleted_count}
        return Outcome(
            result=document_result(answer, self.limits), command_tag=verb, affected_rows=done.deleted_count
        )

    async def _deleteOne(self) -> Outcome:  # noqa: N802 — named for the shell's method
        return await self._delete(many=False)

    async def _deleteMany(self) -> Outcome:  # noqa: N802 — named for the shell's method
        return await self._delete(many=True)

    async def _find_and(self, kind: str) -> Outcome:
        verb = self.operation.verb
        allowed = dict(_FIND_AND_OPTIONS)
        if kind != "update":
            allowed.pop("arrayFilters")
        if kind == "delete":
            for name in ("upsert", "returnDocument", "returnNewDocument", "bypassDocumentValidation"):
                allowed.pop(name)
        options = _options(self.arg(1 if kind == "delete" else 2), allowed, verb)
        _sorted(options)
        collection = self.collection
        with self._timed(options):
            if kind == "delete":
                found = await collection.find_one_and_delete(self.arg(0), comment=self.comment, **options)
            else:
                _returned(options)
                change = (
                    collection.find_one_and_update if kind == "update" else collection.find_one_and_replace
                )
                found = await change(self.arg(0), self.arg(1), comment=self.comment, **options)
        return Outcome(
            result=rows_result([] if found is None else [found], self.limits), command_tag=verb
        )

    async def _findOneAndUpdate(self) -> Outcome:  # noqa: N802 — named for the shell's method
        return await self._find_and("update")

    async def _findOneAndReplace(self) -> Outcome:  # noqa: N802 — named for the shell's method
        return await self._find_and("replace")

    async def _findOneAndDelete(self) -> Outcome:  # noqa: N802 — named for the shell's method
        return await self._find_and("delete")

    def _index_options(self, given: Any) -> dict[str, Any]:
        if given is None:
            return {}
        if not isinstance(given, Mapping):
            raise Refused(say("The options of {method} are a document", method=self.operation.verb))
        # An index's options are the server's to check: they go into its spec.
        return {name: value for name, value in given.items() if name != "maxTimeMS"}

    async def _createIndex(self) -> Outcome:  # noqa: N802 — named for the shell's method
        options = self._index_options(self.arg(1))
        with self._timed():
            name = await self.collection.create_index(_items(self.arg(0)), comment=self.comment, **options)
        return Outcome(command_tag=say("Created index {name}", name=name))

    async def _createIndexes(self) -> Outcome:  # noqa: N802 — named for the shell's method
        options = self._index_options(self.arg(1))
        models = [IndexModel(_items(keys), **options) for keys in self.arg(0)]
        with self._timed():
            names = await self.collection.create_indexes(models, comment=self.comment)
        return Outcome(command_tag=say("Created indexes {names}", names=", ".join(names)))

    async def _dropIndex(self) -> Outcome:  # noqa: N802 — named for the shell's method
        index = self.arg(0)
        with self._timed():
            await self.collection.drop_index(_items(index), comment=self.comment)
        named = index if isinstance(index, str) else relaxed_json(index)
        return Outcome(command_tag=say("Dropped index {name}", name=named))

    async def _dropIndexes(self) -> Outcome:  # noqa: N802 — named for the shell's method
        given = self.arg(0)
        with self._timed():
            if given is None or given == "*":
                await self.collection.drop_indexes(comment=self.comment)
                return Outcome(command_tag=say("Dropped every index but _id"))
            names = given if isinstance(given, list) else [given]
            for name in names:
                await self.collection.drop_index(_items(name), comment=self.comment)
        return Outcome(command_tag=say("Dropped indexes {names}", names=", ".join(map(str, names))))

    async def _drop(self) -> Outcome:
        with self._timed():
            await self.collection.drop(comment=self.comment)
        return Outcome(command_tag=say("Dropped collection {name}", name=self.operation.collection))

    async def _renameCollection(self) -> Outcome:  # noqa: N802 — named for the shell's method
        with self._timed():
            await self.collection.rename(
                self.arg(0), comment=self.comment, dropTarget=self.arg(1) is True
            )
        return Outcome(
            command_tag=say(
                "Renamed {name} to {new}", name=self.operation.collection, new=self.arg(0)
            )
        )


def _truncated(result: MaterialisedResult) -> MaterialisedResult:
    result.truncated = True
    return result


_IDENTIFIER = re.compile(r"[A-Za-z_$][\w$]*")


def collection_text(database: str, collection: str, default: str) -> str:
    """How the shell names a collection, the database only when it is not the
    connection's own."""
    prefix = "db" if database == default else f"db.getSiblingDB({json.dumps(database, ensure_ascii=False)})"
    if _IDENTIFIER.fullmatch(collection) and collection not in DATABASE_METHODS:
        return f"{prefix}.{collection}"
    return f"{prefix}.getCollection({json.dumps(collection, ensure_ascii=False)})"


class MongodbQuery:
    """MongoDB as a source that accepts the shell's syntax (D62, D296)."""

    def __init__(self, session: MongodbSession, relation: MongodbRelation) -> None:
        self._session = session
        self._relation = relation

    def profile(self) -> QueryProfile:
        return QueryProfile(
            dialect="mongodb",
            parameter_syntax="none",
            editor_language="javascript",
            # No manual transaction: a change is kept as it ends (D296).
            statement_modes=["read", "auto_commit"],
            supports_cancel=True,
            default_timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
            max_timeout_seconds=MAX_TIMEOUT_SECONDS,
        )

    def prepare(self, text: str) -> PreparedScript:
        return prepare(text)

    def open(self, request: QueryRequest) -> MongodbExecution:
        return MongodbExecution(self._session, request)

    async def metadata(self, request: QueryMetadataRequest) -> QueryMetadata:
        """The databases, and the collections of the one the console is in.

        Never complete: a field is read from documents rather than declared,
        so the editor is never told a name does not exist (D65).
        """
        database = next((name for name in request.search_path if name), None)
        database = database or self._session.database() or None
        async with self._session.client() as client:
            with self._session.failures():
                listing = await client.admin.command(
                    "listDatabases", nameOnly=True, authorizedDatabases=True
                )
                names = [str(one["name"]) for one in listing.get("databases", [])]
                collections = (
                    [] if database is None else await client[database].list_collection_names()
                )
        return QueryMetadata(
            schemas=sorted(name for name in names if name not in SYSTEM_DATABASES),
            relations=[
                RelationSummary(schema_name=database or "", name=name, kind="table")
                for name in sorted(collections)
                if not name.startswith("system.")
            ],
            complete=False,
        )

    async def generate(self, request: GenerateQueryRequest) -> GeneratedQuery:
        database, collection = parse(request.node_id)
        if collection is None or "\\" in request.node_id[:1]:
            raise ValueError(say("A statement is written about a collection"))
        named = collection_text(database, collection, self._session.database())
        if request.kind == "name":
            return GeneratedQuery(text=named)
        if request.kind == "columns":
            model = await self._relation.relation_model(request.node_id)
            fields = ", ".join(
                f"{_key(column.name)}: 1" for column in model.columns if column.name != "_id"
            )
            return GeneratedQuery(text=f"{{ {fields} }}" if fields else "{}")
        return GeneratedQuery(text=f"{named}.find({{}}).limit(100)")


def _key(name: str) -> str:
    return name if _IDENTIFIER.fullmatch(name) else json.dumps(name, ensure_ascii=False)
