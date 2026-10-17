"""Where one statement ends, what kind it is, and what it names.

Pure in the sense that matters: text in, prepared statements out, nothing
opened and no file touched. The engine is here only as a parser — it holds an
empty in-memory database that has never been allowed to reach a filesystem.

Two questions are answered, and both by the engine rather than by this module
guessing. Where the statements are, and what class each one belongs to, come
from DuckDB's own parser, so a semicolon inside a string or a comment is not a
boundary. What a statement refers to comes from the engine's own serialisation
of it: a table function anywhere in the tree refuses the statement, because a
table function is how a path is written in this dialect, and a text the engine
will not serialise is `unknown` rather than admitted by omission (D77).
"""

import json
import threading
from dataclasses import dataclass, field
from typing import Any

import duckdb

from app.adapters.query import PreparedScript, PreparedStatement, StatementClass
from app.core.translation import N_, say

# What each of the engine's statement types is, in the platform's vocabulary.
# Keyed by name rather than by enum member so that a type a later version of
# the engine adds arrives as `unknown` and is refused, instead of matching some
# neighbouring number.
_CLASSES: dict[str, StatementClass] = {
    "SELECT": "read",
    "EXPLAIN": "explain",
    "INSERT": "dml",
    "UPDATE": "dml",
    "DELETE": "dml",
    "MERGE_INTO": "dml",
    "CREATE": "ddl",
    "CREATE_FUNC": "ddl",
    "DROP": "ddl",
    "ALTER": "ddl",
    "VACUUM": "ddl",
    "ANALYZE": "ddl",
    "COPY": "copy",
    "COPY_DATABASE": "copy",
    "EXPORT": "copy",
    "TRANSACTION": "transaction",
    "SET": "session",
    "VARIABLE_SET": "session",
    "PRAGMA": "session",
    "LOAD": "session",
    "EXTENSION": "session",
    "PREPARE": "session",
    "EXECUTE": "session",
    "CALL": "session",
    "ATTACH": "session",
    "DETACH": "session",
}

# Why each class other than `read` will not run here. One sentence each, naming
# the family rather than the statement, because the answer is about what this
# source is and not about what somebody typed (D77). English, worded where a
# statement is prepared (D226).
REFUSALS: dict[StatementClass, str] = {
    "dml": N_(
        "This source reads files and does not change them through SQL. "
        "A file's rows are edited in its grid"
    ),
    "ddl": N_("A file has no structure that SQL could change here"),
    "copy": N_(
        "A COPY statement writes a file. Downloading a result is a command "
        "of its own"
    ),
    "transaction": N_(
        "The engine is opened for one run and thrown away, so there is no "
        "transaction to control"
    ),
    "session": N_("This source does not accept session or extension commands"),
    "explain": N_("Explain is a command of its own here, beside Run"),
    "unknown": N_("This source could not establish what this statement is"),
}

NOT_SERIALISABLE = N_("This source could not establish what this statement reads")
TABLE_FUNCTION = N_(
    "A table function names a path. This source names its own files instead: "
    'write the file, as in FROM "sales.csv"'
)
QUALIFIED = N_("This source has no schemas, so a name cannot be qualified")


@dataclass(frozen=True)
class Shape:
    """What one statement refers to, read out of the engine's own parse tree."""

    tables: list[str] = field(default_factory=list)
    qualified: list[str] = field(default_factory=list)
    table_function: bool = False
    # Whether the engine serialised the statement at all. It serialises
    # queries, so this is false for everything else and for nonsense.
    serialised: bool = False


class _Parser:
    """The engine, held open as a parser and never as a database.

    One instance per process rather than one per request: building a database
    costs about ten milliseconds, and the editor asks where the statements are
    on every pause in typing. It is safe to share because it is not allowed to
    reach anything — external access is off before the first statement and the
    configuration is locked, so even a mistake here reads no file — and because
    the one call made on it binds its argument rather than composing SQL.
    """

    def __init__(self) -> None:
        self._connection: duckdb.DuckDBPyConnection | None = None
        self._lock = threading.Lock()

    def serialise(self, text: str) -> dict[str, Any] | None:
        """The engine's parse tree for this text, or None if it will not."""
        with self._lock:
            connection = self._open()
            try:
                row = connection.execute(
                    "SELECT json_serialize_sql(?)", [text]
                ).fetchone()
            except duckdb.Error:
                return None
        if row is None or row[0] is None:
            return None
        document: Any = json.loads(str(row[0]))
        if not isinstance(document, dict) or document.get("error"):
            return None
        return document

    def statements(self, text: str) -> list[Any] | None:
        """The statements the engine finds, or None if the text does not parse."""
        try:
            return list(duckdb.extract_statements(text))
        except duckdb.Error:
            return None

    def _open(self) -> duckdb.DuckDBPyConnection:
        if self._connection is None:
            connection = duckdb.connect(
                config={
                    "enable_external_access": False,
                    "autoinstall_known_extensions": False,
                    "autoload_known_extensions": False,
                    "allow_community_extensions": False,
                    "allow_unsigned_extensions": False,
                    "threads": 1,
                }
            )
            connection.execute("SET lock_configuration=true")
            self._connection = connection
        return self._connection


