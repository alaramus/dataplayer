"""Acting on the backends PostgreSQL reports about itself.

The Processes report (D55) lists what is connected and what each of them is
doing. Reading it and being unable to do anything about a statement that has
been running for an hour is half a tool, and the old application had the other
half: `cancel` and `terminate` on a pid.

Both statements are written here and never composed from anything a request
carries. A request chooses a command by name from the two below; the pids it
sends are bound as an array parameter, and the server does the rest.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from psycopg import sql

from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.system_reports import PROCESSES_REPORT_ID
from app.adapters.row_commands import (
    RowCommand,
    RowCommandResult,
    UnknownRowCommand,
)

# The column of the Processes report that names a backend.
PID_COLUMN = "pid"

# How many backends one request may act on. A person picks rows out of a page,
# and a page has a ceiling of its own; this is the same statement made where
# the request arrives.
MAX_KEYS = 500


@dataclass(frozen=True)
class _Runnable:
    """One offered command and the function that carries it out."""

    command: RowCommand
    function: sql.Identifier
    # What to say afterwards. Written per command because "cancelled" and
    # "closed" are different things and the difference is the whole point.
    done_wording: str


CANCEL = _Runnable(
    command=RowCommand(
        name="cancel_query",
        title="Cancel query",
        description=(
            "Ask the backend to stop the statement it is running. "
            "The connection stays open."
        ),
        destructive=True,
        # The strongest level that can be given away: stopping somebody else's
        # work is not what "may write rows" was granted for.
        requires="structure",
        identified_by=PID_COLUMN,
    ),
    function=sql.Identifier("pg_catalog", "pg_cancel_backend"),
    done_wording="asked to stop",
)

TERMINATE = _Runnable(
    command=RowCommand(
        name="terminate_backend",
        title="Terminate",
        description=(
            "Close the connection, rolling back whatever it was doing. "
            "Use it when cancelling was not enough."
        ),
        destructive=True,
        requires="structure",
        identified_by=PID_COLUMN,
    ),
    function=sql.Identifier("pg_catalog", "pg_terminate_backend"),
    done_wording="closed",
)

_RUNNABLE = {runnable.command.name: runnable for runnable in (CANCEL, TERMINATE)}


class PostgresRowCommands:
    """The commands PostgreSQL offers over the rows of its own reports."""

    def __init__(self, session: PostgresSession) -> None:
        self._session = session

    def for_node(self, node_id: str) -> list[RowCommand]:
        """What this node offers. Nothing, for everything but one report.

        Said here rather than in the report's own declaration because it is
        this module that can carry them out: a report that named a command
        nobody implements would be a promise with nothing behind it.
        """
        if node_id != PROCESSES_REPORT_ID:
            return []
        return [runnable.command for runnable in (CANCEL, TERMINATE)]

    async def run(
        self, node_id: str, name: str, keys: Sequence[str]
    ) -> RowCommandResult:
        offered = {command.name for command in self.for_node(node_id)}
        if name not in offered:
            raise UnknownRowCommand(name)
        runnable = _RUNNABLE[name]
        if len(keys) > MAX_KEYS:
            raise ValueError(f"At most {MAX_KEYS} processes at a time")

        pids, unreadable = _pids(keys)
        acted: list[int] = []
        refused = [f"{key} is not a process id" for key in unreadable]
        if pids:
            rows = await self._session.query(
                sql.SQL("""
                    SELECT p AS pid,
                           CASE WHEN p = pg_backend_pid() THEN NULL
                                ELSE {}(p) END AS acted
                    FROM unnest(%s::int[]) AS p
                """)
                .format(runnable.function)
                .as_string(),
                (pids,),
            )
            for row in rows:
                pid = int(row["pid"])
                if row["acted"] is True:
                    acted.append(pid)
                elif row["acted"] is None:
                    refused.append(f"{pid} is this connection")
                else:
                    refused.append(f"{pid} is no longer running")

        return RowCommandResult(
            message=_said(runnable, done=len(acted), asked=len(keys)),
            done=len(acted),
            refused=refused,
        )


def _pids(keys: Sequence[str]) -> tuple[list[int], list[str]]:
    """The keys that are process ids, and the ones that are not.

    Never passed on as text: a pid is an integer, and one that is not is a
    request about something this report does not hold rather than a failure of
    the server.
    """
    pids: list[int] = []
    unreadable: list[str] = []
    for key in keys:
        try:
            pids.append(int(key))
        except ValueError:
            unreadable.append(key)
    return pids, unreadable


def _said(runnable: _Runnable, *, done: int, asked: int) -> str:
    """One line about the whole request.

    The count of what was asked stays in it even when everything worked: a
    person who ticked four rows wants to read that four happened.
    """
    subject = "process" if asked == 1 else "processes"
    if done == asked:
        return f"{done} {subject} {runnable.done_wording}"
    return f"{done} of {asked} {subject} {runnable.done_wording}"
