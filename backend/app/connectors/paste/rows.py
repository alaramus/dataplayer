"""Rows pasted into another connection: a new table, or into a ticked one (D166).

What runs is D43's and D45's own work, from `imports`: the same bounded read,
the same check of every value, the same transaction.
"""

import asyncio

from app.adapters.actions import ActionRefused
from app.adapters.catalog import CatalogNode
from app.adapters.fetch import FetchColumn, FetchRequest
from app.adapters.protocol import (
    AdapterError,
    DataAdapter,
    NodeNotFound,
    SupportsCreateRelation,
    SupportsDropCreated,
    SupportsFetch,
    SupportsInsert,
    SupportsNodePath,
)
from app.adapters.relation import ColumnType
from app.adapters.update import ValuesRejected
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
    PasteResult,
    PasteRun,
    PasteWorkflow,
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

NOT_ROWS = N_("This cannot be read as rows")


async def columns_of(source: DataAdapter, node_ids: list[str]) -> list[FetchColumn] | str:
    """The columns of the one node on the clipboard, or why it has none."""
    if not isinstance(source, SupportsFetch):
        return say(NOT_ROWS)
    if len(node_ids) != 1:
        return say("Paste one table at a time")
    return await _columns(source, node_ids[0], gone=N_("The copied node no longer exists"))


async def _columns(source: SupportsFetch, node_id: str, *, gone: str) -> list[FetchColumn] | str:
    try:
        page = await source.fetch(FetchRequest(node_id=node_id, limit=1))
    except NodeNotFound:
        return say(gone)
    except ValueError:
        return say(NOT_ROWS)
    except AdapterError:
        return say("The connection is unavailable")
    return page.columns or say(NOT_ROWS)


def rejected(result: ValuesRejected) -> str:
    """The first value that could not cross, and how many more there are."""
    first = result.cells[0]
    more = len(result.cells) - 1
    found = {"value": repr(first.value), "column": first.column, "row": first.row + 1}
    if more == 0:
        return say("{value} cannot be read by {column} (row {row})", **found)
    if more == 1:
        return say(
            "{value} cannot be read by {column} (row {row}), and {count} other value",
            count=more,
            **found,
        )
    return say(
        "{value} cannot be read by {column} (row {row}), and {count} other values",
        count=more,
        **found,
    )


class _Rows:
    """A folder is not a destination: it takes a file as it is (D161) or a
    table as CSV (D165), and a second answer beside those would be a second
    meaning for the same Paste."""

    name: PasteKindName
    title: str
    workflow: PasteWorkflow
    needs = N_("Tick a file or a table readable as rows")
    destination_requires: Access
    mode: ClipboardMode = "copy"
    converts = True
    can_replace = False
    source_requires: Access = "read"
    changes_source = False
    pipelines = True
    outranks: tuple[PasteKindName, ...] = ()

    def takes_from(self, source: DataAdapter) -> bool:
        return isinstance(source, SupportsFetch)

    async def too_large_for_request(self, source: DataAdapter, request: PasteRun) -> bool:
        if not isinstance(source, SupportsFetch) or len(request.source_node_ids) != 1:
            return False
        return await imports.exceeds_ceiling(source, request.source_node_ids[0])

    def _pairs(self, transfer: Transfer) -> list[imports.ColumnPair]:
        return [
            imports.ColumnPair(source=column.source, target=column.target)
            for column in transfer.columns or []
        ]

    async def _carried(
        self,
        source: DataAdapter,
        transfer: Transfer,
        report: TransferReport,
        write: imports.BlockWriter,
    ) -> int:
        """The rows carried, the item kept up to date as blocks arrive."""
        if not isinstance(source, SupportsFetch):
            raise TransferStopped(say(NOT_ROWS))
        item = transfer.items[0]

        async def arrived(count: int) -> None:
            item.rows = count
            await report.progressed()

        item.outcome = "running"
        item.rows = 0
        transfer.current = item.name
        await report.progressed()
        return await imports.carry_rows(source, item.node_id, self._pairs(transfer), write, arrived)

    def _takes_rows(self, destination: DataAdapter) -> bool:
        return not isinstance(destination, TransfersFiles)

    async def supply(self, source: DataAdapter, node_ids: list[str]) -> Availability:
        found = await columns_of(source, node_ids)
        if isinstance(found, str):
            return Availability(available=False, reason=found)
        return Availability(available=True)

    async def _read_from(self, source: DataAdapter, end: PairEnd) -> list[FetchColumn] | str:
        """The columns rows are read by, from a node or from what a link makes."""
        if isinstance(end, Foreseen):
            return end.columns or say(NOT_ROWS)
        if end is None:
            return say(self.needs)
        return await columns_of(source, [end])


