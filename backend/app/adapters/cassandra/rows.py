"""What may be done to a Cassandra table's rows, and how a row is named (D345).

A row is named by its primary key — the partition key and the clustering
columns, which together are unique — and a digest of the row as it was shown,
the handle MySQL's is (`app.adapters.row_handles`).
"""

from app.adapters.cassandra.inspection import ColumnFacts, RelationFacts
from app.adapters.cassandra.types import type_name
from app.adapters.row_handles import encode_handle, version_of
from app.core.translation import say


def change_reason(facts: RelationFacts) -> str | None:
    """Why this relation's rows cannot be changed here, or nothing."""
    if facts.is_system:
        return say('"{keyspace}" belongs to the server', keyspace=facts.keyspace)
    if facts.is_virtual:
        return say("A virtual table is the server's own")
    if facts.is_view:
        return say("A materialized view's rows are written by its table")
    if facts.has_counters:
        return say(
            "A counter table is changed by adding to its counters, in the console"
        )
    return None


def writable(column: ColumnFacts) -> bool:
    """Whether a value of this column can be written from its text.

    A key column decides where the row is kept and is never changed; a
    duration has no spelling that is read back.
    """
    return not column.in_key and type_name(column.type_text) != "duration"


def key_positions(facts: RelationFacts) -> list[int]:
    """Where the primary key's columns sit in a row of `facts.columns`."""
    position = {column.name: index for index, column in enumerate(facts.columns)}
    return [position[column.name] for column in facts.primary_key]


def handles_of(facts: RelationFacts, rows: list[list[str | None]]) -> list[str | None]:
    if change_reason(facts) is not None:
        return []
    keys = key_positions(facts)
    return [
        encode_handle([row[index] for index in keys], version_of(row)) for row in rows
    ]
