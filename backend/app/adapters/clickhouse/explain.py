"""Planning a statement without running it (D65).

`EXPLAIN json = 1, description = 1, indexes = 1` is the tree, and the same
EXPLAIN as text is what a person reads in clickhouse-client; both run under
`readonly=2` in the database a read would have. A plan step says what it does
and which indexes it uses, and nothing about cost: ClickHouse estimates no
cost and no rows for a plan.
"""

import json
from typing import Any

from app.adapters.clickhouse.query import database_of, diagnostic_of, values_of
from app.adapters.clickhouse.session import ClickhouseSession, ServerError, classify
from app.adapters.clickhouse.statements import prepare
from app.adapters.protocol import AdapterError
from app.adapters.query import ExplainNode, ExplainRequest, ExplainResult
from app.core.translation import N_, say

MAX_NODES = 2000
MAX_DETAIL_CHARS = 500

_NAMED = {"Node Type", "Node Id", "Description", "Plans"}


class _Counter:
    def __init__(self) -> None:
        self.kept = 0
        self.cut = False


def _detail(value: Any) -> str:
    if isinstance(value, str):
        return value[:MAX_DETAIL_CHARS]
    return json.dumps(value, ensure_ascii=False, separators=(", ", ": "))[:MAX_DETAIL_CHARS]


def _relation(block: dict[str, Any]) -> str | None:
    """The table a reading step reads, which its description names."""
    kind = str(block.get("Node Type", ""))
    description = block.get("Description")
    if kind.startswith("ReadFrom") and isinstance(description, str):
        return description
    return None


def _node_of(block: dict[str, Any], path: str, counted: _Counter) -> ExplainNode:
    counted.kept += 1
    children: list[ExplainNode] = []
    for index, child in enumerate(block.get("Plans") or []):
        if counted.kept >= MAX_NODES:
            counted.cut = True
            break
        if isinstance(child, dict):
            children.append(_node_of(child, f"{path}.{index}", counted))
    kind = str(block.get("Node Type", "Step"))
    description = block.get("Description")
    return ExplainNode(
        id=path,
        kind=kind,
        label=f"{kind} ({description})" if isinstance(description, str) else kind,
        relation=_relation(block),
        details={key: _detail(value) for key, value in block.items() if key not in _NAMED},
        children=children,
    )


class ClickhouseExplain:
    def __init__(self, session: ClickhouseSession) -> None:
        self._session = session

    async def explain(self, request: ExplainRequest) -> ExplainResult:
        statements = prepare(request.text).statements
        if len(statements) != 1:
            raise ValueError(say("Explain takes one statement"))
        statement = statements[0]
        if statement.kind == "explain":
            raise ValueError(say("This is already an Explain"))
        if statement.kind != "read" or statement.refused is not None:
            raise ValueError(say("A {kind} statement is not planned here", kind=statement.kind))
        values = values_of(request.parameters, statement)
        settings = {"max_execution_time": str(request.timeout_seconds)}
        try:
            database = await database_of(self._session, request.search_path)
            if database is not None:
                settings["database"] = database
            tree = await self._session.answer(
                f"EXPLAIN json = 1, description = 1, indexes = 1 {statement.text}",
                values,
                settings=settings,
                server_errors=True,
            )
            printed = await self._session.answer(
                f"EXPLAIN description = 1, indexes = 1 {statement.text}",
                values,
                settings=settings,
                server_errors=True,
            )
        except AdapterError:
            raise
        except ServerError as exc:
            raise ValueError(diagnostic_of(exc, cancelled=False, timed_out=False).message) from None
        except Exception as exc:
            error_kind, message = classify(exc, fallback_message=N_("The plan could not be read"))
            raise AdapterError(error_kind, message) from None
        text = "".join(str(row[0]) for row in tree.rows)
        try:
            answered = json.loads(text)
        except ValueError:
            answered = None
        block = (
            answered[0].get("Plan")
            if isinstance(answered, list) and answered and isinstance(answered[0], dict)
            else None
        )
        if not isinstance(block, dict):
            raise ValueError(say("The source answered with no plan"))
        counted = _Counter()
        plan = _node_of(block, "0", counted)
        return ExplainResult(
            plan=plan,
            raw="\n".join(str(row[0]) for row in printed.rows),
            truncated=counted.cut,
        )
