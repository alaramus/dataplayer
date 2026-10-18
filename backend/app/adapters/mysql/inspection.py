"""What `information_schema` says about one relation, read once for all callers.

The relation model, the summary and a page of rows ask about the same table,
and each reading it its own way would be three answers to one question. Every
column is aliased in lower case: MySQL 8 names the columns of its catalog in
capitals and MariaDB does not, so an unaliased `*` reads differently by server.
"""

from dataclasses import dataclass, field
from typing import Any

from app.adapters.mysql.session import MysqlSession, ServerProfile, quoted_name
from app.adapters.mysql.types import build_column_type
from app.adapters.relation import ColumnType, RefAction

_RELATION = """
SELECT TABLE_TYPE AS table_type,
       ENGINE AS engine,
       TABLE_ROWS AS table_rows,
       DATA_LENGTH + INDEX_LENGTH AS size_bytes,
       TABLE_COMMENT AS comment,
       TABLE_COLLATION AS collation
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
"""

_COLUMNS = """
SELECT COLUMN_NAME AS name,
       ORDINAL_POSITION AS position,
       DATA_TYPE AS data_type,
       COLUMN_TYPE AS column_type,
       IS_NULLABLE AS is_nullable,
       COLUMN_DEFAULT AS column_default,
       EXTRA AS extra,
       GENERATION_EXPRESSION AS generation_expression,
       COLUMN_COMMENT AS comment,
       COLLATION_NAME AS collation,
       CHARACTER_MAXIMUM_LENGTH AS character_length,
       NUMERIC_PRECISION AS numeric_precision,
       NUMERIC_SCALE AS numeric_scale
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
ORDER BY ORDINAL_POSITION
"""

# Keys and their columns in key order. A foreign key's target schema is read
# rather than assumed to be the table's own: MySQL lets a key point into any
# database on the server.
_KEYS = """
SELECT tc.CONSTRAINT_NAME AS name,
       tc.CONSTRAINT_TYPE AS constraint_type,
       k.COLUMN_NAME AS column_name,
       k.REFERENCED_TABLE_SCHEMA AS target_schema,
       k.REFERENCED_TABLE_NAME AS target_table,
       k.REFERENCED_COLUMN_NAME AS target_column,
       rc.UPDATE_RULE AS update_rule,
       rc.DELETE_RULE AS delete_rule
FROM information_schema.TABLE_CONSTRAINTS AS tc
JOIN information_schema.KEY_COLUMN_USAGE AS k
  ON k.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA
 AND k.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
 AND k.TABLE_SCHEMA = tc.TABLE_SCHEMA
 AND k.TABLE_NAME = tc.TABLE_NAME
LEFT JOIN information_schema.REFERENTIAL_CONSTRAINTS AS rc
  ON rc.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA
 AND rc.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
 AND rc.TABLE_NAME = tc.TABLE_NAME
WHERE tc.TABLE_SCHEMA = %s AND tc.TABLE_NAME = %s
  AND tc.CONSTRAINT_TYPE IN ('PRIMARY KEY', 'UNIQUE', 'FOREIGN KEY')
ORDER BY tc.CONSTRAINT_NAME, k.ORDINAL_POSITION
"""

# The two servers keep checks differently: MySQL names a check's table only in
# TABLE_CONSTRAINTS and says there whether it is enforced; MariaDB names the
# table in CHECK_CONSTRAINTS itself, and says whether the check is a column's.
_MYSQL_CHECKS = """
SELECT cc.CONSTRAINT_NAME AS name,
       cc.CHECK_CLAUSE AS expression,
       tc.ENFORCED AS enforced,
       'Table' AS level
FROM information_schema.TABLE_CONSTRAINTS AS tc
JOIN information_schema.CHECK_CONSTRAINTS AS cc
  ON cc.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA
 AND cc.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
WHERE tc.TABLE_SCHEMA = %s AND tc.TABLE_NAME = %s AND tc.CONSTRAINT_TYPE = 'CHECK'
ORDER BY cc.CONSTRAINT_NAME
"""

_MARIADB_CHECKS = """
SELECT CONSTRAINT_NAME AS name,
       CHECK_CLAUSE AS expression,
       'YES' AS enforced,
       LEVEL AS level
FROM information_schema.CHECK_CONSTRAINTS
WHERE CONSTRAINT_SCHEMA = %s AND TABLE_NAME = %s
ORDER BY CONSTRAINT_NAME
"""

_MYSQL_INDEXES = """
SELECT INDEX_NAME AS name,
       NON_UNIQUE AS non_unique,
       COLUMN_NAME AS column_name,
       EXPRESSION AS expression,
       SUB_PART AS sub_part,
       COLLATION AS collation,
       INDEX_TYPE AS index_type
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
ORDER BY INDEX_NAME, SEQ_IN_INDEX
"""

