"""Planning a statement without running it (D65, D253).

`EXPLAIN QUERY PLAN`, on a connection that cannot write: SQLite answers with
one row per step — its id, its parent's id and a sentence — and no costs or
row counts, so the tree carries the sentences alone. A row change is planned
too, since planning it does not carry it out.
"""

import sqlite3
from typing import Any

from app.adapters.protocol import AdapterError
from app.adapters.query import ExplainNode, ExplainRequest, ExplainResult
from app.adapters.sqlite.query import check_search_path, diagnostic_of
from app.adapters.sqlite.session import Handle, SqliteSession, classify
from app.adapters.sqlite.statements import prepare
from app.core.translation import N_, say

MAX_NODES = 2000

_PLANNED = frozenset({"read", "dml"})


def _plan(connection: sqlite3.Connection, text: str, values: dict[str, str | None]) -> list[tuple[Any, ...]]:
    return connection.execute(f"EXPLAIN QUERY PLAN {text}", values).fetchmany(MAX_NODES + 1)


def _relation(detail: str) -> str | None:
    """The table a step reads, from `SCAN t` or `SEARCH t USING …`."""
    words = detail.split()
    if len(words) >= 2 and words[0] in ("SCAN", "SEARCH"):
        return words[1]
    return None


def tree_of(rows: list[tuple[Any, ...]]) -> ExplainNode:
    """The rows as a tree under one root, each node at its place: "0", "0.1"."""
    children: dict[int, list[tuple[int, str]]] = {}
    for row in rows:
        step, parent, detail = int(row[0]), int(row[1]), str(row[3])
        children.setdefault(parent, []).append((step, detail))

    def build(step: int, detail: str, place: str) -> ExplainNode:
        return ExplainNode(
            id=place,
            kind=" ".join(detail.split()[:1]) or detail,
            label=detail,
            relation=_relation(detail),
            children=[
                build(child, text, f"{place}.{index}")
                for index, (child, text) in enumerate(children.get(step, []))
            ],
        )

    return ExplainNode(
        id="0",
        kind="QUERY PLAN",
        label=say("Query plan"),
        children=[
            build(step, detail, f"0.{index}")
            for index, (step, detail) in enumerate(children.get(0, []))
        ],
    )


def printed(node: ExplainNode, depth: int = 0) -> list[str]:
    """The plan as SQLite's own shell draws it."""
    lines = ["QUERY PLAN"] if depth == 0 else ["   " * (depth - 1) + "|--" + node.label]
    for child in node.children:
        lines += printed(child, depth + 1)
    return lines


class SqliteExplain:
    def __init__(self, session: SqliteSession) -> None:
        self._session = session

    async def explain(self, request: ExplainRequest) -> ExplainResult:
        statements = prepare(request.text).statements
        if len(statements) != 1:
            raise ValueError(say("Explain takes one statement"))
        statement = statements[0]
        if statement.kind == "explain":
            raise ValueError(say("This is already an Explain"))
        if statement.kind not in _PLANNED:
            raise ValueError(say("A {kind} statement is not planned here", kind=statement.kind))
        check_search_path(request.search_path)
        given = {parameter.name: parameter.value for parameter in request.parameters}
        values = {name: given.get(name) for name in statement.parameters}
        handle: Handle = await self._session.handle(
            writes=False, fallback_message=N_("The plan could not be read")
        )
        try:
            rows = await handle.call(
                lambda connection: _plan(connection, statement.text, values),
                seconds=request.timeout_seconds,
            )
        except sqlite3.Error as exc:
            if handle.timed_out:
                raise ValueError(say("The statement ran out of time")) from None
            if isinstance(exc, sqlite3.OperationalError | sqlite3.ProgrammingError):
                raise ValueError(
                    diagnostic_of(exc, cancelled=False, timed_out=False).message
                ) from None
            error_kind, message = classify(exc, fallback_message=N_("The plan could not be read"))
            raise AdapterError(error_kind, message) from None
        finally:
            await handle.close()
        plan = tree_of(rows[:MAX_NODES])
        return ExplainResult(
            plan=plan, raw="\n".join(printed(plan)), truncated=len(rows) > MAX_NODES
        )
