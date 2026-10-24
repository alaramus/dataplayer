"""What a node id of a SQLite source is made of (D248).

`main`, or `main.<relation>`. The schema part is a fixed name with no dot, so
the first dot is the separator and a relation's name keeps all of its own.
"""

from app.adapters.sqlite.inspection import SCHEMA


def relation_id(relation: str) -> str:
    return f"{SCHEMA}.{relation}"


def parse(node_id: str) -> tuple[str, str | None]:
    """The schema and the relation an id names; no relation for the schema."""
    schema, dot, relation = node_id.partition(".")
    return schema, relation if dot else None