_parser = _Parser()


def prepare(text: str) -> PreparedScript:
    """The statements in this text, each with its class and its refusal."""
    found = _parser.statements(text)
    if found is None:
        # The engine could not read the text as statements at all. That is one
        # unknown statement spanning what was sent, so the console marks the
        # place rather than showing nothing.
        return PreparedScript(
            statements=[
                PreparedStatement(
                    ordinal=0,
                    start=0,
                    end=len(text),
                    text=text,
                    kind="unknown",
                    refused=say(REFUSALS["unknown"]),
                )
            ]
        )

    statements: list[PreparedStatement] = []
    for ordinal, (statement, span) in enumerate(zip(found, _spans(text, found), strict=True)):
        statements.append(_prepared(text, statement, span, ordinal))
    parameters: list[str] = []
    for statement in statements:
        parameters += [name for name in statement.parameters if name not in parameters]
    return PreparedScript(statements=statements, parameters=parameters)


def shape_of(text: str) -> Shape:
    """What one statement refers to. Public because execution asks again."""
    document = _parser.serialise(text)
    if document is None:
        return Shape()
    names: list[str] = []
    qualified: list[str] = []
    table_function = False
    ctes: set[str] = set()

    def walk(node: Any) -> None:
        nonlocal table_function
        if isinstance(node, dict):
            map_ = node.get("cte_map")
            if isinstance(map_, dict):
                for entry in map_.get("map", []):
                    if isinstance(entry, dict) and isinstance(entry.get("key"), str):
                        ctes.add(entry["key"])
            kind = node.get("type")
            if kind == "TABLE_FUNCTION":
                table_function = True
            elif kind == "BASE_TABLE":
                name = node.get("table_name")
                if isinstance(name, str):
                    if node.get("schema_name") or node.get("catalog_name"):
                        qualified.append(name)
                    else:
                        names.append(name)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(document)
    # A CTE is written like a table and is not one. Its name is defined by the
    # text itself, so it never becomes a file this source has to find.
    tables = [name for name in dict.fromkeys(names) if name not in ctes]
    return Shape(
        tables=tables,
        qualified=[name for name in dict.fromkeys(qualified) if name not in ctes],
        table_function=table_function,
        serialised=True,
    )


def _prepared(
    text: str, statement: Any, span: tuple[int, int], ordinal: int
) -> PreparedStatement:
    start, end = span
    body = text[start:end].strip()
    kind = _CLASSES.get(statement.type.name, "unknown")
    refusal = REFUSALS.get(kind) if kind != "read" else None
    refused = None if refusal is None else say(refusal)
    targets: list[str] = []
    if kind == "read":
        shape = shape_of(body)
        if not shape.serialised:
            kind = "unknown"
            refused = say(NOT_SERIALISABLE)
        elif shape.table_function:
            refused = say(TABLE_FUNCTION)
        elif shape.qualified:
            refused = say(QUALIFIED)
        else:
            targets = shape.tables
    return PreparedStatement(
        ordinal=ordinal,
        start=start,
        end=end,
        text=body,
        kind=kind,
        refused=refused,
        parameters=_parameters(body, statement),
        targets=targets,
    )


def _parameters(body: str, statement: Any) -> list[str]:
    """The names this statement binds, in the order they are written.

    The engine answers with a set, and an order is what a form is filled in.
    Where a name is found decides it, and a name the search does not find —
    there is no such spelling — sorts after the ones it did.
    """
    names = {str(name) for name in statement.named_parameters}
    # An unnamed `?` is numbered by the engine. It is a binding this
    # application never asks for a value of, so it is not offered as a name.
    named = [name for name in names if not name.isdigit()]

    def written_at(name: str) -> tuple[int, str]:
        at = body.find(f"${name}")
        return (at if at >= 0 else len(body), name)

    return sorted(named, key=written_at)


def _spans(text: str, statements: list[Any]) -> list[tuple[int, int]]:
    """Where each statement sits in the text it was found in.

    The engine hands back the slice it read, so the slice is looked for. One
    form does not come back as a slice — a `PRAGMA` is rewritten into the
    query it stands for — and rather than losing every offset after it, an
    unfound statement takes the gap between the two around it.
    """
    located: list[tuple[int, int] | None] = []
    cursor = 0
    for statement in statements:
        at = text.find(statement.query, cursor)
        if at < 0:
            located.append(None)
            continue
        located.append((at, at + len(statement.query)))
        cursor = at + len(statement.query)

    spans: list[tuple[int, int]] = []
    for index, span in enumerate(located):
        if span is not None:
            spans.append(span)
            continue
        before = next(
            (found[1] for found in reversed(located[:index]) if found is not None), 0
        )
        after = next(
            (found[0] for found in located[index + 1 :] if found is not None), len(text)
        )
        spans.append((before, max(before, after)))
    return spans
