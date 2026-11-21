"""Planning a statement without running it (D65, D394).

`EXPLAIN (FORMAT JSON)` gives the plan as a tree of operators, each with its
name and what DuckDB says about it; the raw text is DuckDB's own drawing of
the same plan. A row change is planned too, since planning it does not carry
it out, and the plan is read in a transaction that is rolled back.
"""

import json
from typing import Any

import duckdb

from app.adapters.duckdb.query import diagnostic_of, opened
from app.adapters.duckdb.session import DuckdbSession, classify
from app.adapters.duckdb.statements import prepare
from app.adapters.protocol import AdapterError
from app.adapters.query import ExplainNode, ExplainRequest, ExplainResult
from app.core.translation import N_, say

MAX_NODES = 2000

_PLANNED = frozenset({"read", "dml"})
_CARDINALITY = "Estimated Cardinality"


def _plans(
    connection: duckdb.DuckDBPyConnection, text: str, values: dict[str, str | None]
) -> tuple[str, str]:
    params = values or None
    connection.execute("BEGIN")
    try:
        tree = connection.execute(f"EXPLAIN (FORMAT JSON) {text}", params).fetchall()
        drawn = connection.execute(f"EXPLAIN {text}", params).fetchall()
    finally:
        connection.execute("ROLLBACK")
    return str(tree[0][1]) if tree else "[]", "\n".join(str(row[1]) for row in drawn)


def _text(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


class _Builder:
    def __init__(self) -> None:
        self.count = 0
        self.truncated = False

    def node(self, raw: dict[str, Any], place: str) -> ExplainNode:
        self.count += 1
        info: dict[str, Any] = raw.get("extra_info") or {}
        name = str(raw.get("name", "")).strip()
        table = info.get("Table")
        estimate = str(info.get(_CARDINALITY, "")).strip()
        children: list[ExplainNode] = []
        for index, child in enumerate(raw.get("children") or []):
            if self.count >= MAX_NODES:
                self.truncated = True
                break
            children.append(self.node(child, f"{place}.{index}"))
        return ExplainNode(
            id=place,
            kind=name,
            label=name if table is None else f"{name} {table}",
            relation=None if table is None else str(table),
            rows=int(estimate) if estimate.isdigit() else None,
            details={
                str(key): _text(value) for key, value in info.items() if key != _CARDINALITY
            },
            children=children,
        )


def tree_of(text: str) -> tuple[ExplainNode, bool]:
    """DuckDB's JSON plan under one root, each node at its place: "0", "0.1"."""
    roots = json.loads(text)
    builder = _Builder()
    children = [
        builder.node(raw, f"0.{index}")
        for index, raw in enumerate(roots if isinstance(roots, list) else [roots])
    ]
    return ExplainNode(id="0", kind="QUERY PLAN", label=say("Query plan"), children=children), (
        builder.truncated
    )


class DuckdbExplain:
    def __init__(self, session: DuckdbSession) -> None:
        self._session = session

    async def explain(self, request: ExplainRequest) -> ExplainResult:
        statements = prepare(request.text).statements
        if len(statements) != 1:
            raise ValueError(say("Explain takes one statement"))
        statement = statements[0]
        if statement.kind == "explain":
            raise ValueError(say("This is already an Explain"))
        if statement.refused is not None:
            raise ValueError(statement.refused)
        if statement.kind not in _PLANNED:
            raise ValueError(say("A {kind} statement is not planned here", kind=statement.kind))
        given = {parameter.name: parameter.value for parameter in request.parameters}
        values = {name: given.get(name) for name in statement.parameters}
        fallback = N_("The plan could not be read")
        handle = await opened(self._session, request.search_path, fallback)
        try:
            tree, drawn = await handle.call(
                lambda connection: _plans(connection, statement.text, values),
                seconds=request.timeout_seconds,
            )
        except duckdb.Error as exc:
            if handle.timed_out:
                raise ValueError(say("The statement ran out of time")) from None
            diagnostic = diagnostic_of(exc, self._session.home, cancelled=False, timed_out=False)
            if diagnostic.category in ("syntax", "missing_object", "data", "permission"):
                raise ValueError(diagnostic.message) from None
            error_kind, message = classify(exc, fallback_message=fallback)
            raise AdapterError(error_kind, message) from None
        finally:
            await handle.close()
        plan, truncated = tree_of(tree)
        top = plan.children[0] if plan.children else None
        return ExplainResult(
            plan=plan,
            raw=drawn,
            rows=None if top is None else top.rows,
            truncated=truncated,
        )
