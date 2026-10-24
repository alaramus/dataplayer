"""Changing a SQLite table's structure by rebuilding it (D255).

SQLite's ALTER TABLE adds, renames and drops a column and renames a table, and
nothing else. Every other change — a type, a requirement, a default, a key — is
the procedure SQLite documents: make the new table, copy the rows, drop the
old one, give the new one its name, and make its indexes and triggers again,
inside one transaction with foreign keys switched off.

The new definition is the old `CREATE TABLE` text with one clause edited, by
the positions the reader of that text keeps (`definition.Clause.span`), rather
than a definition written again from the catalog: the catalog has no word for
AUTOINCREMENT, a conflict clause, DEFERRABLE or a comment, and a rebuild that
wrote them out would drop them without saying so.
"""

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass

from app.adapters.sqlite.definition import (
    Clause,
    ColumnText,
    Span,
    TableText,
    read_table,
)
from app.adapters.sqlite.sql import SQL, Composable, Identifier, quoted_name
from app.core.translation import say

Edit = tuple[Span, str]


def edited(text: str, edits: list[Edit]) -> str:
    """The text with each span replaced, the last first so offsets hold."""
    for (start, end), replacement in sorted(edits, key=lambda edit: edit[0], reverse=True):
        text = text[:start] + replacement + text[end:]
    return text


def _with_space(text: str, span: Span) -> Span:
    """A clause's span with the space before it, so removing it leaves none."""
    start, end = span
    while start > 0 and text[start - 1] in " \t":
        start -= 1
    return start, end


def without_items(table: TableText, positions: list[int]) -> Edit:
    """Remove several items at once, and the commas that joined them.

    One edit rather than one per item: two neighbours removed one at a time
    would each claim the comma between them. Between two items that stay
    goes what followed the first of them in the text, so the layout holds.
    """
    removed = set(positions)
    kept = [index for index in range(len(table.items)) if index not in removed]
    if not kept:
        raise ValueError(say("A table must keep at least one column"))
    pieces: list[str] = []
    for order, index in enumerate(kept):
        if order:
            before = kept[order - 1]
            pieces.append(table.text[table.items[before][1] : table.items[before + 1][0]])
        start, end = table.items[index]
        pieces.append(table.text[start:end])
    return (table.items[0][0], table.items[-1][1]), "".join(pieces)


def without_clause(table: TableText, clause: Clause) -> Edit:
    if clause.inline:
        return _with_space(table.text, clause.span), ""
    return without_items(table, [clause.item])


def after_type(column: ColumnText, addition: str) -> Edit:
    """Something written just after a column's type, or its name if it has none."""
    at = column.type_span[1]
    return (at, at), " " + addition


def retyped(column: ColumnText, sql: str) -> list[Edit]:
    start, end = column.type_span
    if start == end:
        return [((start, end), " " + sql)]
    return [((start, end), sql)]


def appended(table: TableText, item: str) -> Edit:
    """A new last item of the definition."""
    at = table.items[-1][1]
    return (at, at), ",\n  " + item


def column_added(table: TableText, item: str) -> Edit:
    """A new column, after the last column and before the table's constraints."""
    last = max(column.item for column in table.columns.values())
    at = table.items[last][1]
    return (at, at), ",\n  " + item


def constraint_names(table: TableText) -> dict[str, Clause]:
    """Every constraint of the text by the name the catalog shows it under (D249)."""
    named: dict[str, Clause] = {}
    checks = 0
    for clause in table.constraints:
        if clause.kind == "check":
            checks += 1
        if clause.name is not None:
            named[clause.name] = clause
            continue
        listed = ", ".join(quoted_name(column) for column in clause.columns)
        if clause.kind == "primary":
            named["PRIMARY KEY"] = clause
        elif clause.kind == "unique":
            named[f"UNIQUE ({listed})"] = clause
        elif clause.kind == "foreign":
            named[f"FOREIGN KEY ({listed})"] = clause
        else:
            named[f"CHECK {checks}"] = clause
    return named


def uses_column(clause: Clause, name: str) -> bool:
    return any(column.lower() == name.lower() for column in clause.columns)


@dataclass(frozen=True)
class Kept:
    """An index or trigger of the table, made again after the rebuild."""

    name: str
    sql: str
    columns: list[str]


