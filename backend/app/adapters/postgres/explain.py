"""Planning a statement without running it.

D65: Explain is a capability of its own, separately declared. `EXPLAIN` without
`ANALYZE` plans and does not execute, and that is the whole of what is offered
here — Explain Analyze runs the statement, so it waits until its effects have
the same policy the statement itself has.

It still runs inside the read-only transaction with the same timeout and the
same validated context as a read: planning touches the catalog, and there is no
reason for it to see anything a read would not.
"""

import json
from typing import Any

import psycopg
from psycopg_pool import PoolTimeout

from app.adapters.postgres.query import diagnostic_of, set_read_context
from app.adapters.postgres.session import PostgresSession, classify
from app.adapters.postgres.statements import bind, prepare
from app.adapters.protocol import AdapterError
from app.adapters.query import ExplainNode, ExplainRequest, ExplainResult

# A plan of this many operations is already beyond reading; what is kept says
# it was cut short rather than pretending to be the whole tree.
MAX_NODES = 2000
# One detail line is a value, not a document.
MAX_DETAIL_CHARS = 500

# What is said about an operation on its own line rather than in the details.
_NAMED = {
    "Node Type",
    "Relation Name",
    "Startup Cost",
    "Total Cost",
    "Plan Rows",
    "Plan Width",
    "Plans",
    "Parent Relationship",
    "Parallel Aware",
    "Async Capable",
    "Disabled",
}


class PostgresExplain:
    """PostgreSQL's own plan for a statement, in its two published forms."""

    def __init__(self, session: PostgresSession) -> None:
        self._session = session

    async def explain(self, request: ExplainRequest) -> ExplainResult:
        script = prepare(request.text)
        statements = script.statements
        if len(statements) != 1:
            raise ValueError("Explain takes one statement")
        statement = statements[0]
        if statement.kind == "explain":
            raise ValueError("This is already an Explain")
        if statement.kind != "read":
            raise ValueError(f"A {statement.kind} statement is not planned here")

        values = (
            {
                name: next(
                    (
                        parameter.value
                        for parameter in request.parameters
                        if parameter.name == name
                    ),
                    None,
                )
                for name in statement.parameters
            }
            if statement.parameters
            else None
        )
        text = bind(statement.text) if values is not None else statement.text
        try:
            async with self._session.acquire() as connection:
                await connection.set_read_only(True)
                try:
                    async with connection.transaction():
                        await set_read_context(
                            connection,
                            search_path=request.search_path,
                            statement_timeout_seconds=request.timeout_seconds,
                        )
                        structured = await self._plan(
                            connection, f"EXPLAIN (FORMAT JSON) {text}", values
                        )
                        printed = await self._printed(
                            connection, f"EXPLAIN {text}", values
                        )
                finally:
                    await connection.set_read_only(None)
        except PoolTimeout:
            raise AdapterError("timeout", "No connection was free for this query") from None
        except psycopg.Error as exc:
            # A plan that cannot be made is the source's answer about the
            # statement, reduced the same way a failed run's is (D64).
            diagnostic = diagnostic_of(exc, cancelled=False)
            raise ValueError(diagnostic.message) from None
        except Exception as exc:
            error_kind, message = classify(exc, fallback_message="The plan could not be read")
            raise AdapterError(error_kind, message) from None

        counted = _Counter()
        plan = _node_of(structured, "0", counted)
        return ExplainResult(
            plan=plan,
            raw="\n".join(printed),
            total_cost=plan.total_cost,
            rows=plan.rows,
            truncated=counted.cut,
        )

    async def _plan(
        self,
        connection: psycopg.AsyncConnection[Any],
        statement: str,
        values: dict[str, str | None] | None,
    ) -> dict[str, Any]:
        async with connection.cursor() as cursor:
            await cursor.execute(statement, values)
            row = await cursor.fetchone()
        answered = row[0] if row is not None else None
        if isinstance(answered, str):
            answered = json.loads(answered)
        if not isinstance(answered, list) or not answered:
            raise ValueError("The source answered with no plan")
        first = answered[0]
        plan = first.get("Plan") if isinstance(first, dict) else None
        if not isinstance(plan, dict):
            raise ValueError("The source answered with no plan")
        return plan

    async def _printed(
        self,
        connection: psycopg.AsyncConnection[Any],
        statement: str,
        values: dict[str, str | None] | None,
    ) -> list[str]:
        async with connection.cursor() as cursor:
            await cursor.execute(statement, values)
            return [str(row[0]) for row in await cursor.fetchall()]


class _Counter:
    """How many operations have been kept, and whether any were left out."""

    def __init__(self) -> None:
        self.kept = 0
        self.cut = False


def _text(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)[:MAX_DETAIL_CHARS]
    return str(value)[:MAX_DETAIL_CHARS]


def _label(plan: dict[str, Any]) -> str:
    """What this operation is called on screen, in PostgreSQL's own words."""
    kind = str(plan.get("Node Type", "Operation"))
    relation = plan.get("Relation Name")
    index = plan.get("Index Name")
    if isinstance(index, str) and index:
        return f"{kind} using {index}" + (
            f" on {relation}" if isinstance(relation, str) else ""
        )
    if isinstance(relation, str) and relation:
        return f"{kind} on {relation}"
    return kind


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) else None


def _count(value: Any) -> int | None:
    return int(value) if isinstance(value, int | float) else None


def _node_of(plan: dict[str, Any], path: str, counted: _Counter) -> ExplainNode:
    counted.kept += 1
    children: list[ExplainNode] = []
    for index, child in enumerate(plan.get("Plans", []) or []):
        if counted.kept >= MAX_NODES:
            counted.cut = True
            break
        if isinstance(child, dict):
            children.append(_node_of(child, f"{path}.{index}", counted))
    relation = plan.get("Relation Name")
    return ExplainNode(
        id=path,
        kind=str(plan.get("Node Type", "Operation")),
        label=_label(plan),
        relation=relation if isinstance(relation, str) else None,
        startup_cost=_number(plan.get("Startup Cost")),
        total_cost=_number(plan.get("Total Cost")),
        rows=_count(plan.get("Plan Rows")),
        width=_count(plan.get("Plan Width")),
        details={
            key: _text(value)
            for key, value in plan.items()
            if key not in _NAMED and value not in (None, [], {}, False)
        },
        children=children,
    )
