"""Stopping what a connection runs, from the Processes report (D70).

The ids a request sends are checked to be whole numbers and are bound; nothing
else of the request reaches a statement.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import pymysql

from app.adapters.mysql.reports import PROCESSES_REPORT_ID
from app.adapters.mysql.session import MysqlSession
from app.adapters.row_commands import RowCommand, RowCommandResult, UnknownRowCommand
from app.core.translation import N_, say

ID_COLUMN = "id"
MAX_KEYS = 500

# What the server says about a connection it will not stop, by error number.
_REFUSALS: dict[int, str] = {
    1094: N_("it has already ended"),
    1095: N_("this connection may not stop it"),
}


@dataclass(frozen=True)
class _Runnable:
    command: RowCommand
    statement: str
    said: Callable[[int, int], str]


def _tally(done: int, asked: int, *, every: str, short: str) -> str:
    return every if done == asked else short


KILL_QUERY = _Runnable(
    command=RowCommand(
        name="kill_query",
        title=N_("Cancel query"),
        icon="cancel",
        description=N_("Stop the statement the connection is running. The connection stays open."),
        destructive=True,
        requires="structure",
        identified_by=ID_COLUMN,
    ),
    statement="KILL QUERY %s",
    said=lambda done, asked: _tally(
        done,
        asked,
        every=say("{done} statements stopped", done=done),
        short=say("{done} of {asked} statements stopped", done=done, asked=asked),
    ),
)

KILL_CONNECTION = _Runnable(
    command=RowCommand(
        name="kill_connection",
        title=N_("Terminate"),
        icon="power_settings_new",
        description=N_(
            "Close the connection, rolling back whatever it was doing. "
            "Use it when cancelling was not enough."
        ),
        destructive=True,
        requires="structure",
        identified_by=ID_COLUMN,
    ),
    statement="KILL CONNECTION %s",
    said=lambda done, asked: _tally(
        done,
        asked,
        every=say("{done} connections closed", done=done),
        short=say("{done} of {asked} connections closed", done=done, asked=asked),
    ),
)

_RUNNABLE = {runnable.command.name: runnable for runnable in (KILL_QUERY, KILL_CONNECTION)}


class MysqlRowCommands:
    def __init__(self, session: MysqlSession) -> None:
        self._session = session

    def for_node(self, node_id: str) -> list[RowCommand]:
        if node_id != PROCESSES_REPORT_ID:
            return []
        return [runnable.command.model_copy(update={
            "title": say(runnable.command.title),
            "description": say(runnable.command.description),
        }) for runnable in _RUNNABLE.values()]

    async def run(self, node_id: str, name: str, keys: Sequence[str]) -> RowCommandResult:
        runnable = _RUNNABLE.get(name)
        if node_id != PROCESSES_REPORT_ID or runnable is None:
            raise UnknownRowCommand(name)
        if not keys or len(keys) > MAX_KEYS:
            raise ValueError(say("Pick between 1 and {count} rows", count=MAX_KEYS))
        if not all(key.isdigit() for key in keys):
            raise ValueError(say("A connection is named by its number"))
        done = 0
        refused: list[str] = []
        async with self._session.acquire() as connection:
            for key in dict.fromkeys(keys):
                try:
                    async with connection.cursor() as cursor:
                        await cursor.execute(runnable.statement, (int(key),))
                    done += 1
                except pymysql.err.MySQLError as exc:
                    reason = _REFUSALS.get(exc.args[0] if exc.args else 0)
                    if reason is None:
                        raise
                    refused.append(say("{key}: {reason}", key=key, reason=say(reason)))
        asked = len(dict.fromkeys(keys))
        return RowCommandResult(message=runnable.said(done, asked), done=done, refused=refused)