_KEPT = """
SELECT name, sql FROM sqlite_schema
WHERE tbl_name = ? AND type = ? AND sql IS NOT NULL
ORDER BY name
"""
_INDEX_COLUMNS = "SELECT name FROM pragma_index_info(?, 'main') WHERE name IS NOT NULL"
_HAS_SEQUENCE = "SELECT 1 FROM sqlite_schema WHERE type = 'table' AND name = 'sqlite_sequence'"
_SEQUENCE = "SELECT seq FROM sqlite_sequence WHERE name = ?"
_TAKEN = "SELECT 1 FROM sqlite_schema WHERE name = ? COLLATE NOCASE"
_WITHOUT_ROWID = "SELECT wr FROM pragma_table_list WHERE schema = 'main' AND name = ?"
_BROKEN_KEYS = "SELECT count(*) FROM pragma_foreign_key_check(?, 'main')"
_VIEWS = "SELECT name FROM sqlite_schema WHERE type = 'view' ORDER BY name"


def free_name(connection: sqlite3.Connection, wanted: str) -> str:
    """`wanted`, or it with a number, whichever no object of the file has."""
    candidate = wanted
    number = 1
    while connection.execute(_TAKEN, (candidate,)).fetchone() is not None:
        number += 1
        candidate = f"{wanted}_{number}"
    return candidate


def rebuild(
    connection: sqlite3.Connection,
    name: str,
    definition: str,
    copied: list[str],
    *,
    keep_index: Callable[[Kept], bool] = lambda _kept: True,
) -> None:
    """Replace table `name` with one made by `definition`, its rows copied.

    `definition` is the whole `CREATE TABLE` statement under the table's own
    name; `copied` are the columns both tables have, which carry the rows. The
    caller runs this inside `SqliteSession.restructure`, which has switched
    foreign keys off: dropping the old table would otherwise act on the rows
    that point at it.
    """
    table = read_table(definition)
    if table.name_span is None:
        raise ValueError(say("The table's definition could not be read"))
    temporary = free_name(connection, f"dp_rebuild_{name}")
    indexes = [
        Kept(
            str(row[0]),
            str(row[1]),
            [str(found[0]) for found in connection.execute(_INDEX_COLUMNS, (row[0],))],
        )
        for row in connection.execute(_KEPT, (name, "index")).fetchall()
    ]
    triggers = [
        Kept(str(row[0]), str(row[1]), [])
        for row in connection.execute(_KEPT, (name, "trigger")).fetchall()
    ]
    sequence = (
        connection.execute(_SEQUENCE, (name,)).fetchone()
        if connection.execute(_HAS_SEQUENCE).fetchone() is not None
        else None
    )
    connection.execute(edited(definition, [(table.name_span, quoted_name(temporary))]))
    rowids = not connection.execute(_WITHOUT_ROWID, (name,)).fetchone()[0] and not (
        connection.execute(_WITHOUT_ROWID, (temporary,)).fetchone()[0]
    )
    carried: list[Composable] = [Identifier(column) for column in copied]
    if rowids:
        # The rows keep their rowids, and with them their order (D251). A
        # fixed word: quoted, it would be a column of that name.
        carried.insert(0, SQL("rowid"))
    if carried:
        listed = SQL(", ").join(carried)
        connection.execute(
            SQL("INSERT INTO {} ({}) SELECT {} FROM {}")
            .format(Identifier("main", temporary), listed, listed, Identifier("main", name))
            .text()
        )
    connection.execute(SQL("DROP TABLE {}").format(Identifier("main", name)).text())
    # The rename checks every view against the schema as it is mid-rebuild,
    # where the old name is gone, and refuses; SQLite's own procedure renames
    # in the legacy way and leaves views to be checked afterwards (below).
    connection.execute("PRAGMA legacy_alter_table = ON")
    try:
        connection.execute(
            SQL("ALTER TABLE {} RENAME TO {}")
            .format(Identifier("main", temporary), Identifier(name))
            .text()
        )
    finally:
        connection.execute("PRAGMA legacy_alter_table = OFF")
    for kept in indexes:
        if keep_index(kept):
            connection.execute(kept.sql)
    for kept in triggers:
        connection.execute(kept.sql)
    if sequence is not None:
        # The counter AUTOINCREMENT keeps may be past the largest rowid copied.
        connection.execute(
            "UPDATE sqlite_sequence SET seq = max(seq, ?) WHERE name = ?", (sequence[0], name)
        )
        connection.execute(
            "INSERT INTO sqlite_sequence (name, seq) SELECT ?, ? "
            "WHERE NOT EXISTS (SELECT 1 FROM sqlite_sequence WHERE name = ?)",
            (name, sequence[0], name),
        )
    for (view,) in connection.execute(_VIEWS).fetchall():
        try:
            connection.execute(SQL("SELECT * FROM {} LIMIT 0").format(Identifier("main", view)).text())
        except sqlite3.OperationalError:
            raise ValueError(
                say('The view "{name}" reads what this change takes away', name=view)
            ) from None
    if connection.execute(_BROKEN_KEYS, (name,)).fetchone()[0]:
        raise ValueError(say("Some rows point at nothing in the target relation"))
