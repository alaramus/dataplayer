"""Acting on the rows of the reports PostgreSQL writes about itself.

Two reports have something to act on. The Processes report (D55) lists what is
connected and what each backend is doing; reading it and being unable to stop a
statement that has been running for an hour is half a tool, and the old
application had the other half. The Extensions report lists what this server
offers and what is installed, and the thing a person does there is install one
and remove another — from the list, on the rows they are already looking at,
rather than by typing a name into a form that names nothing else.

No statement here is composed from anything a request carries. A request
chooses a command by name from the ones below; the pids it sends are bound as
an array parameter, and an extension name selects a row of the server's own
catalog whose spelling is what reaches the statement.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from psycopg import sql

from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.system_reports import (
    EXTENSIONS_REPORT_ID,
    PROCESSES_REPORT_ID,
)
from app.adapters.row_commands import (
    RowCommand,
    RowCommandCondition,
    RowCommandResult,
    UnknownRowCommand,
)

# The column of the Processes report that names a backend, and the column of
# the Extensions report that names an extension.
PID_COLUMN = "pid"
NAME_COLUMN = "name"
# The column of the Extensions report that says whether one is installed, and
# what its cell holds. The value is this source's own spelling of a boolean,
# which is what the client compares the cell against.
INSTALLED_COLUMN = "installed"
INSTALLED = "true"
NOT_INSTALLED = "false"

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
        icon="cancel",
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
        icon="power_settings_new",
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


# What the server says when a change to its extensions cannot be made. Named
# codes rather than the driver's text, which carries the connection string.
EXTENSION_REFUSALS = {
    # duplicate_object: a backstop. Installing one already installed is
    # refused by name before the statement runs, but two callers can still
    # race, and the second must read like a refusal rather than a fault.
    "42710": "it is already installed",
    # dependent_objects_still_exist.
    "2BP01": "something in this database is built on it",
    # insufficient_privilege: installing one usually needs a superuser.
    "42501": "this connection may not change the extensions of this server",
    # undefined_file: the extension is listed but its files are not installed.
    "58P01": "the server lists it but cannot find its files",
    # undefined_object: it is built on an extension that is not there, which
    # CASCADE normally settles — so this is a server that refuses that too.
    "42704": "it needs another extension that is not installed",
}

INSTALL_EXTENSION = RowCommand(
    name="install_extension",
    title="Install",
    icon="add",
    description=(
        "Install this on the server. Anything it is built on is installed "
        "with it."
    ),
    requires="structure",
    identified_by=NAME_COLUMN,
    # Only where it is not installed: the row already says which of the two
    # commands is the one that means anything on it.
    applies_when=RowCommandCondition(column=INSTALLED_COLUMN, equals=NOT_INSTALLED),
    # An extension arrives with schemas, types and functions of its own.
    changes_structure=True,
)

DROP_EXTENSION = RowCommand(
    name="drop_extension",
    title="Remove",
    icon="delete",
    description=(
        "Remove this from the server. Whatever was built on it is kept and "
        "the server refuses instead, rather than the removal taking it too."
    ),
    destructive=True,
    requires="structure",
    identified_by=NAME_COLUMN,
    applies_when=RowCommandCondition(column=INSTALLED_COLUMN, equals=INSTALLED),
    changes_structure=True,
)

# How many extensions one request may change. A person picks rows out of a
# page, and each one here is a DDL statement of its own.
MAX_EXTENSIONS = 50

# Which report offers which commands. A table rather than a chain of
# comparisons, so a report that gains a command is an entry here.
_OFFERED: dict[str, tuple[RowCommand, ...]] = {
    PROCESSES_REPORT_ID: (CANCEL.command, TERMINATE.command),
    EXTENSIONS_REPORT_ID: (INSTALL_EXTENSION, DROP_EXTENSION),
}


class PostgresRowCommands:
    """The commands PostgreSQL offers over the rows of its own reports."""

    def __init__(self, session: PostgresSession) -> None:
        self._session = session

    def for_node(self, node_id: str) -> list[RowCommand]:
        """What this node offers. Nothing, for every node but two reports.

        Said here rather than in each report's own declaration because it is
        this module that can carry them out: a report that named a command
        nobody implements would be a promise with nothing behind it.
        """
        return list(_OFFERED.get(node_id, ()))

    async def run(
        self, node_id: str, name: str, keys: Sequence[str]
    ) -> RowCommandResult:
        offered = {command.name for command in self.for_node(node_id)}
        if name not in offered:
            raise UnknownRowCommand(name)
        if node_id == EXTENSIONS_REPORT_ID:
            return await self._extensions(name, keys)
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


    async def _extensions(self, name: str, keys: Sequence[str]) -> RowCommandResult:
        """Install or remove the extensions these rows name, one at a time.

        One statement each rather than one for all of them: DDL cannot be
        parameterised, each is refused for its own reason, and a person who
        ticked four rows wants to be told which of the four the server would
        not do.
        """
        if len(keys) > MAX_EXTENSIONS:
            raise ValueError(f"At most {MAX_EXTENSIONS} extensions at a time")
        installing = name == INSTALL_EXTENSION.name
        done: list[str] = []
        refused: list[str] = []
        for typed in keys:
            named = await self._extension_named(typed, installing=installing)
            if named is None:
                refused.append(
                    f'"{typed}" is not offered by this server'
                    if installing
                    else f'"{typed}" is not installed'
                )
                continue
            if not installing and named == "timescaledb":
                refused.append("TimescaleDB removal is not supported by structured operations")
                continue
            statement = (
                # CASCADE here means "install what this one is built on", which
                # is a different promise from a cascading drop: it adds, and
                # what it adds is what the chosen extension needs to exist.
                sql.SQL("CREATE EXTENSION {} CASCADE")
                if installing
                else sql.SQL("DROP EXTENSION {}")
            ).format(sql.Identifier(named))
            try:
                await self._session.schema_change(
                    statement.as_string(), refusals=EXTENSION_REFUSALS
                )
            except ValueError as refusal:
                refused.append(f"{named}: {refusal}")
                continue
            done.append(named)
        return RowCommandResult(
            message=_extension_said(
                done=len(done),
                asked=len(keys),
                verb="installed" if installing else "removed",
            ),
            done=len(done),
            refused=refused,
        )

    async def _extension_named(self, typed: str, *, installing: bool) -> str | None:
        """The server's own spelling of an extension, or nothing.

        The client's text selects a row; the identifier that reaches the
        statement is the name that came back, never the string that was sent.
        So the only extension that can be named is one this server already
        lists, and in the state the command needs it to be in.
        """
        if installing:
            rows = await self._session.query(
                """
                SELECT name FROM pg_available_extensions
                WHERE name = %s AND installed_version IS NULL
                """,
                (typed,),
            )
        else:
            rows = await self._session.query(
                "SELECT extname AS name FROM pg_extension WHERE extname = %s",
                (typed,),
            )
        return str(rows[0]["name"]) if rows else None


def _extension_said(*, done: int, asked: int, verb: str) -> str:
    subject = "extension" if asked == 1 else "extensions"
    if done == asked:
        return f"{done} {subject} {verb}"
    return f"{done} of {asked} {subject} {verb}"


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
