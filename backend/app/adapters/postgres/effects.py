"""Which of this source's nodes a structure change was about.

D66: after a change commits, the source says what to re-read. The alternative
is a browser reading node ids out of the SQL it sent, which would put the rule
for what an opaque id means in two places and break the first time a name
needed quoting.

Pure, like `statements`: text and a resolved search path in, node ids out. A
PostgreSQL node id is the schema name, or the schema and the relation joined
by a dot, and that is the only knowledge of ids this module holds.
"""

from collections.abc import Sequence

from sqlglot import exp, parse_one
from sqlglot.errors import ParseError, TokenError

from app.adapters.query import SchemaEffect


def _whole_connection() -> SchemaEffect:
    """What is re-read when the statement does not say enough to be exact."""
    return SchemaEffect(scope="connection")


def effect_of(text: str, *, search_path: Sequence[str]) -> SchemaEffect:
    """What committing this statement would change, as node ids.

    The search path is the effective one — what the server itself would use to
    resolve an unqualified name. A name that is not qualified may be in any
    schema on it, so every one of them is named: an invalidation may be a
    superset of what changed, and never a subset.
    """
    try:
        node = parse_one(text, read="postgres")
    except (ParseError, TokenError):
        return _whole_connection()

    if isinstance(node, exp.Comment):
        return _comment(node, search_path)
    if isinstance(node, exp.TruncateTable):
        return _relations(_tables(node), search_path)
    if isinstance(node, exp.Select):
        # `SELECT ... INTO t` creates a relation; its schema gained a child.
        into = node.args.get("into")
        target = None if into is None else into.this
        if not isinstance(target, exp.Table):
            return SchemaEffect()
        return _containers([target], search_path)
    if not isinstance(node, exp.Create | exp.Drop | exp.Alter):
        return _whole_connection()

    subject = str(node.args.get("kind") or "").upper()
    if subject == "SCHEMA":
        # The root's children are the schemas.
        return SchemaEffect(reload_node_ids=[None])
    if subject == "INDEX":
        return _index(node, search_path)
    if subject in ("TABLE", "VIEW"):
        # An ALTER is asked for every table it names, so a rename reaches both
        # the old node and the new one; a CREATE is asked only for its subject,
        # so `CREATE TABLE a AS SELECT ... FROM b` does not claim b changed.
        named = (
            _tables(node)
            if isinstance(node, exp.Alter)
            else [table for table in [_subject(node)] if table is not None]
        )
        # Both, and whatever the statement was: a create or a drop changes what
        # the schema holds, and an alter changes what is inside the relation.
        # Telling those apart from the tree would be a second reading of the
        # dialect for no gain, and the wrong answer would be a stale screen.
        return _containers(named, search_path).with_(_relations(named, search_path))
    return _whole_connection()


def _index(node: exp.Expression, search_path: Sequence[str]) -> SchemaEffect:
    """What an index statement was about.

    `CREATE INDEX i ON s.t (c)` names the relation, so the relation is named
    back. `DROP INDEX s.i` names the index, and which relation it was on is
    not in the statement — so the answer is the whole connection rather than
    the schema node, whose children did not change either.
    """
    if isinstance(node, exp.Create):
        return _relations(_tables(node), search_path)
    return _whole_connection()


def _comment(node: exp.Expression, search_path: Sequence[str]) -> SchemaEffect:
    """What a comment was attached to."""
    subject = str(node.args.get("kind") or "").upper()
    if subject == "COLUMN":
        column = node.args.get("this")
        if not isinstance(column, exp.Column):
            return _whole_connection()
        parts = [part.name for part in (column.args.get("db"), column.args.get("table")) if part is not None]
        return _relation_ids([part for part in parts if part], search_path)
    if subject in ("TABLE", "VIEW"):
        table = _subject(node)
        return _relations([] if table is None else [table], search_path)
    if subject == "SCHEMA":
        return SchemaEffect(reload_node_ids=[None])
    return _whole_connection()


def _subject(node: exp.Expression) -> exp.Table | None:
    """The relation this statement is about, rather than every one it names."""
    this = node.args.get("this")
    if isinstance(this, exp.Schema):
        # `CREATE TABLE t (...)` wraps the name with its column definitions.
        this = this.this
    return this if isinstance(this, exp.Table) else None


def _tables(node: exp.Expression) -> list[exp.Table]:
    return list(node.find_all(exp.Table))


def _containers(
    tables: Sequence[exp.Table], search_path: Sequence[str]
) -> SchemaEffect:
    """The schema nodes whose children these relations belong to."""
    nodes: list[str | None] = []
    for table in tables:
        for schema in _schemas_of(table, search_path):
            if schema not in nodes:
                nodes.append(schema)
    if not nodes:
        return _whole_connection()
    return SchemaEffect(reload_node_ids=nodes)


def _relations(tables: Sequence[exp.Table], search_path: Sequence[str]) -> SchemaEffect:
    """The relation nodes these names stand for."""
    relations: list[str] = []
    for table in tables:
        if not table.name:
            continue
        for schema in _schemas_of(table, search_path):
            node_id = f"{schema}.{table.name}"
            if node_id not in relations:
                relations.append(node_id)
    if not relations:
        return _whole_connection()
    return SchemaEffect(relation_node_ids=relations)


def _relation_ids(parts: Sequence[str], search_path: Sequence[str]) -> SchemaEffect:
    """A relation named by its parts, qualified or not."""
    if len(parts) >= 2:
        return SchemaEffect(relation_node_ids=[f"{parts[-2]}.{parts[-1]}"])
    if len(parts) == 1 and search_path:
        return SchemaEffect(
            relation_node_ids=[f"{schema}.{parts[0]}" for schema in search_path]
        )
    return _whole_connection()


def _schemas_of(table: exp.Table, search_path: Sequence[str]) -> list[str]:
    """Which schemas this name may be in.

    One when it is qualified. Otherwise every schema the server would look
    through, because which of them holds it is a fact about the source and not
    about the text.
    """
    if table.db:
        return [table.db]
    return list(search_path)