class RowsNewRelation(_Rows):
    name: PasteKindName = "rows_new_relation"
    title = N_("Create a table")
    doing = N_("Filling a new table")
    done = N_("created")
    workflow: PasteWorkflow = "new-relation"
    # What D45 asks of the place the table is made in.
    destination_requires: Access = "structure"
    makes = True

    def serves(self, source: DataAdapter, destination: DataAdapter) -> bool:
        return (
            self.takes_from(source)
            and isinstance(destination, SupportsCreateRelation)
            and self._takes_rows(destination)
        )

    async def offer(
        self, source: DataAdapter, destination: DataAdapter, pair: PastePair
    ) -> PasteOffer:
        columns = await columns_of(source, pair.source_node_ids)
        if isinstance(columns, str):
            return refused(self, columns)
        return await self._into(destination, pair.destination_node_id, columns)

    def made(
        self, source: Foreseen, name: str | None, columns: list[PasteColumn] | None
    ) -> Foreseen | None:
        del source  # the table is what its window chose, whatever it was made from
        return Foreseen(
            kind="table",
            name=name or say("a new table"),
            columns=[
                FetchColumn(
                    name=column.target,
                    type=ColumnType(sql=column.type_code or "text", category="other"),
                    insertable=True,
                )
                for column in columns or []
            ],
        )

    async def foresee(
        self,
        source: DataAdapter,
        destination: DataAdapter,
        source_end: PairEnd,
        target_end: PairEnd,
    ) -> PasteOffer:
        columns = await self._read_from(source, source_end)
        if isinstance(columns, str):
            return refused(self, columns)
        if isinstance(target_end, Foreseen):
            return refused(self, say("Choose the schema the table goes in"))
        return await self._into(destination, target_end, columns)

    async def _into(
        self, destination: DataAdapter, place: str | None, columns: list[FetchColumn]
    ) -> PasteOffer:
        if not isinstance(destination, SupportsCreateRelation):
            return refused(self, say("This connection cannot create tables"))
        try:
            options = await destination.new_relation_options(place or "")
        except (NodeNotFound, ValueError):
            return refused(self, say("Choose the schema the table goes in"))
        except AdapterError:
            return refused(self, say("The connection is unavailable"))
        if not options.supported:
            return refused(self, options.reason or say("This place cannot take a new table"))
        return offered(self, available=True, source_columns=columns)

    def _checked(self, source: DataAdapter, destination: DataAdapter, request: PasteRun) -> str:
        """The table's name, once the request asks for something that can run."""
        if not isinstance(source, SupportsFetch) or not isinstance(
            destination, SupportsCreateRelation
        ):
            raise ActionRefused("not_applicable", say("These connections cannot create a table"))
        if len(request.source_node_ids) != 1:
            raise ActionRefused("not_applicable", say("Paste one table at a time"))
        if request.name is None or not request.columns:
            raise ActionRefused("not_applicable", say("Name the table and choose its columns"))
        if any(column.type_code is None for column in request.columns):
            raise ActionRefused("not_applicable", say("Choose a type for every column"))
        return request.name.strip()

    async def plan(
        self, source: DataAdapter, destination: DataAdapter, request: PasteRun
    ) -> TransferPlan:
        name = self._checked(source, destination, request)
        # Filled a block at a time, so taken back when it cannot be filled.
        if not isinstance(destination, SupportsInsert) or not isinstance(
            destination, SupportsDropCreated
        ):
            raise ActionRefused(
                "too_large",
                say(
                    "A new table may be filled with at most {count} rows",
                    count=imports.IMPORT_CEILING,
                ),
            )
        return TransferPlan(
            items=[TransferItem(node_id=request.source_node_ids[0], name=name)],
            bytes_total=None,
            place="",
            name=name,
            columns=request.columns,
        )

    async def transfer(
        self,
        source: DataAdapter,
        destination: DataAdapter,
        transfer: Transfer,
        report: TransferReport,
    ) -> None:
        if not isinstance(destination, SupportsCreateRelation) or not isinstance(
            destination, SupportsInsert
        ):
            raise TransferStopped(say("This connection cannot create tables"))
        item = transfer.items[0]
        blocks = imports.NewRelationBlocks(
            destination,
            destination,
            imports.CreateRelationFromSourceRequest(
                parent_node_id=transfer.destination_node_id or "",
                name=transfer.name or item.name,
                source_connector_id=str(transfer.source_connector_id),
                source_node_id=item.node_id,
                columns=[
                    imports.NewRelationColumn(
                        source=column.source, target=column.target, type_code=column.type_code or ""
                    )
                    for column in transfer.columns or []
                ],
            ),
        )
        try:
            count = await self._carried(source, transfer, report, blocks.write)
        except (asyncio.CancelledError, Exception) as failure:
            # A table holding part of its source under a name that claims all
            # of it is taken back, whatever ended the filling.
            await _taken_back(destination, blocks.node)
            item.outcome = "stopped" if isinstance(failure, asyncio.CancelledError) else "failed"
            if isinstance(failure, (asyncio.CancelledError, TransferStopped)):
                raise
            raise TransferStopped(_ended(failure)) from None
        if blocks.node is None:
            # An empty source still makes its table.
            await blocks.write([column.target for column in transfer.columns or []], [])
        item.outcome = "done"
        item.arrived = 1
        item.rows = count
        item.published_as = blocks.node.name if blocks.node else item.name
        item.published_id = blocks.node.id if blocks.node else None
        transfer.current = None
        transfer.published += 1

    def told(self, transfer: Transfer, stopped: str | None = None) -> str:
        item = transfer.items[0]
        if stopped is not None:
            return say("{name} was not created: {reason}", name=item.name, reason=stopped)
        return say("{name} created with {count} rows", name=item.published_as or item.name, count=item.rows or 0)

    async def run(
        self, source: DataAdapter, destination: DataAdapter, request: PasteRun
    ) -> PasteResult:
        self._checked(source, destination, request)
        if not isinstance(source, SupportsFetch) or not isinstance(destination, SupportsCreateRelation):
            raise ActionRefused("not_applicable", say("These connections cannot create a table"))
        if request.name is None or not request.columns:
            raise ActionRefused("not_applicable", say("Name the table and choose its columns"))
        creation = imports.CreateRelationFromSourceRequest(
            parent_node_id=request.destination_node_id or "",
            name=request.name.strip(),
            source_connector_id=str(request.source_connector_id),
            source_node_id=request.source_node_ids[0],
            columns=[
                imports.NewRelationColumn(
                    source=column.source,
                    target=column.target,
                    type_code=column.type_code or "",
                )
                for column in request.columns
            ],
        )
        try:
            result = await imports.create_from_source(destination, source, creation)
        except imports.SourceTooLarge:
            raise ActionRefused(
                "too_large",
                say(
                    "A new table may be filled with at most {count} rows",
                    count=imports.IMPORT_CEILING,
                ),
            ) from None
        if isinstance(result, ValuesRejected):
            raise ValueError(rejected(result))
        return PasteResult(
            kind=self.name,
            message=(
                say("{name} created with {count} row", name=result.node.name, count=1)
                if result.inserted == 1
                else say(
                    "{name} created with {count} rows",
                    name=result.node.name,
                    count=result.inserted,
                )
            ),
            written=1,
            rows=result.inserted,
            name=result.node.name,
            reload_node_ids=[request.destination_node_id],
            made_node_id=result.node.id,
        )