# MariaDB has no functional index, and so no EXPRESSION column to read.
_MARIADB_INDEXES = """
SELECT INDEX_NAME AS name,
       NON_UNIQUE AS non_unique,
       COLUMN_NAME AS column_name,
       NULL AS expression,
       SUB_PART AS sub_part,
       COLLATION AS collation,
       INDEX_TYPE AS index_type
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
ORDER BY INDEX_NAME, SEQ_IN_INDEX
"""

_REF_ACTIONS: dict[str, RefAction] = {
    "NO ACTION": "no_action",
    "RESTRICT": "restrict",
    "CASCADE": "cascade",
    "SET NULL": "set_null",
    "SET DEFAULT": "set_default",
}

# What `TABLE_TYPE` says, as far as rows go. A system-versioned or a sequence
# table of MariaDB is a table to read.
_TABLE_TYPES = ("BASE TABLE", "SYSTEM VERSIONED", "SEQUENCE")
VIEW_TYPES = ("VIEW", "SYSTEM VIEW")
RELATION_TYPES = (*_TABLE_TYPES, *VIEW_TYPES)


@dataclass(frozen=True)
class ColumnFacts:
    position: int
    name: str
    type: ColumnType
    nullable: bool
    default: str | None
    auto_increment: bool
    generated: str | None
    comment: str | None
    collation: str | None


@dataclass(frozen=True)
class KeyFacts:
    name: str
    kind: str
    columns: list[str]
    target_schema: str | None = None
    target_table: str | None = None
    target_columns: list[str] = field(default_factory=list)
    on_update: RefAction = "no_action"
    on_delete: RefAction = "no_action"


@dataclass(frozen=True)
class CheckFacts:
    name: str
    expression: str
    enforced: bool


@dataclass(frozen=True)
class IndexFacts:
    name: str
    unique: bool
    method: str
    # A column name, or `(expression)` for a functional part, with its prefix
    # length and direction as MySQL writes them.
    parts: list[str]
    columns: list[str]


@dataclass(frozen=True)
class RelationFacts:
    schema: str
    name: str
    table_type: str
    engine: str | None
    row_estimate: int | None
    size_bytes: int | None
    comment: str | None
    columns: list[ColumnFacts]
    keys: list[KeyFacts]
    checks: list[CheckFacts] = field(default_factory=list)
    indexes: list[IndexFacts] = field(default_factory=list)

    @property
    def is_view(self) -> bool:
        return self.table_type in VIEW_TYPES

    @property
    def foreign_keys(self) -> list[KeyFacts]:
        """Keys pointing elsewhere whose two ends pair up column for column."""
        return [
            key
            for key in self.keys
            if key.kind == "FOREIGN KEY"
            and key.target_table is not None
            and key.columns
            and len(key.columns) == len(key.target_columns)
        ]

    @property
    def primary_key(self) -> list[str]:
        return next((key.columns for key in self.keys if key.kind == "PRIMARY KEY"), [])

    @property
    def ordering_key(self) -> list[str]:
        """What a page is ordered by once the reader's own sort is done (D231).

        The primary key, or else a unique key over columns that cannot be
        null — the key InnoDB itself keeps the rows in when there is no primary
        one. Several such keys are taken by name, so the choice is the same
        every time it is made.
        """
        if self.primary_key:
            return self.primary_key
        not_null = {column.name for column in self.columns if not column.nullable}
        for key in sorted(self.keys, key=lambda key: key.name):
            if key.kind == "UNIQUE" and set(key.columns) <= not_null:
                return key.columns
        return []


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = value.decode() if isinstance(value, bytes) else str(value)
    return text or None


def _default(row: dict[str, Any], type_: ColumnType, profile: ServerProfile) -> str | None:
    """The default as an expression, the way PostgreSQL's reads.

    MariaDB writes an expression already, and the word NULL for a column that
    has none. MySQL writes a literal bare and marks an expression in EXTRA.
    """
    value = _text(row["column_default"])
    if value is None:
        return None
    if profile.mariadb:
        return None if value == "NULL" else value
    if "DEFAULT_GENERATED" in str(row["extra"]).upper() or type_.category == "number":
        return value
    return "'" + value.replace("'", "''") + "'"


def _generated(row: dict[str, Any]) -> str | None:
    extra = str(row["extra"]).upper()
    if "VIRTUAL GENERATED" in extra or "STORED GENERATED" in extra:
        return _text(row["generation_expression"])
    return None


def _json_columns(checks: list[dict[str, Any]], columns: list[dict[str, Any]]) -> set[str]:
    """MariaDB's JSON columns: LONGTEXT with a check of their own that it is JSON."""
    longtext = {str(row["name"]) for row in columns if str(row["data_type"]) == "longtext"}
    return {
        str(check["name"])
        for check in checks
        if str(check["level"]) == "Column"
        and str(check["name"]) in longtext
        and str(check["expression"]) == f"json_valid(`{check['name']}`)"
    }


