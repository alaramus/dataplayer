"""What `system.tables` and `system.columns` say about a relation, read once.

The relation model, the summary and a page of rows ask about the same table,
and each reading it its own way would be three answers to one question.
Several relations of one database are three statements however many are
asked for (D246): the names travel as one `Array(String)` parameter.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.adapters.clickhouse.sql import array_of_strings
from app.adapters.clickhouse.types import (
    build_column_type,
    is_nullable,
    split_arguments,
)
from app.adapters.relation import ColumnType

_RELATIONS = """
SELECT name, engine, engine_full, total_rows, total_bytes, comment, sorting_key,
       primary_key, partition_key, create_table_query, dependencies_database,
       dependencies_table
FROM system.tables
WHERE database = {database:String} AND name IN {names:Array(String)} AND NOT is_temporary
"""

_COLUMNS = """
SELECT table, name, position, type, default_kind, default_expression, comment,
       compression_codec, is_in_sorting_key, is_in_partition_key, is_in_primary_key
FROM system.columns
WHERE database = {database:String} AND table IN {names:Array(String)}
ORDER BY table, position
"""

_SKIPPING_INDEXES = """
SELECT table, name, type, type_full, expr, granularity
FROM system.data_skipping_indices
WHERE database = {database:String} AND table IN {names:Array(String)}
ORDER BY table, name
"""

VIEW_ENGINES = frozenset({"View", "MaterializedView", "LiveView", "WindowView"})

# Engines whose rows are a finite set the server can sort: a page of them is
# ordered by every column (D269). Anything else — a URL, a file, a stream, a
# generator, the server's own tables, of which `system.numbers` never ends —
# is read in the order its engine gives.
_FINITE_ENGINES = frozenset(
    {
        "Log",
        "TinyLog",
        "StripeLog",
        "Memory",
        "Join",
        "Dictionary",
        "Distributed",
        "Merge",
        "Buffer",
        "View",
        "MaterializedView",
        "EmbeddedRocksDB",
        "KeeperMap",
    }
)


def has_finite_rows(engine: str) -> bool:
    return engine.endswith("MergeTree") or engine in _FINITE_ENGINES


@dataclass(frozen=True)
class ColumnFacts:
    position: int
    name: str
    type: ColumnType
    nullable: bool
    # DEFAULT and EPHEMERAL: what an insert without the column writes.
    default: str | None
    # MATERIALIZED and ALIAS: computed, never written.
    generated: str | None
    comment: str | None
    codec: str | None
    # In the sorting, primary or partition key: where a row is stored, which
    # an UPDATE cannot move it from.
    in_key: bool = False


@dataclass(frozen=True)
class CheckFacts:
    name: str
    expression: str
    # ASSUME: a promise the optimizer relies on and nothing checks.
    enforced: bool


@dataclass(frozen=True)
class SkippingIndexFacts:
    name: str
    type: str
    expression: str
    granularity: int
    # With its arguments, `bloom_filter(0.01)`, as a copy writes it.
    type_full: str = ""


@dataclass(frozen=True)
class RelationFacts:
    schema: str
    name: str
    engine: str
    row_estimate: int | None
    size_bytes: int | None
    comment: str | None
    sorting_key: list[str]
    primary_key: list[str]
    partition_key: str | None
    columns: list[ColumnFacts]
    checks: list[CheckFacts] = field(default_factory=list)
    indexes: list[SkippingIndexFacts] = field(default_factory=list)
    # The engine with its keys and settings, as CREATE TABLE writes it.
    engine_full: str = ""
    # Materialized views fed by this table, as `database.name`.
    dependents: list[str] = field(default_factory=list)

    @property
    def is_view(self) -> bool:
        return self.engine in VIEW_ENGINES

    @property
    def is_materialized(self) -> bool:
        return self.engine == "MaterializedView"

    def key_columns(self, key: list[str]) -> list[str]:
        """The parts of a key that are plain columns, in key order."""
        names = {column.name for column in self.columns}
        found: list[str] = []
        for part in key:
            name = _unquoted_identifier(part)
            if name in names and name not in found:
                found.append(name)
        return found


def _unquoted_identifier(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "`\"":
        body = text[1:-1]
        out: list[str] = []
        index = 0
        while index < len(body):
            if body[index] == "\\" and index + 1 < len(body):
                out.append(body[index + 1])
                index += 2
                continue
            out.append(body[index])
            index += 1
        return "".join(out)
    return text


def key_parts(text: str) -> list[str]:
    """`id, toDate(d)` as its two parts; a tuple `(a, b)` as its members."""
    text = text.strip()
    if text == "" or text == "tuple()":
        return []
    parts = split_arguments(f"key({text})")
    if len(parts) == 1 and parts[0].startswith("(") and parts[0].endswith(")"):
        parts = split_arguments(f"key{parts[0]}")
    return parts


def _column_list(create: str) -> list[str]:
    """The items between a CREATE TABLE's first parentheses, as written."""
    depth = 0
    quoted: str | None = None
    start = -1
    index = 0
    while index < len(create):
        character = create[index]
        if quoted is not None:
            if character == "\\":
                index += 2
                continue
            if character == quoted:
                quoted = None
        elif character in "'`\"":
            quoted = character
        elif character == "(":
            if depth == 0:
                start = index
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0 and start >= 0:
                return split_arguments("t" + create[start : index + 1])
        index += 1
    return []


