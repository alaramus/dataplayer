"""Rows read on from where a pipeline's link stopped, added to a table (D312).

A link's kind only: "since the last run" means nothing to a paste made once,
so Paste in the catalog never offers it. It writes as Add rows does, and
reads through `SupportsReadingOn`: a span drawn when the step starts, read a
block at a time, each block's bookmark kept once the block is written. A
failure between the two reads that block again: at least once.
"""

import asyncio

from app.adapters.actions import ActionRefused
from app.adapters.fetch import FetchColumn
from app.adapters.protocol import (
    DataAdapter,
    SupportsFetch,
    SupportsInsert,
    SupportsReadingOn,
)
from app.adapters.update import ValuesRejected
from app.connectors import imports
from app.connectors.paste.files import TransfersFiles
from app.connectors.paste.kinds import refused
from app.connectors.paste.models import (
    Availability,
    ClipboardMode,
    Foreseen,
    PairEnd,
    PasteColumn,
    PasteKindName,
    PasteOffer,
    PastePair,
    PasteRun,
    PasteWorkflow,
)
from app.connectors.paste.rows import (
    NOT_ROWS,
    columns_of,
    into_table,
    name_of,
    why_ended,
)
from app.connectors.paste.transfer import (
    Transfer,
    TransferItem,
    TransferPlan,
    TransferReport,
    TransferStopped,
)
from app.core.access import Access
from app.core.translation import N_, say

NOT_READ_ON = N_("Only a topic is read on from where the link stopped")


