"""One structure change of a DuckDB file, in a transaction, views read after (D396).

DuckDB's structure changes are transactional (D393), so a change and the
checks around it are one transaction: what the rows contradict is counted
first, the change made, and every view of the file bound again, since DuckDB
renames and drops a column without looking at the views that read it. A view
that bound before and does not after refuses the change by name.
"""

from collections.abc import Callable

import duckdb

from app.adapters.duckdb.inspection import RelationFacts
from app.adapters.duckdb.query import redacted
from app.adapters.duckdb.session import DuckdbSession, classify
from app.adapters.duckdb.sql import SQL, Composable, Identifier
from app.adapters.duckdb.statements import sentence
from app.adapters.protocol import AdapterError
from app.core.translation import N_, say

# How far a count of what stands in the way goes before it says "at least" (D37).
COUNT_CEILING = 1000

_VIEWS = """
SELECT schema_name, view_name FROM duckdb_views()
WHERE database_name = current_database() AND NOT internal AND NOT temporary
"""

# What DuckDB refuses about a structure change: said in its own sentence,
# which names the index, the view or the column in the way.
_REFUSED = (
    duckdb.CatalogException,
    duckdb.DependencyException,
    duckdb.NotImplementedException,
    duckdb.ConstraintException,
    duckdb.ConversionException,
    duckdb.BinderException,
    duckdb.InvalidInputException,
    duckdb.ParserException,
)


class _BrokenView(Exception):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name


def structure_reason(facts: RelationFacts) -> str | None:
    """Why this relation's structure cannot be changed, or nothing."""
    if facts.is_view:
        return say("Only a table's structure can be changed")
    return None


def bounded_count(
    connection: duckdb.DuckDBPyConnection, statement: Composable, params: list[object] | None = None
) -> tuple[int, bool]:
    """How many rows a statement finds, up to the ceiling, and whether that is all."""
    counted = SQL("SELECT count(*) FROM ({} LIMIT ?)").format(statement)
    row = connection.execute(counted.text(), [*(params or []), COUNT_CEILING + 1]).fetchone()
    found = 0 if row is None else int(row[0])
    return min(found, COUNT_CEILING), found <= COUNT_CEILING


def _views(connection: duckdb.DuckDBPyConnection) -> list[tuple[str, str]]:
    return [(str(schema), str(name)) for schema, name in connection.execute(_VIEWS).fetchall()]


def _binds(connection: duckdb.DuckDBPyConnection, view: tuple[str, str]) -> bool:
    statement = SQL("SELECT * FROM {} LIMIT 0").format(Identifier(*view))
    try:
        connection.execute(statement.text())
    except duckdb.Error:
        return False
    return True


def _broken_views(connection: duckdb.DuckDBPyConnection) -> set[tuple[str, str]]:
    """The views that do not bind now, read outside any transaction, so each
    failure ends only its own statement."""
    return {view for view in _views(connection) if not _binds(connection, view)}


async def restructure[T](
    session: DuckdbSession,
    work: Callable[[duckdb.DuckDBPyConnection], T],
    *,
    views: bool = False,
) -> T:
    """Run `work` as one transaction, committed when it returns and, with
    `views`, when no view it reaches stopped binding."""

    def job(connection: duckdb.DuckDBPyConnection) -> T:
        before = _broken_views(connection) if views else set()
        connection.execute("BEGIN")
        try:
            answer = work(connection)
            if views:
                # Inside the change's transaction, which is the only place the
                # change is visible: the first view that fails aborts it, and
                # it is rolled back anyway (D393).
                for view in _views(connection):
                    if view not in before and not _binds(connection, view):
                        raise _BrokenView(view[1])
        except BaseException:
            try:
                connection.execute("ROLLBACK")
            except duckdb.TransactionException:
                pass
            raise
        connection.execute("COMMIT")
        return answer

    handle = await session.handle()
    try:
        return await handle.call(job)
    except duckdb.DependencyException:
        # DuckDB's own sentence names no dependency (checked on 2.0.0).
        raise ValueError(
            say(
                "DuckDB cannot change this table while an index of it, or another "
                "table's foreign key to it, depends on it; adding a column, a default "
                "or an index still works"
            )
        ) from None
    except _BrokenView as broken:
        raise ValueError(
            say('View "{name}" reads what this change takes away', name=broken.name)
        ) from None
    except _REFUSED as exc:
        raise ValueError(redacted(sentence(str(exc)), session.home)) from None
    except duckdb.Error as exc:
        error_kind, message = classify(exc, fallback_message=N_("The structure could not be changed"))
        raise AdapterError(error_kind, message) from None
    finally:
        await handle.close()


def table_of(facts: RelationFacts) -> Identifier:
    return Identifier(facts.schema, facts.name)
