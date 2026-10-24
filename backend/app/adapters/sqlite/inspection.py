"""What the pragmas and a table's own text say about a relation, read once (D249).

The relation model, the summary and a page of rows ask about the same table,
and each reading it its own way would be three answers to one question. Every
function here runs inside the session's worker thread, on one connection.
"""

import sqlite3
from dataclasses import dataclass, field
from typing import Any, Literal

from app.adapters.protocol import AdapterError
from app.adapters.relation import ColumnType, RefAction
from app.adapters.sqlite.definition import TableText, index_predicate, read_table
from app.adapters.sqlite.session import Reading
from app.adapters.sqlite.sql import quoted_name
from app.adapters.sqlite.types import build_column_type
from app.core.translation import say

SCHEMA = "main"

RelationType = Literal["table", "view", "virtual", "shadow"]

_RELATIONS = """
SELECT name, type, wr, strict
FROM pragma_table_list
WHERE schema = 'main' AND type IN ('table', 'view', 'virtual', 'shadow')
"""

_RELATION = _RELATIONS + " AND name = ?"

_TEXT = "SELECT sql FROM sqlite_schema WHERE type IN ('table', 'view') AND name = ?"
_SPELLING = (
    "SELECT name FROM sqlite_schema WHERE type IN ('table', 'view') AND name = ? COLLATE NOCASE"
)

_COLUMNS = """
SELECT cid, name, type, "notnull" AS not_null, dflt_value, pk, hidden
FROM pragma_table_xinfo(?, 'main')
ORDER BY cid
"""

_FOREIGN_KEYS = """
SELECT id, seq, "table" AS target, "from" AS source, "to" AS target_column,
       on_update, on_delete
FROM pragma_foreign_key_list(?, 'main')
ORDER BY id, seq
"""

_INDEXES = """
SELECT name, "unique" AS is_unique, origin, partial
FROM pragma_index_list(?, 'main')
"""

_INDEX_PARTS = """
SELECT seqno, cid, name, "desc" AS descending, coll
FROM pragma_index_xinfo(?, 'main')
WHERE key = 1
ORDER BY seqno
"""

_INDEX_TEXT = "SELECT sql FROM sqlite_schema WHERE type = 'index' AND name = ?"

_HAS_STATISTICS = "SELECT 1 FROM sqlite_schema WHERE type = 'table' AND name = 'sqlite_stat1'"
_STATISTICS = "SELECT tbl, stat FROM sqlite_stat1"

_REF_ACTIONS: dict[str, RefAction] = {
    "NO ACTION": "no_action",
    "RESTRICT": "restrict",
    "CASCADE": "cascade",
    "SET NULL": "set_null",
    "SET DEFAULT": "set_default",
}

# A column a virtual table keeps for its module, such as FTS5's own name and
# rank: `hidden` 1. Generated columns are 2 (virtual) and 3 (stored).
_MODULE_COLUMN = 1
_GENERATED = (2, 3)
_ROWID_NAMES = ("rowid", "oid", "_rowid_")


@dataclass(frozen=True)
class ColumnFacts:
    position: int
    name: str
    type: ColumnType
    nullable: bool
    default: str | None
    # Where it stands in the primary key, from 1; 0 when it is not in it.
    key_position: int
    # INTEGER PRIMARY KEY of a rowid table: the rowid under another name,
    # given a value when none is written.
    rowid_alias: bool
    generated: str | None
    stored: bool
    collation: str | None


@dataclass(frozen=True)
class KeyFacts:
    name: str
    kind: Literal["PRIMARY KEY", "UNIQUE", "FOREIGN KEY"]
    columns: list[str]
    target_table: str | None = None
    target_columns: list[str] = field(default_factory=list)
    on_update: RefAction = "no_action"
    on_delete: RefAction = "no_action"


@dataclass(frozen=True)
class CheckFacts:
    name: str
    expression: str


@dataclass(frozen=True)
class IndexFacts:
    name: str
    unique: bool
    # c: made by CREATE INDEX; u: a UNIQUE constraint's; pk: the primary key's.
    origin: str
    predicate: str | None
    columns: list[str]
    definition: str


