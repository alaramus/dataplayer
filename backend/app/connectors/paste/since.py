"""Rows read on from where a pipeline's link stopped, added to a table (D312)
or to a table the link makes (D313).

Link kinds only: "since the last run" means nothing to a paste made once, so
Paste in the catalog never offers them. They read through
`SupportsReadingOn`: a span drawn when the step starts, read a block at a
time, each block's bookmark kept once the block is written. A failure
between the two reads that block again: at least once, unless the table the
link made has a key that leaves the repeat out (D313).
"""

import asyncio
from collections.abc import Awaitable, Callable

from app.adapters.actions import ActionRefused
from app.adapters.catalog import CatalogNode
from app.adapters.constraints import CreateConstraintRequest, UniqueConstraintSpec
from app.adapters.fetch import FetchColumn
from app.adapters.keyed import KeyedRow, KeyedWriteRequest
from app.adapters.protocol import (
    DataAdapter,
    SupportsCatalog,
    SupportsConstraints,
    SupportsCreateRelation,
    SupportsDropCreated,
    SupportsFetch,
    SupportsInsert,
    SupportsKeyedWrite,
    SupportsMovingColumns,
    SupportsReadingOn,
    SupportsSkippingInsert,
)
from app.adapters.reading_on import Bookmark
from app.adapters.relation_changes import CreateRelationRequest, NewColumn
from app.adapters.update import InsertRowsRequest, RowsInserted, ValuesRejected
from app.connectors import imports
from app.connectors.paste.files import TransfersFiles
from app.connectors.paste.kinds import offered, refused
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
    made_table,
    moving_columns_of,
    name_of,
    new_table,
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

NOT_READ_ON = N_(
    "Only a topic, a stream, a queue, or a symbol's trades or candles, is read on from where the link stopped"
)

# Kafka's key, said in a sentence of its own: the first source that read on.
MESSAGE_KEY = ["partition", "offset"]

type Writer = Callable[
    [list[str], list[list[str | None]]], Awaitable[RowsInserted | ValuesRejected]
]


