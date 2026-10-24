"""Planning a statement without running it (D65).

`EXPLAIN FORMAT=JSON` is the tree and the tabular `EXPLAIN` is the text, both
inside a read-only transaction with the same default database a read would
have. Never `EXPLAIN ANALYZE`, which runs the statement.

MySQL and MariaDB write the JSON differently — MySQL puts costs in a
`cost_info` object of strings, MariaDB writes `cost` as a number — so the tree
is read generically: every object under a key is an operation named by that
key, every list of objects is a list of operations, and the rest is detail.
"""

import asyncio
import json
from typing import Any

import pymysql

from app.adapters.mysql.query import diagnostic_of, restore_database, use_database
from app.adapters.mysql.session import MysqlSession, classify
from app.adapters.mysql.statements import bind, bound_names, prepare
from app.adapters.protocol import AdapterError
from app.adapters.query import ExplainNode, ExplainRequest, ExplainResult
from app.core.translation import N_, say

MAX_NODES = 2000
MAX_DETAIL_CHARS = 500

# What is said about an operation on its own line rather than in its details.
_NAMED = {"table_name", "access_type", "key", "rows", "rows_examined_per_scan", "cost", "cost_info"}


class _Counter:
    def __init__(self) -> None:
        self.kept = 0
        self.cut = False


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _cost(block: dict[str, Any]) -> float | None:
    info = block.get("cost_info")
    if isinstance(info, dict):
        for key in ("query_cost", "prefix_cost", "read_cost", "sort_cost"):
            found = _number(info.get(key))
            if found is not None:
                return found
    return _number(block.get("cost"))


def _rows(block: dict[str, Any]) -> int | None:
    found = _number(block.get("rows_examined_per_scan", block.get("rows")))
    return None if found is None else int(found)


def _text(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)[:MAX_DETAIL_CHARS]
    return str(value)[:MAX_DETAIL_CHARS]


def _label(kind: str, block: dict[str, Any]) -> str:
    table = block.get("table_name")
    access = block.get("access_type")
    key = block.get("key")
    label = kind
    if isinstance(table, str):
        label = f"{access or kind} on {table}" if access else f"{kind} {table}"
    if isinstance(key, str):
        label += f" using {key}"
    return label


def _children(block: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    found: list[tuple[str, dict[str, Any]]] = []
    for key, value in block.items():
        if key == "cost_info":
            continue
        if isinstance(value, dict):
            found.append((key, value))
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    # A step of a nested loop is `{"table": {...}}`: one key
                    # naming the operation it holds.
                    if len(item) == 1 and isinstance(next(iter(item.values())), dict):
                        found.append(next(iter(item.items())))
                    else:
                        found.append((key, item))
    return found


def _node_of(kind: str, block: dict[str, Any], path: str, counted: _Counter) -> ExplainNode:
    counted.kept += 1
    children: list[ExplainNode] = []
    for index, (child_kind, child) in enumerate(_children(block)):
        if counted.kept >= MAX_NODES:
            counted.cut = True
            break
        children.append(_node_of(child_kind, child, f"{path}.{index}", counted))
    table = block.get("table_name")
    return ExplainNode(
        id=path,
        kind=kind,
        label=_label(kind, block),
        relation=table if isinstance(table, str) else None,
        total_cost=_cost(block),
        rows=_rows(block),
        details={
            key: _text(value)
            for key, value in block.items()
            if key not in _NAMED
            and not isinstance(value, dict)
            and not (isinstance(value, list) and value and isinstance(value[0], dict))
            and value not in (None, [], False)
        },
        children=children,
    )


def _printed(description: Any, rows: list[tuple[Any, ...]]) -> str:
    """The tabular EXPLAIN as a person reads it in a terminal."""
    header = [str(column[0]) for column in description or []]
    lines = ["\t".join(header)]
    lines += ["\t".join("NULL" if value is None else str(value) for value in row) for row in rows]
    return "\n".join(lines)


class MysqlExplain:
    def __init__(self, session: MysqlSession) -> None:
        self._session = session

    async def explain(self, request: ExplainRequest) -> ExplainResult:
        statements = prepare(request.text).statements
        if len(statements) != 1:
            raise ValueError(say("Explain takes one statement"))
        statement = statements[0]
        if statement.kind == "explain":
            raise ValueError(say("This is already an Explain"))
        if statement.kind != "read":
            raise ValueError(say("A {kind} statement is not planned here", kind=statement.kind))
        values: tuple[str | None, ...] | None = None
        text = statement.text
        if statement.parameters:
            given = {parameter.name: parameter.value for parameter in request.parameters}
            values = tuple(given.get(name) for name in bound_names(text))
            text = bind(text)
        try:
            async with self._session.acquire() as connection:
                changed = await use_database(self._session, connection, request.search_path)
                try:
                    await connection.query("START TRANSACTION READ ONLY")
                    async with connection.cursor() as cursor:
                        await asyncio.wait_for(
                            cursor.execute(f"EXPLAIN FORMAT=JSON {text}", values),
                            request.timeout_seconds,
                        )
                        row = await cursor.fetchone()
                        await cursor.execute(f"EXPLAIN {text}", values)
                        printed = _printed(cursor.description, list(await cursor.fetchall()))
                    await connection.rollback()
                finally:
                    await restore_database(self._session, connection, changed)
        except pymysql.err.MySQLError as exc:
            if exc.args and isinstance(exc.args[0], int) and exc.args[0] >= 2000:
                error_kind, message = classify(exc, fallback_message=N_("The plan could not be read"))
                raise AdapterError(error_kind, message) from None
            raise ValueError(diagnostic_of(exc, cancelled=False).message) from None
        except AdapterError:
            raise
        except TimeoutError:
            raise ValueError(say("The statement ran out of time")) from None
        except Exception as exc:
            error_kind, message = classify(exc, fallback_message=N_("The plan could not be read"))
            raise AdapterError(error_kind, message) from None
        answered = json.loads(row[0]) if row is not None else None
        block = answered.get("query_block") if isinstance(answered, dict) else None
        if not isinstance(block, dict):
            raise ValueError(say("The source answered with no plan"))
        counted = _Counter()
        plan = _node_of("query_block", block, "0", counted)
        return ExplainResult(
            plan=plan,
            raw=printed,
            total_cost=plan.total_cost,
            rows=plan.rows,
            truncated=counted.cut,
        )