class RowsSinceLast:
    name: PasteKindName = "rows_since_last"
    title = N_("Add new messages to a table")
    doing = N_("Adding new messages")
    done = N_("added")
    needs = N_("Tick a topic")
    workflow: PasteWorkflow = "into-relation"
    mode: ClipboardMode = "copy"
    converts = True
    can_replace = False
    source_requires: Access = "read"
    destination_requires: Access = "write"
    # The reader's bookmark moves, and no message changes.
    changes_source = False
    makes = False
    pipelines = True
    outranks: tuple[PasteKindName, ...] = ()
    # What a node read on is not offered in a pipeline: each would read it
    # whole again at every run.
    replaces: tuple[PasteKindName, ...] = (
        "rows_into_relation",
        "rows_new_relation",
        "relation_csv",
    )

    def takes_from(self, source: DataAdapter) -> bool:
        return isinstance(source, SupportsReadingOn) and isinstance(
            source, SupportsFetch
        )

    def serves(self, source: DataAdapter, destination: DataAdapter) -> bool:
        return (
            self.takes_from(source)
            and isinstance(destination, SupportsInsert)
            and isinstance(destination, SupportsFetch)
            and not isinstance(destination, TransfersFiles)
        )

    async def supply(self, source: DataAdapter, node_ids: list[str]) -> Availability:
        del source, node_ids
        return Availability(
            available=False, reason=say("This is a pipeline's link only")
        )

    async def _source_columns(
        self, source: DataAdapter, end: PairEnd
    ) -> list[FetchColumn] | str:
        if not isinstance(end, str):
            return say(NOT_READ_ON)
        if not isinstance(source, SupportsReadingOn) or not source.reads_on(end):
            return say(NOT_READ_ON)
        return await columns_of(source, [end])

    async def offer(
        self, source: DataAdapter, destination: DataAdapter, pair: PastePair
    ) -> PasteOffer:
        if pair.target_node_id is None:
            return refused(self, say("Tick the table the rows go into"))
        if len(pair.source_node_ids) != 1:
            return refused(self, say("Paste one table at a time"))
        columns = await self._source_columns(source, pair.source_node_ids[0])
        if isinstance(columns, str):
            return refused(self, columns)
        return await into_table(self, destination, pair.target_node_id, columns)

    def made(
        self, source: Foreseen, name: str | None, columns: list[PasteColumn] | None
    ) -> Foreseen | None:
        del source, name, columns
        return None

    async def foresee(
        self,
        source: DataAdapter,
        destination: DataAdapter,
        source_end: PairEnd,
        target_end: PairEnd,
    ) -> PasteOffer:
        if target_end is None or (
            isinstance(target_end, Foreseen) and target_end.kind != "table"
        ):
            return refused(self, say("Tick the table the rows go into"))
        columns = await self._source_columns(source, source_end)
        if isinstance(columns, str):
            return refused(self, columns)
        return await into_table(self, destination, target_end, columns)

    def _checked(
        self, source: DataAdapter, destination: DataAdapter, request: PasteRun
    ) -> str:
        if not self.serves(source, destination):
            raise ActionRefused(
                "not_applicable", say("These connections cannot move rows")
            )
        if len(request.source_node_ids) != 1 or request.reader is None:
            raise ActionRefused("not_applicable", say(NOT_READ_ON))
        if request.target_node_id is None:
            raise ActionRefused(
                "not_applicable", say("Tick the table the rows go into")
            )
        if not request.columns:
            raise ActionRefused("not_applicable", say("Pair at least one column"))
        return request.target_node_id

    async def plan(
        self, source: DataAdapter, destination: DataAdapter, request: PasteRun
    ) -> TransferPlan:
        target = self._checked(source, destination, request)
        return TransferPlan(
            items=[
                TransferItem(
                    node_id=request.source_node_ids[0],
                    name=await name_of(destination, target),
                )
            ],
            bytes_total=None,
            place="",
            columns=request.columns,
            target_node_id=target,
            reader=request.reader,
            start=request.start,
        )

    async def transfer(
        self,
        source: DataAdapter,
        destination: DataAdapter,
        transfer: Transfer,
        report: TransferReport,
    ) -> None:
        if (
            not isinstance(source, SupportsReadingOn)
            or not isinstance(destination, SupportsInsert)
            or transfer.target_node_id is None
            or transfer.reader is None
        ):
            raise TransferStopped(say(NOT_ROWS))
        item = transfer.items[0]
        item.outcome = "running"
        item.rows = 0
        transfer.current = item.name
        try:
            await self._read_on(source, destination, transfer, report)
        except asyncio.CancelledError:
            item.outcome = "stopped"
            raise
        except TransferStopped:
            item.outcome = "failed"
            raise
        except Exception as failure:  # noqa: BLE001 — said in the step's sentence, blocks kept
            item.outcome = "failed"
            raise TransferStopped(why_ended(failure)) from None
        item.outcome = "done"
        item.arrived = 1
        item.published_id = transfer.target_node_id
        transfer.current = None
        transfer.published += 1

    async def _read_on(
        self,
        source: SupportsReadingOn,
        destination: SupportsInsert,
        transfer: Transfer,
        report: TransferReport,
    ) -> None:
        item = transfer.items[0]
        node, reader = item.node_id, transfer.reader or ""
        span = await source.unread(node, reader, transfer.start or "earliest")
        item.skipped = span.lost
        transfer.fresh = span.fresh
        await report.progressed()
        pairs = transfer.columns or []
        write = imports.into_relation(destination, transfer.target_node_id or "")
        at = span.start
        done = 0
        while True:
            block = await source.read_on(
                node,
                [pair.source for pair in pairs],
                at,
                span.line,
                imports.IMPORT_CEILING,
            )
            if block.rows:
                result = await write([pair.target for pair in pairs], block.rows)
                if isinstance(result, ValuesRejected):
                    raise imports.BlockRefused(
                        ValuesRejected(
                            cells=[
                                cell.model_copy(update={"row": cell.row + done})
                                for cell in result.cells
                            ]
                        )
                    )
                done += len(block.rows)
                item.rows = done
            # Kept after every block, an empty one too: Kafka forgets the
            # positions of a group nobody writes for a week.
            await source.mark_read(node, reader, block.after)
            await report.progressed()
            if block.done:
                return
            if block.after == at:
                raise TransferStopped(say("Reading stopped moving on"))
            at = block.after

    def told(self, transfer: Transfer, stopped: str | None = None) -> str:
        item = transfer.items[0]
        rows = item.rows or 0
        if stopped is not None:
            # What arrived before stays, its bookmark kept.
            said = say(
                "{count} new messages added to {name}, then: {reason}",
                count=rows,
                name=item.name,
                reason=stopped,
            )
        elif rows == 0:
            said = say("Nothing new since the last run")
        else:
            said = say(
                "{count} new messages added to {name}", count=rows, name=item.name
            )
        if transfer.fresh:
            said = (
                say(
                    "{said}; no position was kept, so reading started from the beginning",
                    said=said,
                )
                if transfer.start != "latest"
                else say(
                    "{said}; no position was kept, so reading started from the end",
                    said=said,
                )
            )
        if item.skipped:
            said = say(
                "{said}; {count} were deleted before they were read",
                said=said,
                count=item.skipped,
            )
        return said