class _ReadsOn:
    """What both kinds share: the reading, the bookmark and the sentence."""

    name: PasteKindName
    title: str
    workflow: PasteWorkflow
    destination_requires: Access
    makes: bool
    doing = N_("Adding new messages")
    done = N_("added")
    needs = N_("Tick a topic, a stream, a queue, or a symbol's trades or candles")
    mode: ClipboardMode = "copy"
    converts = True
    can_replace = False
    source_requires: Access = "read"
    # The reader's bookmark moves, and no message changes.
    changes_source = False
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
        # A queue's page is its bindings; what is read of it is messages (D336).
        if isinstance(source, SupportsMovingColumns):
            moving = await moving_columns_of(source, end, None)
            if moving is not None:
                return moving
        return await columns_of(source, [end])

    def _source_checked(
        self, source: DataAdapter, destination: DataAdapter, request: PasteRun
    ) -> None:
        if not self.serves(source, destination):
            raise ActionRefused(
                "not_applicable", say("These connections cannot move rows")
            )
        if len(request.source_node_ids) != 1 or request.reader is None:
            raise ActionRefused("not_applicable", say(NOT_READ_ON))
        if not request.columns:
            raise ActionRefused("not_applicable", say("Pair at least one column"))

    def serves(self, source: DataAdapter, destination: DataAdapter) -> bool:
        raise NotImplementedError

    async def _writer(
        self,
        source: SupportsReadingOn,
        destination: DataAdapter,
        transfer: Transfer,
        fresh: bool,
        start: Bookmark,
    ) -> Writer:
        """Where the blocks go, the table made or found first where it must be."""
        raise NotImplementedError

    async def transfer(
        self,
        source: DataAdapter,
        destination: DataAdapter,
        transfer: Transfer,
        report: TransferReport,
    ) -> None:
        item = transfer.items[0]
        item.outcome = "running"
        item.rows = 0
        transfer.current = item.name
        try:
            await self._carry(source, destination, transfer, report)
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
        transfer.current = None
        transfer.published += 1

    async def _carry(
        self,
        source: DataAdapter,
        destination: DataAdapter,
        transfer: Transfer,
        report: TransferReport,
    ) -> None:
        if not isinstance(source, SupportsReadingOn) or transfer.reader is None:
            raise TransferStopped(say(NOT_ROWS))
        await self._read_on(source, destination, transfer, report)

    def _reading(self, transfer: Transfer) -> list[PasteColumn]:
        """What is read of each row, and what each becomes."""
        return transfer.columns or []

    async def _read_on(
        self,
        source: SupportsReadingOn,
        destination: DataAdapter,
        transfer: Transfer,
        report: TransferReport,
    ) -> None:
        item = transfer.items[0]
        node, reader = item.node_id, transfer.reader or ""
        span = await source.unread(node, reader, transfer.start or "earliest")
        item.skipped = span.lost
        transfer.fresh = span.fresh
        write = await self._writer(
            source, destination, transfer, span.fresh, span.start
        )
        await report.progressed()
        pairs = self._reading(transfer)
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
                # What arrived: a block written twice and keyed counts once.
                done += result.inserted
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
        name = item.published_as or item.name
        if stopped is not None:
            if rows == 0:
                return stopped
            # What arrived before stays, its bookmark kept.
            return say(
                "{count} new messages added to {name}, then: {reason}",
                count=rows,
                name=name,
                reason=stopped,
            )
        if rows == 0:
            said = say("Nothing new since the last run")
        else:
            said = say("{count} new messages added to {name}", count=rows, name=name)
        if transfer.made_table:
            said = (
                say(
                    "{said}; the table was made with a key on partition and offset, so each message is kept once",
                    said=said,
                )
                if transfer.keyed and transfer.key in ([], MESSAGE_KEY)
                else say(
                    "{said}; the table was made with a key on {columns}, so each row is kept once",
                    said=said,
                    columns=", ".join(transfer.key),
                )
                if transfer.keyed
                else say("{said}; the table was made", said=said)
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


class RowsSinceLast(_ReadsOn):
    """Into a table that is there: at least once, whatever keys it has."""

    name: PasteKindName = "rows_since_last"
    title = N_("Add new messages to a table")
    workflow: PasteWorkflow = "into-relation"
    destination_requires: Access = "write"
    makes = False

    def serves(self, source: DataAdapter, destination: DataAdapter) -> bool:
        return (
            self.takes_from(source)
            and isinstance(destination, SupportsInsert)
            and isinstance(destination, SupportsFetch)
            and not isinstance(destination, TransfersFiles)
        )

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

    async def plan(
        self, source: DataAdapter, destination: DataAdapter, request: PasteRun
    ) -> TransferPlan:
        self._source_checked(source, destination, request)
        if request.target_node_id is None:
            raise ActionRefused(
                "not_applicable", say("Tick the table the rows go into")
            )
        target = request.target_node_id
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

    async def _writer(
        self,
        source: SupportsReadingOn,
        destination: DataAdapter,
        transfer: Transfer,
        fresh: bool,
        start: Bookmark,
    ) -> Writer:
        del source, fresh, start
        if (
            not isinstance(destination, SupportsInsert)
            or transfer.target_node_id is None
        ):
            raise TransferStopped(say("This connection cannot take rows"))
        return imports.into_relation(destination, transfer.target_node_id)


class RowsSinceLastNew(_ReadsOn):
    """Into a table the link makes on its first run and adds to after (D313)."""

    name: PasteKindName = "rows_since_last_new"
    title = N_("Add new messages to a new table")
    workflow: PasteWorkflow = "new-relation"
    # What D45 asks of the place a table is made in.
    destination_requires: Access = "structure"
    makes = True

    def serves(self, source: DataAdapter, destination: DataAdapter) -> bool:
        return (
            self.takes_from(source)
            and isinstance(destination, SupportsCreateRelation)
            and isinstance(destination, SupportsInsert)
            and isinstance(destination, SupportsCatalog)
            and not isinstance(destination, TransfersFiles)
        )

    async def offer(
        self, source: DataAdapter, destination: DataAdapter, pair: PastePair
    ) -> PasteOffer:
        if len(pair.source_node_ids) != 1:
            return refused(self, say("Paste one table at a time"))
        columns = await self._source_columns(source, pair.source_node_ids[0])
        if isinstance(columns, str):
            return refused(self, columns)
        return await new_table(self, destination, pair.destination_node_id, columns)

    def made(
        self, source: Foreseen, name: str | None, columns: list[PasteColumn] | None
    ) -> Foreseen | None:
        del source  # the table is what its window chose
        return made_table(name, columns)

    async def foresee(
        self,
        source: DataAdapter,
        destination: DataAdapter,
        source_end: PairEnd,
        target_end: PairEnd,
    ) -> PasteOffer:
        if isinstance(target_end, Foreseen):
            return refused(self, say("Choose the schema the table goes in"))
        columns = await self._source_columns(source, source_end)
        if isinstance(columns, str):
            return refused(self, columns)
        return await new_table(self, destination, target_end, columns)

    async def plan(
        self, source: DataAdapter, destination: DataAdapter, request: PasteRun
    ) -> TransferPlan:
        self._source_checked(source, destination, request)
        if request.name is None or not request.name.strip():
            raise ActionRefused(
                "not_applicable", say("Name the table and choose its columns")
            )
        if any(column.type_code is None for column in request.columns or []):
            raise ActionRefused("not_applicable", say("Choose a type for every column"))
        name = request.name.strip()
        return TransferPlan(
            items=[TransferItem(node_id=request.source_node_ids[0], name=name)],
            bytes_total=None,
            place="",
            name=name,
            columns=request.columns,
            reader=request.reader,
            start=request.start,
        )

    async def _writer(
        self,
        source: SupportsReadingOn,
        destination: DataAdapter,
        transfer: Transfer,
        fresh: bool,
        start: Bookmark,
    ) -> Writer:
        if not isinstance(destination, SupportsCreateRelation) or not isinstance(
            destination, SupportsInsert
        ):
            raise TransferStopped(say("This connection cannot create tables"))
        item = transfer.items[0]
        name = transfer.name or item.name
        place = transfer.destination_node_id or ""
        found = await _table_named(destination, place, name)
        pairs = transfer.columns or []
        if fresh:
            # No bookmark: the first run, or the source forgot it. The table
            # is made now, and a name taken is somebody else's table.
            if found is not None:
                raise TransferStopped(
                    say("A table named {name} is already there", name=name)
                )
            table = await self._made(source, destination, transfer, place, name, start)
            transfer.made_table = True
        else:
            if found is None:
                # Made again it would hold only what came after, under a name
                # that claims all of it.
                raise TransferStopped(
                    say(
                        "{name} is no longer there; to read everything again, "
                        "draw the link again",
                        name=name,
                    )
                )
            table = found
        item.published_id, item.published_as = table.id, table.name
        if (
            isinstance(destination, SupportsSkippingInsert)
            and _keyed_by(pairs, source.row_key(item.node_id)) is not None
        ):
            return _skipping(destination, table.id)
        return imports.into_relation(destination, table.id)

    async def _made(
        self,
        source: SupportsReadingOn,
        destination: SupportsCreateRelation,
        transfer: Transfer,
        place: str,
        name: str,
        start: Bookmark,
    ) -> CatalogNode:
        pairs = transfer.columns or []
        made = await destination.create_relation(
            CreateRelationRequest(
                parent_node_id=place,
                name=name,
                columns=[
                    NewColumn(name=pair.target, type_code=pair.type_code or "")
                    for pair in pairs
                ],
            )
        )
        if isinstance(made, ValuesRejected):
            raise TransferStopped(say("The table could not be made"))
        try:
            named_by = source.row_key(transfer.items[0].node_id)
            key = _keyed_by(pairs, named_by)
            if (
                key is not None
                and isinstance(destination, SupportsConstraints)
                and isinstance(destination, SupportsSkippingInsert)
            ):
                await destination.create_constraint(
                    CreateConstraintRequest(
                        node_id=made.node.id,
                        constraint=UniqueConstraintSpec(columns=list(key)),
                    )
                )
                transfer.keyed = True
                transfer.key = named_by
            # Kept at once: a failure later in this run then leaves a bookmark,
            # and the next run adds to this table instead of meeting its own
            # name taken.
            await source.mark_read(
                transfer.items[0].node_id, transfer.reader or "", start
            )
        except asyncio.CancelledError, Exception:
            if isinstance(destination, SupportsDropCreated):
                await asyncio.shield(destination.drop_created(made.node.id))
            raise
        return made.node


def _keyed_by(pairs: list[PasteColumn], named_by: list[str]) -> list[str] | None:
    """The table's columns holding what names a row of the source, if all are
    paired."""
    targets = {pair.source: pair.target for pair in pairs}
    if named_by and all(column in targets for column in named_by):
        return [targets[column] for column in named_by]
    return None


def _skipping(destination: SupportsSkippingInsert, node_id: str) -> Writer:
    async def write(
        columns: list[str], rows: list[list[str | None]]
    ) -> RowsInserted | ValuesRejected:
        return await destination.insert_rows_skipping(
            InsertRowsRequest(node_id=node_id, columns=columns, rows=rows)
        )

    return write


async def _table_named(
    destination: DataAdapter, place: str, name: str
) -> CatalogNode | None:
    """The node called `name` in the place, if there is one: a table, or what
    the source makes in its stead."""
    if not isinstance(destination, SupportsCatalog):
        return None
    children = await destination.list_children(place or None)
    return next((node for node in children if node.name == name), None)


class RowsByKey(_ReadsOn):
    """Each row kept as a key of its own, replacing it (D314).

    From any source of rows: a key written twice is the same key, so a table
    read whole at every run is a fair source. From a node read on, only what
    is new is read.
    """

    name: PasteKindName = "rows_by_key"
    title = N_("Keep the latest per key")
    doing = N_("Keeping the latest per key")
    done = N_("written")
    needs = N_("Tick something readable as rows")
    workflow: PasteWorkflow = "keyed"
    destination_requires: Access = "write"
    makes = False

    def takes_from(self, source: DataAdapter) -> bool:
        return isinstance(source, SupportsFetch)

    def serves(self, source: DataAdapter, destination: DataAdapter) -> bool:
        return self.takes_from(source) and isinstance(destination, SupportsKeyedWrite)

    async def _columns(
        self, source: DataAdapter, end: PairEnd
    ) -> list[FetchColumn] | str:
        if isinstance(end, Foreseen):
            return end.columns or say(NOT_ROWS)
        if end is None:
            return say(self.needs)
        return await columns_of(source, [end])

    def _place(self, destination: DataAdapter, place: PairEnd) -> str | None:
        if isinstance(place, Foreseen) or not isinstance(
            destination, SupportsKeyedWrite
        ):
            return None
        return destination.keyed_prefix(place)

    async def offer(
        self, source: DataAdapter, destination: DataAdapter, pair: PastePair
    ) -> PasteOffer:
        if len(pair.source_node_ids) != 1:
            return refused(self, say("Paste one table at a time"))
        return await self._offered(
            source, destination, pair.source_node_ids[0], pair.destination_node_id
        )

    async def foresee(
        self,
        source: DataAdapter,
        destination: DataAdapter,
        source_end: PairEnd,
        target_end: PairEnd,
    ) -> PasteOffer:
        return await self._offered(source, destination, source_end, target_end)

    async def _offered(
        self,
        source: DataAdapter,
        destination: DataAdapter,
        source_end: PairEnd,
        place: PairEnd,
    ) -> PasteOffer:
        prefix = self._place(destination, place)
        if prefix is None:
            return refused(self, say("Draw it to a database or a folder"))
        columns = await self._columns(source, source_end)
        if isinstance(columns, str):
            return refused(self, columns)
        return offered(
            self, available=True, source_columns=columns, suggested_name=prefix
        )

    def made(
        self, source: Foreseen, name: str | None, columns: list[PasteColumn] | None
    ) -> Foreseen | None:
        del source, name, columns
        return None

    async def plan(
        self, source: DataAdapter, destination: DataAdapter, request: PasteRun
    ) -> TransferPlan:
        if not self.serves(source, destination):
            raise ActionRefused(
                "not_applicable", say("These connections cannot move rows")
            )
        if len(request.source_node_ids) != 1:
            raise ActionRefused("not_applicable", say("Paste one table at a time"))
        if request.by_key is None or not request.columns:
            raise ActionRefused("not_applicable", say("Choose the key and the values"))
        if self._place(destination, request.destination_node_id) is None:
            raise ActionRefused(
                "not_applicable", say("Draw it to a database or a folder")
            )
        return TransferPlan(
            items=[
                TransferItem(
                    node_id=request.source_node_ids[0],
                    name=request.by_key.prefix[:255] or "",
                )
            ],
            bytes_total=None,
            place="",
            columns=request.columns,
            reader=request.reader,
            start=request.start,
            by_key=request.by_key,
        )

    def _reading(self, transfer: Transfer) -> list[PasteColumn]:
        choice = transfer.by_key
        key = (
            []
            if choice is None
            else [PasteColumn(source=choice.key_column, target=KEY_TARGET)]
        )
        return [*key, *(transfer.columns or [])]

    async def _carry(
        self,
        source: DataAdapter,
        destination: DataAdapter,
        transfer: Transfer,
        report: TransferReport,
    ) -> None:
        node = transfer.items[0].node_id
        if (
            isinstance(source, SupportsReadingOn)
            and transfer.reader is not None
            and source.reads_on(node)
        ):
            await self._read_on(source, destination, transfer, report)
            return
        if not isinstance(source, SupportsFetch):
            raise TransferStopped(say(NOT_ROWS))
        # A source read whole: every run writes what it holds now.
        write = await self._writer(source, destination, transfer, False, Bookmark())
        item = transfer.items[0]

        async def arrived(count: int) -> None:
            item.rows = count
            await report.progressed()

        pairs = [
            imports.ColumnPair(source=pair.source, target=pair.target)
            for pair in self._reading(transfer)
        ]
        await imports.carry_rows(source, node, pairs, write, arrived)

    async def _writer(
        self,
        source: SupportsReadingOn | DataAdapter,
        destination: DataAdapter,
        transfer: Transfer,
        fresh: bool,
        start: Bookmark,
    ) -> Writer:
        del source, fresh, start
        choice = transfer.by_key
        if not isinstance(destination, SupportsKeyedWrite) or choice is None:
            raise TransferStopped(say("This connection cannot keep rows as keys"))
        fields = [pair.target for pair in transfer.columns or []]
        place = transfer.destination_node_id or ""

        async def write(
            columns: list[str], rows: list[list[str | None]]
        ) -> RowsInserted | ValuesRejected:
            del columns  # the key first, then the values in the order of `fields`
            answer = await destination.write_keyed(
                KeyedWriteRequest(
                    place_node_id=place,
                    prefix=choice.prefix,
                    fields=fields,
                    rows=[KeyedRow(key=row[0], values=row[1:]) for row in rows],
                    ttl_seconds=choice.ttl_seconds,
                )
            )
            transfer.keys_written += answer.written
            transfer.without_key += answer.without_key
            transfer.other_type += answer.other_type
            # Rows read, which the step counts; what became of them is above.
            return RowsInserted(inserted=len(rows))

        return write

    def told(self, transfer: Transfer, stopped: str | None = None) -> str:
        item = transfer.items[0]
        rows = item.rows or 0
        if stopped is not None:
            if rows == 0:
                return stopped
            return say("{count} rows read, then: {reason}", count=rows, reason=stopped)
        prefix = transfer.by_key.prefix if transfer.by_key is not None else ""
        if rows == 0:
            said = (
                say("Nothing new since the last run")
                if transfer.reader
                else say("No rows to write")
            )
        elif prefix:
            said = say(
                "{rows} rows: {keys} keys written under {prefix}",
                rows=rows,
                keys=transfer.keys_written,
                prefix=prefix,
            )
        else:
            said = say(
                "{rows} rows: {keys} keys written",
                rows=rows,
                keys=transfer.keys_written,
            )
        if transfer.without_key:
            said = say(
                "{said}; {count} rows without a key or a value skipped",
                said=said,
                count=transfer.without_key,
            )
        if transfer.other_type:
            said = say(
                "{said}; {count} keys of another type left as they were",
                said=said,
                count=transfer.other_type,
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


# The name the key column is read under; never a field of what is written.
KEY_TARGET = "\x00key"
