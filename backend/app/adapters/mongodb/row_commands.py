"""Stopping an operation, from the Operations report (D70, D289).

An operation is named by its `opid`, a number read from the row; nothing else
of the request reaches the command.
"""

from collections.abc import Sequence

from app.adapters.mongodb.reports import REPORTS
from app.adapters.mongodb.session import MongodbSession
from app.adapters.row_commands import RowCommand, RowCommandResult, UnknownRowCommand
from app.core.translation import N_, say

OPERATIONS_REPORT_ID = next(report.node_id for report in REPORTS if report.key == "operations")
MAX_KEYS = 500

KILL_OPERATION = RowCommand(
    name="kill_operation",
    title=N_("Stop operation"),
    icon="cancel",
    description=N_("Stop the operation. What it already wrote stays written."),
    destructive=True,
    requires="structure",
    identified_by="id",
)


class MongodbRowCommands:
    def __init__(self, session: MongodbSession) -> None:
        self._session = session

    def for_node(self, node_id: str) -> list[RowCommand]:
        if node_id != OPERATIONS_REPORT_ID:
            return []
        return [
            KILL_OPERATION.model_copy(
                update={
                    "title": say(KILL_OPERATION.title),
                    "description": say(KILL_OPERATION.description),
                }
            )
        ]

    async def run(self, node_id: str, name: str, keys: Sequence[str]) -> RowCommandResult:
        if name != KILL_OPERATION.name or node_id != OPERATIONS_REPORT_ID:
            raise UnknownRowCommand(name)
        if not keys or len(keys) > MAX_KEYS:
            raise ValueError(say("Pick between 1 and {count} rows", count=MAX_KEYS))
        wanted = list(dict.fromkeys(keys))
        if not all(key.lstrip("-").isdigit() and len(key) < 20 for key in wanted):
            raise ValueError(say("That does not name a row of this report"))
        async with self._session.client() as client:
            with self._session.failures():
                for key in wanted:
                    # killOp answers ok for an operation that has already ended.
                    await client.admin.command("killOp", op=int(key))
        done = len(wanted)
        return RowCommandResult(
            message=say("{done} operations stopped", done=done), done=done, refused=[]
        )