async def relation_exists(session: MysqlSession, schema: str, name: str) -> dict[str, Any] | None:
    rows = await session.query(_RELATION, (schema, name))
    if not rows or str(rows[0]["table_type"]) not in RELATION_TYPES:
        return None
    return rows[0]


async def read_relation(
    session: MysqlSession, schema: str, name: str, *, structure: bool = True
) -> RelationFacts | None:
    """One relation, or nothing when there is none by that name.

    `structure` reads checks and indexes as well, which a page of rows does
    not need.
    """
    relation = await relation_exists(session, schema, name)
    if relation is None:
        return None
    profile = await session.profile()
    column_rows = await session.query(_COLUMNS, (schema, name))
    check_rows = await session.query(
        _MARIADB_CHECKS if profile.mariadb else _MYSQL_CHECKS, (schema, name)
    )
    json_columns = _json_columns(check_rows, column_rows) if profile.mariadb else set()
    table_collation = _text(relation["collation"])

    columns: list[ColumnFacts] = []
    for row in column_rows:
        column_name = str(row["name"])
        type_ = build_column_type(row, is_json=column_name in json_columns)
        collation = _text(row["collation"])
        columns.append(
            ColumnFacts(
                position=int(row["position"]),
                name=column_name,
                type=type_,
                nullable=str(row["is_nullable"]) == "YES",
                default=_default(row, type_, profile),
                auto_increment="AUTO_INCREMENT" in str(row["extra"]).upper(),
                generated=_generated(row),
                comment=_text(row["comment"]),
                # Only where it differs from the table's: every text column
                # has one, and the same name on each of them says nothing.
                collation=None if collation == table_collation else collation,
            )
        )

    keys = _keys(await session.query(_KEYS, (schema, name)))
    checks = (
        [
            CheckFacts(
                name=str(row["name"]),
                expression=str(row["expression"]),
                enforced=str(row["enforced"]) == "YES",
            )
            for row in check_rows
            if str(row["name"]) not in json_columns or str(row["level"]) != "Column"
        ]
        if structure
        else []
    )
    indexes = (
        _indexes(
            await session.query(
                _MARIADB_INDEXES if profile.mariadb else _MYSQL_INDEXES, (schema, name)
            )
        )
        if structure
        else []
    )
    is_view = str(relation["table_type"]) in VIEW_TYPES
    rows_estimate = relation["table_rows"]
    size = relation["size_bytes"]
    return RelationFacts(
        schema=schema,
        name=name,
        table_type=str(relation["table_type"]),
        engine=_text(relation["engine"]),
        row_estimate=None if is_view or rows_estimate is None else int(rows_estimate),
        size_bytes=None if is_view or size is None else int(size),
        # MySQL writes the word VIEW as the comment of every view.
        comment=None if is_view else _text(relation["comment"]),
        columns=columns,
        keys=keys,
        checks=checks,
        indexes=indexes,
    )


def _keys(rows: list[dict[str, Any]]) -> list[KeyFacts]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault((str(row["name"]), str(row["constraint_type"])), []).append(row)
    keys: list[KeyFacts] = []
    for (key_name, kind), members in grouped.items():
        first = members[0]
        keys.append(
            KeyFacts(
                name=key_name,
                kind=kind,
                columns=[str(member["column_name"]) for member in members],
                target_schema=_text(first["target_schema"]),
                target_table=_text(first["target_table"]),
                target_columns=[
                    str(member["target_column"])
                    for member in members
                    if member["target_column"] is not None
                ],
                on_update=_REF_ACTIONS.get(str(first["update_rule"]), "no_action"),
                on_delete=_REF_ACTIONS.get(str(first["delete_rule"]), "no_action"),
            )
        )
    return keys


def _indexes(rows: list[dict[str, Any]]) -> list[IndexFacts]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["name"]), []).append(row)
    indexes: list[IndexFacts] = []
    for index_name, members in grouped.items():
        parts: list[str] = []
        columns: list[str] = []
        for member in members:
            column = _text(member["column_name"])
            if column is None:
                parts.append(f"({_text(member['expression']) or ''})")
            else:
                columns.append(column)
                quoted = quoted_name(column)
                if member["sub_part"] is not None:
                    quoted += f"({int(member['sub_part'])})"
                parts.append(quoted)
            if str(member["collation"]) == "D":
                parts[-1] += " DESC"
        indexes.append(
            IndexFacts(
                name=index_name,
                unique=int(members[0]["non_unique"]) == 0,
                method=str(members[0]["index_type"]).lower(),
                parts=parts,
                columns=columns,
            )
        )
    return indexes
