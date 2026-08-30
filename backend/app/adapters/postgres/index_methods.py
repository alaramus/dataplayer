"""The closed PostgreSQL index method vocabulary, and what the server says of it.

The set of methods offered is decided here. What each of them can do is not:
`pg_indexam_has_property` answers that, and the answer changes with what is
installed, so a table written down in this repository would be wrong within a
release.
"""

from typing import Any

from psycopg import sql

from app.adapters.relation import IndexMethodOption

# code -> (title, the access method's own name). The order is the order the
# choices are offered in, so the usual answer comes first.
POSTGRES_INDEX_METHODS: dict[str, tuple[str, str]] = {
    "btree": ("B-tree", "btree"),
    "hash": ("Hash", "hash"),
    "brin": ("BRIN", "brin"),
    "gin": ("GIN", "gin"),
    "gist": ("GiST", "gist"),
}

# Written out rather than derived from the table above: a fragment of a
# statement is a literal in this project, and composing one from a variable is
# how the distinction between syntax and data gets lost.
POSTGRES_INDEX_METHOD_SQL: dict[str, sql.SQL] = {
    "btree": sql.SQL("btree"),
    "hash": sql.SQL("hash"),
    "brin": sql.SQL("brin"),
    "gin": sql.SQL("gin"),
    "gist": sql.SQL("gist"),
}

# One row per access method the server has, with the two limits worth knowing
# before a statement is built. Filtered down to the offered ones afterwards, so
# an installation missing one simply does not publish it.
INDEX_METHOD_PROPERTIES = """
SELECT amname AS name,
       pg_indexam_has_property(oid, 'can_unique') AS unique_supported,
       pg_indexam_has_property(oid, 'can_multi_col') AS multi_column_supported
FROM pg_am
WHERE amtype = 'i'
"""


def index_method_options(rows: list[dict[str, Any]]) -> list[IndexMethodOption]:
    """The offered methods, in the order this module lists them."""
    by_name = {str(row["name"]): row for row in rows}
    options = []
    for code, (title, name) in POSTGRES_INDEX_METHODS.items():
        row = by_name.get(name)
        if row is None:
            continue
        options.append(
            IndexMethodOption(
                code=code,
                title=title,
                sql=name,
                unique_supported=bool(row["unique_supported"]),
                multi_column_supported=bool(row["multi_column_supported"]),
            )
        )
    return options