@dataclass(frozen=True)
class RelationFacts:
    name: str
    type: RelationType
    without_rowid: bool
    strict: bool
    text: str | None
    row_estimate: int | None
    columns: list[ColumnFacts]
    keys: list[KeyFacts]
    checks: list[CheckFacts] = field(default_factory=list)
    indexes: list[IndexFacts] = field(default_factory=list)

    schema = SCHEMA

    @property
    def is_view(self) -> bool:
        return self.type == "view"

    @property
    def primary_key(self) -> list[str]:
        return next((key.columns for key in self.keys if key.kind == "PRIMARY KEY"), [])

    @property
    def foreign_keys(self) -> list[KeyFacts]:
        return [key for key in self.keys if key.kind == "FOREIGN KEY" and key.target_columns]

    @property
    def rowid(self) -> str | None:
        """The name the row's own id answers to here, or nothing (D251).

        Each of the three names is the id only while no column takes it.
        """
        if self.type == "view" or self.without_rowid:
            return None
        taken = {column.name.lower() for column in self.columns}
        return next((name for name in _ROWID_NAMES if name not in taken), None)


def is_system_relation(name: str, relation_type: str) -> bool:
    """The library's own tables, and the ones a virtual table keeps (D248)."""
    return relation_type == "shadow" or name.lower().startswith("sqlite_")


def _key_name(kind: str, columns: list[str], given: str | None) -> str:
    if given is not None:
        return given
    if kind == "PRIMARY KEY":
        return "PRIMARY KEY"
    listed = ", ".join(quoted_name(column) for column in columns)
    return f"{kind} ({listed})"


def _same(left: list[str], right: list[str]) -> bool:
    return [name.lower() for name in left] == [name.lower() for name in right]


def _keys(
    reading: Reading,
    name: str,
    text: TableText,
    columns: list[ColumnFacts],
    indexes: list[dict[str, Any]],
) -> list[KeyFacts]:
    keys: list[KeyFacts] = []
    primary = [column.name for column in sorted(columns, key=lambda c: c.key_position) if column.key_position]
    if primary:
        given = text.primary_key.name if text.primary_key else None
        keys.append(KeyFacts(_key_name("PRIMARY KEY", primary, given), "PRIMARY KEY", primary))
    for index in indexes:
        if index["origin"] != "u":
            continue
        parts = [str(part["name"]) for part in reading.rows(_INDEX_PARTS, (index["name"],))]
        given = next((key.name for key in text.unique if _same(key.columns, parts)), None)
        keys.append(KeyFacts(_key_name("UNIQUE", parts, given), "UNIQUE", parts))
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in reading.rows(_FOREIGN_KEYS, (name,)):
        grouped.setdefault(int(row["id"]), []).append(row)
    # pragma_foreign_key_list numbers keys from the last one written.
    for members in reversed(list(grouped.values())):
        first = members[0]
        # A key names its target as it was written; SQLite finds the table
        # without case, and a node id needs its own spelling.
        written = str(first["target"])
        target = str(reading.value(_SPELLING, (written,)) or written)
        sources = [str(member["source"]) for member in members]
        targets = [member["target_column"] for member in members]
        if any(column is None for column in targets):
            # A key naming no columns points at the target's primary key.
            targets = [
                str(row["name"])
                for row in sorted(
                    (row for row in reading.rows(_COLUMNS, (target,)) if int(row["pk"])),
                    key=lambda row: int(row["pk"]),
                )
            ]
        given = next(
            (
                key.name
                for key in text.foreign
                if _same(key.columns, sources) and (key.target or "").lower() == target.lower()
            ),
            None,
        )
        keys.append(
            KeyFacts(
                name=_key_name("FOREIGN KEY", sources, given),
                kind="FOREIGN KEY",
                columns=sources,
                target_table=target,
                target_columns=[str(column) for column in targets]
                if len(targets) == len(sources)
                else [],
                on_update=_REF_ACTIONS.get(str(first["on_update"]).upper(), "no_action"),
                on_delete=_REF_ACTIONS.get(str(first["on_delete"]).upper(), "no_action"),
            )
        )
    return keys