def read_checks(create: str) -> list[CheckFacts]:
    """`CONSTRAINT name CHECK expr` and `… ASSUME expr` from the table's own text.

    The server keeps them nowhere else: there is no system table of
    constraints.
    """
    checks: list[CheckFacts] = []
    for item in _column_list(create):
        if not item.upper().startswith("CONSTRAINT "):
            continue
        rest = item[len("CONSTRAINT ") :].lstrip()
        if rest[:1] in "`\"":
            close = rest.find(rest[0], 1)
            while close > 0 and rest[close - 1] == "\\":
                close = rest.find(rest[0], close + 1)
            raw_name, rest = rest[: close + 1], rest[close + 1 :].lstrip()
        else:
            raw_name, _, rest = rest.partition(" ")
        word, _, expression = rest.partition(" ")
        if word.upper() not in ("CHECK", "ASSUME"):
            continue
        checks.append(
            CheckFacts(
                name=_unquoted_identifier(raw_name),
                expression=expression.strip(),
                enforced=word.upper() == "CHECK",
            )
        )
    return checks


class Reader(Protocol):
    async def query(
        self,
        sql: str,
        params: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]: ...


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def _count(value: Any) -> int | None:
    return None if value is None else int(value)


async def relation_rows(
    reader: Reader, schema: str, names: Sequence[str]
) -> dict[str, dict[str, Any]]:
    """system.tables's row of every relation of these that exists, by name."""
    rows = await reader.query(
        _RELATIONS, {"database": schema, "names": array_of_strings(list(names))}
    )
    return {str(row["name"]): row for row in rows}


async def read_relations(
    reader: Reader,
    schema: str,
    names: Sequence[str],
    *,
    structure: bool = True,
) -> dict[str, RelationFacts]:
    """The relations of one database that exist, by name.

    `structure` reads the skipping indexes as well, which a page of rows does
    not need.
    """
    wanted = list(dict.fromkeys(names))
    relations = await relation_rows(reader, schema, wanted)
    if not relations:
        return {}
    found = array_of_strings(list(relations))
    columns: dict[str, list[dict[str, Any]]] = {}
    for row in await reader.query(_COLUMNS, {"database": schema, "names": found}):
        columns.setdefault(str(row["table"]), []).append(row)
    indexes: dict[str, list[dict[str, Any]]] = {}
    if structure:
        for row in await reader.query(_SKIPPING_INDEXES, {"database": schema, "names": found}):
            indexes.setdefault(str(row["table"]), []).append(row)
    return {
        name: _facts(schema, name, row, columns.get(name, []), indexes.get(name, []), structure)
        for name, row in relations.items()
    }


async def read_relation(
    reader: Reader, schema: str, name: str, *, structure: bool = True
) -> RelationFacts | None:
    return (await read_relations(reader, schema, [name], structure=structure)).get(name)


def _column(row: dict[str, Any]) -> ColumnFacts:
    kind = str(row["default_kind"])
    expression = _text(row["default_expression"])
    return ColumnFacts(
        position=int(row["position"]),
        name=str(row["name"]),
        type=build_column_type(str(row["type"])),
        nullable=is_nullable(str(row["type"])),
        default=expression if kind in ("DEFAULT", "EPHEMERAL") else None,
        generated=expression if kind in ("MATERIALIZED", "ALIAS") else None,
        comment=_text(row["comment"]),
        codec=_text(row["compression_codec"]),
        in_key=any(
            int(row[flag]) == 1
            for flag in ("is_in_sorting_key", "is_in_partition_key", "is_in_primary_key")
        ),
    )


def _facts(
    schema: str,
    name: str,
    relation: dict[str, Any],
    column_rows: list[dict[str, Any]],
    index_rows: list[dict[str, Any]],
    structure: bool,
) -> RelationFacts:
    engine = str(relation["engine"])
    view = engine in VIEW_ENGINES
    return RelationFacts(
        schema=schema,
        name=name,
        engine=engine,
        # Exact for a MergeTree table and nothing for most other engines;
        # called an estimate all the same, since nothing here counts (D229).
        row_estimate=None if view else _count(relation["total_rows"]),
        size_bytes=None if view else _count(relation["total_bytes"]),
        comment=_text(relation["comment"]),
        sorting_key=key_parts(str(relation["sorting_key"] or "")),
        primary_key=key_parts(str(relation["primary_key"] or "")),
        partition_key=_text(relation["partition_key"]),
        columns=[_column(row) for row in column_rows],
        checks=read_checks(str(relation["create_table_query"] or "")) if structure else [],
        engine_full=str(relation["engine_full"] or ""),
        dependents=[
            f"{database}.{table}"
            for database, table in zip(
                relation["dependencies_database"], relation["dependencies_table"], strict=False
            )
        ],
        indexes=[
            SkippingIndexFacts(
                name=str(row["name"]),
                type=str(row["type"]),
                type_full=str(row["type_full"]),
                expression=str(row["expr"]),
                granularity=int(row["granularity"]),
            )
            for row in index_rows
        ],
    )