class RowsIntoRelation(_Rows):
    name: PasteKindName = "rows_into_relation"
    title = N_("Add rows to a table")
    doing = N_("Adding rows")
    done = N_("added")
    workflow: PasteWorkflow = "into-relation"
    # What D43 asks of the relation written.
    destination_requires: Access = "write"
    # The rows go into a table that is there already.
    makes = False

    def serves(self, source: DataAdapter, destination: DataAdapter) -> bool:
        return (
            self.takes_from(source)
            and isinstance(destination, SupportsInsert)
            and isinstance(destination, SupportsFetch)
            and self._takes_rows(destination)
        )

    async def offer(
        self, source: DataAdapter, destination: DataAdapter, pair: PastePair
    ) -> PasteOffer:
        if pair.target_node_id is None:
            return refused(self, say("Tick the table the rows go into"))
        columns = await columns_of(source, pair.source_node_ids)
        if isinstance(columns, str):
            return refused(self, columns)
        return await self._into(destination, pair.target_node_id, columns)

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
        if target_end is None or (isinstance(target_end, Foreseen) and target_end.kind != "table"):
            return refused(self, say("Tick the table the rows go into"))
        columns = await self._read_from(source, source_end)
        if isinstance(columns, str):
            return refused(self, columns)
        return await self._into(destination, target_end, columns)

    async def _into(
        self, destination: DataAdapter, target_end: str | Foreseen, columns: list[FetchColumn]
    ) -> PasteOffer:
        if isinstance(target_end, Foreseen):
            target: list[FetchColumn] | str = target_end.columns
        elif not isinstance(destination, SupportsFetch):
            return refused(self, say("This connection cannot take rows"))
        else:
            target = await _columns(
                destination, target_end, gone=N_("The ticked table no longer exists")
            )
        if isinstance(target, str):
            return refused(self, say("The ticked node cannot take rows"))
        insertable = [column for column in target if column.insertable]
        if not insertable:
            return refused(self, say("The ticked table takes no rows"))
        return offered(
            self, available=True, source_columns=columns, target_columns=insertable
        )

    def _checked(self, source: DataAdapter, destination: DataAdapter, request: PasteRun) -> str:
        """The table the rows go into, once the request can run."""
        if not isinstance(source, SupportsFetch) or not isinstance(
            destination, SupportsInsert
        ):
            raise ActionRefused("not_applicable", say("These connections cannot move rows"))
        if len(request.source_node_ids) != 1:
            raise ActionRefused("not_applicable", say("Paste one table at a time"))
        if request.target_node_id is None:
            raise ActionRefused("not_applicable", say("Tick the table the rows go into"))
        if not request.columns:
            raise ActionRefused("not_applicable", say("Pair at least one column"))
        return request.target_node_id

    async def plan(
        self, source: DataAdapter, destination: DataAdapter, request: PasteRun
    ) -> TransferPlan:
        target = self._checked(source, destination, request)
        return TransferPlan(
            items=[TransferItem(node_id=request.source_node_ids[0], name=await _name_of(destination, target))],
            bytes_total=None,
            place="",
            columns=request.columns,
            target_node_id=target,
        )

    async def transfer(
        self,
        source: DataAdapter,
        destination: DataAdapter,
        transfer: Transfer,
        report: TransferReport,
    ) -> None:
        if not isinstance(destination, SupportsInsert) or transfer.target_node_id is None:
            raise TransferStopped(say("This connection cannot take rows"))
        item = transfer.items[0]
        try:
            count = await self._carried(
                source, transfer, report, imports.into_relation(destination, transfer.target_node_id)
            )
        except asyncio.CancelledError:
            item.outcome = "stopped"
            raise
        except TransferStopped:
            item.outcome = "failed"
            raise
        except Exception as failure:  # noqa: BLE001 — said in the job's sentence, rows kept
            item.outcome = "failed"
            raise TransferStopped(_ended(failure)) from None
        item.outcome = "done"
        item.arrived = 1
        item.rows = count
        item.published_id = transfer.target_node_id
        transfer.current = None
        transfer.published += 1

    def told(self, transfer: Transfer, stopped: str | None = None) -> str:
        item = transfer.items[0]
        rows = item.rows or 0
        if stopped is not None:
            # What arrived before stays: each block was its own transaction.
            return say("{count} rows added to {name}, then: {reason}", count=rows, name=item.name, reason=stopped)
        return say("{count} rows added to {name}", count=rows, name=item.name)

    async def run(
        self, source: DataAdapter, destination: DataAdapter, request: PasteRun
    ) -> PasteResult:
        self._checked(source, destination, request)
        if (
            not isinstance(source, SupportsFetch)
            or not isinstance(destination, SupportsInsert)
            or request.target_node_id is None
            or not request.columns
        ):
            raise ActionRefused("not_applicable", say("These connections cannot move rows"))
        importing = imports.ImportRowsRequest(
            node_id=request.target_node_id,
            source_connector_id=str(request.source_connector_id),
            source_node_id=request.source_node_ids[0],
            columns=[
                imports.ColumnPair(source=column.source, target=column.target)
                for column in request.columns
            ],
        )
        result, truncated = await imports.insert_from_source(
            destination, source, importing
        )
        if isinstance(result, ValuesRejected):
            raise ValueError(rejected(result))
        if truncated:
            message = say(
                "{count} rows added, the first {limit} of the source",
                count=result.inserted,
                limit=imports.IMPORT_CEILING,
            )
        elif result.inserted == 1:
            message = say("{count} row added", count=1)
        else:
            message = say("{count} rows added", count=result.inserted)
        return PasteResult(
            kind=self.name,
            message=message,
            written=result.inserted,
            rows=result.inserted,
            reload_node_ids=[request.destination_node_id],
        )


async def _name_of(destination: DataAdapter, node_id: str) -> str:
    """What a table is called, for the screen that follows the job."""
    if isinstance(destination, SupportsNodePath):
        try:
            return (await destination.path_to(node_id))[-1].name
        except (NodeNotFound, AdapterError, ValueError, IndexError):
            pass
    return node_id


async def _taken_back(destination: DataAdapter, node: CatalogNode | None) -> None:
    if node is not None and isinstance(destination, SupportsDropCreated):
        # Shielded: a Stop is what most often ends the filling, and the drop
        # must not be stopped with it.
        await asyncio.shield(destination.drop_created(node.id))


def _ended(failure: BaseException) -> str:
    """Why the carrying ended, in a sentence that is safe to show."""
    if isinstance(failure, imports.BlockRefused):
        return rejected(failure.rejected)
    if isinstance(failure, NodeNotFound):
        return say("The copied node no longer exists")
    if isinstance(failure, AdapterError):
        return failure.message
    if isinstance(failure, (ValueError, ActionRefused)):
        return str(failure)
    return say("The rows could not be carried")