def _indexes(reading: Reading, rows: list[dict[str, Any]]) -> list[IndexFacts]:
    found: list[IndexFacts] = []
    for row in rows:
        index_name = str(row["name"])
        parts = reading.rows(_INDEX_PARTS, (index_name,))
        columns = [str(part["name"]) for part in parts if part["name"] is not None]
        origin = str(row["origin"])
        written = reading.value(_INDEX_TEXT, (index_name,))
        if written is None:
            # The index SQLite made for a key keeps no text of its own.
            listed = ", ".join(
                quoted_name(str(part["name"])) + (" DESC" if part["descending"] else "")
                for part in parts
            )
            kind = "PRIMARY KEY" if origin == "pk" else "UNIQUE"
            definition = f"{kind} ({listed})"
        else:
            definition = str(written)
        found.append(
            IndexFacts(
                name=index_name,
                unique=bool(row["is_unique"]),
                origin=origin,
                predicate=index_predicate(definition) if row["partial"] else None,
                columns=columns,
                definition=definition,
            )
        )
    return sorted(found, key=lambda index: index.name)


def estimates(reading: Reading) -> dict[str, int]:
    """What ANALYZE counted, by table; empty when it never ran (D248).

    Nothing counts the rows themselves: a count is a full scan. A row per
    index, each leading with the rows the index holds; a partial index holds
    fewer, so the largest is the table's.
    """
    if reading.value(_HAS_STATISTICS) is None:
        return {}
    found: dict[str, int] = {}
    for row in reading.rows(_STATISTICS):
        head = str(row["stat"]).split(" ", 1)[0]
        if head.isdigit():
            table = str(row["tbl"])
            found[table] = max(found.get(table, 0), int(head))
    return found


def list_relations(reading: Reading) -> list[dict[str, Any]]:
    """Every relation of `main`, ordered by name as SQLite compares them."""
    return sorted(reading.rows(_RELATIONS), key=lambda row: (str(row["name"]).lower(), str(row["name"])))


def find_relation(reading: Reading, name: str) -> dict[str, Any] | None:
    rows = reading.rows(_RELATION, (name,))
    return rows[0] if rows else None


def read_relation(reading: Reading, name: str, *, structure: bool = True) -> RelationFacts | None:
    """One relation, or nothing when there is none by that name.

    `structure` reads checks and indexes as well, which a page of rows does
    not need.
    """
    relation = find_relation(reading, name)
    if relation is None:
        return None
    statement = reading.value(_TEXT, (name,))
    written = str(statement) if statement is not None else None
    relation_type: RelationType = relation["type"]
    text = read_table(written) if relation_type == "table" else TableText()
    try:
        column_rows = reading.rows(_COLUMNS, (name,))
    except sqlite3.OperationalError as exc:
        # The one failure told apart by its text, which is not passed on: a
        # virtual table is read through a module the library may lack.
        if relation_type == "virtual" and "no such module" in str(exc):
            raise AdapterError(
                "config",
                say('"{name}" needs a module this server does not have', name=name),
            ) from None
        raise
    declared_key = [row for row in column_rows if int(row["pk"])]
    alias = (
        not relation["wr"]
        and relation_type == "table"
        and len(declared_key) == 1
        and str(declared_key[0]["type"] or "").upper() == "INTEGER"
    )
    columns: list[ColumnFacts] = []
    for row in column_rows:
        hidden = int(row["hidden"])
        if hidden == _MODULE_COLUMN:
            continue
        column_name = str(row["name"])
        said = text.columns.get(column_name.lower())
        default = row["dflt_value"]
        columns.append(
            ColumnFacts(
                position=int(row["cid"]) + 1,
                name=column_name,
                type=build_column_type(str(row["type"] or "")),
                # A primary key of a rowid table takes NULL unless it is the
                # rowid itself; the pragma says only what was declared.
                nullable=not int(row["not_null"]) and not (alias and int(row["pk"])),
                default=None if default is None else str(default),
                key_position=int(row["pk"]),
                rowid_alias=alias and bool(int(row["pk"])),
                generated=said.generated if said is not None and hidden in _GENERATED else None,
                stored=hidden == 3,
                collation=said.collation if said is not None else None,
            )
        )
    index_rows = reading.rows(_INDEXES, (name,)) if relation_type == "table" else []
    keys = _keys(reading, name, text, columns, index_rows) if relation_type == "table" else []
    checks = [
        CheckFacts(name=check.name or f"CHECK {position}", expression=check.expression or "")
        for position, check in enumerate(text.checks, start=1)
    ]
    return RelationFacts(
        name=name,
        type=relation_type,
        without_rowid=bool(relation["wr"]),
        strict=bool(relation["strict"]),
        text=written,
        row_estimate=estimates(reading).get(name) if relation_type != "view" else None,
        columns=columns,
        keys=keys,
        checks=checks if structure else [],
        indexes=_indexes(reading, index_rows) if structure else [],
    )
