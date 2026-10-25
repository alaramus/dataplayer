"""Stopping a query or a mutation, from the Processes and Mutations reports (D70, D275).

A query is named by its id and a mutation by the number its report gives it,
both bound as parameters; nothing else of the request reaches a statement.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from app.adapters.clickhouse.reports import MUTATIONS_REPORT_ID, PROCESSES_REPORT_ID
from app.adapters.clickhouse.session import ClickhouseSession, Encoded
from app.adapters.clickhouse.sql import array_of_strings
from app.adapters.row_commands import RowCommand, RowCommandResult, UnknownRowCommand
from app.core.translation import N_, say

ID_COLUMN = "id"
MAX_KEYS = 500
# A query id is any text up to the server's limit; a mutation's number is one.
_MAX_KEY_CHARS = 1000


@dataclass(frozen=True)
class _Runnable:
    command: RowCommand
    report: str
    # Answers the ids it stopped, of those asked.
    statement: str
    key_type: str
    said: Callable[[int, int], str]


def _tally(done: int, asked: int, *, every: str, short: str) -> str:
    return every if done == asked else short


KILL_QUERY = _Runnable(
    command=RowCommand(
        name="kill_query",
        title=N_("Cancel query"),
        icon="cancel",
        description=N_("Stop the query. What it already wrote stays written."),
        destructive=True,
        requires="structure",
        identified_by=ID_COLUMN,
    ),
    report=PROCESSES_REPORT_ID,
    statement="KILL QUERY WHERE query_id IN {ids:Array(String)} SYNC",
    key_type="String",
    said=lambda done, asked: _tally(
        done,
        asked,
        every=say("{done} queries stopped", done=done),
        short=say("{done} of {asked} queries stopped", done=done, asked=asked),
    ),
)

KILL_MUTATION = _Runnable(
    command=RowCommand(
        name="kill_mutation",
        title=N_("Stop mutation"),
        icon="cancel",
        description=N_(
            "Stop rewriting the table's parts. Parts already rewritten keep the change; "
            "a mutation that keeps failing stops holding up the table's next change."
        ),
        destructive=True,
        requires="structure",
        identified_by=ID_COLUMN,
    ),
    report=MUTATIONS_REPORT_ID,
    statement=(
        "KILL MUTATION WHERE cityHash64(database, table, mutation_id) IN {ids:Array(UInt64)} SYNC"
    ),
    key_type="UInt64",
    said=lambda done, asked: _tally(
        done,
        asked,
        every=say("{done} mutations stopped", done=done),
        short=say("{done} of {asked} mutations stopped", done=done, asked=asked),
    ),
)

_RUNNABLE = {runnable.command.name: runnable for runnable in (KILL_QUERY, KILL_MUTATION)}


class ClickhouseRowCommands:
    def __init__(self, session: ClickhouseSession) -> None:
        self._session = session

    def for_node(self, node_id: str) -> list[RowCommand]:
        return [
            runnable.command.model_copy(
                update={
                    "title": say(runnable.command.title),
                    "description": say(runnable.command.description),
                }
            )
            for runnable in _RUNNABLE.values()
            if runnable.report == node_id
        ]

    async def run(self, node_id: str, name: str, keys: Sequence[str]) -> RowCommandResult:
        runnable = _RUNNABLE.get(name)
        if runnable is None or runnable.report != node_id:
            raise UnknownRowCommand(name)
        if not keys or len(keys) > MAX_KEYS:
            raise ValueError(say("Pick between 1 and {count} rows", count=MAX_KEYS))
        wanted = list(dict.fromkeys(keys))
        if any(len(key) > _MAX_KEY_CHARS for key in wanted) or (
            runnable.key_type == "UInt64" and not all(key.isdigit() for key in wanted)
        ):
            raise ValueError(say("That does not name a row of this report"))
        ids = (
            array_of_strings(wanted)
            if runnable.key_type == "String"
            else Encoded("[" + ",".join(wanted) + "]")
        )
        # KILL … SYNC answers a line for each one it stopped.
        answer = await self._session.answer(runnable.statement, {"ids": ids}, read=False)
        done = len(answer.rows)
        return RowCommandResult(message=runnable.said(done, len(wanted)), done=done, refused=[])
