"""A table pasted into a folder becomes a CSV file (D165, D168)."""

import asyncio
from contextlib import ExitStack
from functools import partial

from anyio import to_thread

from app.adapters.actions import ActionRefused
from app.adapters.explorer.storage import Place, Storage, is_plain_name
from app.adapters.export import ExportRequest
from app.adapters.protocol import (
    AdapterError,
    DataAdapter,
    NodeNotFound,
    SupportsExport,
    SupportsRelationModel,
)
from app.adapters.relation import RelationModel
from app.connectors import downloads
from app.connectors.paste.files import (
    MAX_TRANSFER_BYTES,
    TransfersFiles,
    destination_folder,
    place_for,
    storage_of,
)
from app.connectors.paste.kinds import counted, offered, refused
from app.connectors.paste.models import (
    Availability,
    ClipboardMode,
    Conflict,
    PasteKindName,
    PasteOffer,
    PastePair,
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

NOT_A_RELATION = "Copy a table or a view"
GONE = "The copied table no longer exists"


def suggested_name(relation: str) -> str:
    return f"{downloads.safe_stem(relation)}.csv"


def csv_name(typed: str) -> str:
    """The name typed, ending in `.csv`.

    Not D45's rule, which keeps any delimited extension: a `.tsv` holding
    commas would be read back as one column.
    """
    name = typed.strip()
    if not is_plain_name(name):
        raise ActionRefused(
            "not_applicable", "A name must be a single plain name, without separators"
        )
    return name if name.lower().endswith(".csv") else f"{name}.csv"


class RelationCsv:
    name: PasteKindName = "relation_csv"
    title = "Save as CSV"
    needs = "Tick a table or a view"
    doing = "Saving as CSV"
    done = "saved"
    mode: ClipboardMode = "copy"
    workflow: PasteWorkflow = "file-name"
    converts = True
    # Allowed, unlike a move's (D163): the source is not a file, so the file
    # replaced cannot be the source itself.
    can_replace = True
    source_requires: Access = "read"
    destination_requires: Access = "write"
    changes_source = False

    def takes_from(self, source: DataAdapter) -> bool:
        return isinstance(source, SupportsExport) and isinstance(
            source, SupportsRelationModel
        )

    def serves(self, source: DataAdapter, destination: DataAdapter) -> bool:
        return self.takes_from(source) and isinstance(destination, TransfersFiles)

    async def supply(self, source: DataAdapter, node_ids: list[str]) -> Availability:
        # The selection is on screen, so a node the source cannot describe is
        # one that is not a relation rather than one that went away.
        found = await _relation(source, node_ids, gone=NOT_A_RELATION)
        if isinstance(found, str):
            return Availability(available=False, reason=found)
        return Availability(available=True)

    async def offer(
        self, source: DataAdapter, destination: DataAdapter, pair: PastePair
    ) -> PasteOffer:
        found = await _relation(source, pair.source_node_ids, gone=GONE)
        if isinstance(found, str):
            return refused(self, found)
        name = suggested_name(found.name)
        try:
            taken = await to_thread.run_sync(
                _taken, storage_of(destination), pair.destination_node_id, name
            )
        except ActionRefused as refusal:
            return refused(self, refusal.message)
        except (OSError, ValueError):
            return refused(self, "The destination is unavailable")
        return offered(self, available=True, name_conflict=taken, suggested_name=name)

    async def plan(
        self, source: DataAdapter, destination: DataAdapter, request: PasteRun
    ) -> TransferPlan:
        found = await _relation(source, request.source_node_ids, gone=GONE)
        if isinstance(found, str):
            raise ActionRefused("not_applicable", found)
        if not found.columns:
            raise ActionRefused("not_applicable", "The table has no columns")
        name = csv_name(request.name or suggested_name(found.name))
        storage = storage_of(destination)
        try:
            target = await to_thread.run_sync(
                _target, storage, request.destination_node_id, name, request.conflict
            )
        except (OSError, ValueError):
            raise ActionRefused("not_applicable", "The destination is unavailable") from None
        folder = storage.parent(target)
        return TransferPlan(
            items=[TransferItem(node_id=request.source_node_ids[0], name=found.name)],
            bytes_total=None,
            place=folder.name,
            name=name,
        )

    async def transfer(
        self,
        source: DataAdapter,
        destination: DataAdapter,
        transfer: Transfer,
        report: TransferReport,
    ) -> None:
        item = transfer.items[0]
        item.outcome = "running"
        transfer.current = item.name
        await report.progressed()
        try:
            await _saved(source, storage_of(destination), transfer, item, report)
        except asyncio.CancelledError:
            item.outcome = "stopped"
            item.message = f"{transfer.name} was stopped while it was being written; no file was left"
            raise
        except ActionRefused as refusal:
            item.outcome, item.message = "failed", refusal.message
        except AdapterError as failure:
            item.outcome, item.message = "failed", failure.message
            item.failed = 1
            raise TransferStopped(failure.message) from None
        except FileExistsError:
            item.outcome, item.message = "failed", f"{transfer.name} is already there"
        except (OSError, ValueError):
            item.outcome, item.message = "failed", "The file could not be written"
        if item.outcome == "failed":
            item.failed = 1
        transfer.current = None

    def told(self, transfer: Transfer, stopped: str | None = None) -> str:
        item = transfer.items[0]
        if item.outcome == "done":
            return (
                f"{item.published_as} saved in {transfer.place_label} "
                f"with {counted(item.rows or 0, 'row')}"
            )
        if item.outcome == "stopped":
            return f"{transfer.name} was not saved: it was stopped"
        return f"{transfer.name} was not saved: {stopped or item.message or 'it failed'}"


async def _relation(
    source: DataAdapter, node_ids: list[str], *, gone: str
) -> RelationModel | str:
    """The one relation on the clipboard, or why there is none."""
    if not isinstance(source, SupportsRelationModel):
        return NOT_A_RELATION
    if len(node_ids) != 1:
        return "Copy one table at a time"
    try:
        return await source.relation_model(node_ids[0])
    except NodeNotFound:
        return gone
    except ValueError:
        return NOT_A_RELATION
    except AdapterError:
        return "The copied connection is unavailable"


def _taken(storage: Storage, folder_id: str | None, name: str) -> bool:
    folder = destination_folder(storage, folder_id)
    return storage.entry(storage.child(folder, name)) is not None


def _target(
    storage: Storage, folder_id: str | None, name: str, conflict: Conflict
) -> Place:
    return place_for(storage, destination_folder(storage, folder_id), name, conflict)


async def _saved(
    source: DataAdapter,
    storage: Storage,
    transfer: Transfer,
    item: TransferItem,
    report: TransferReport,
) -> None:
    """Stream the rows into the file where it is going; publish it only whole."""
    if not isinstance(source, SupportsExport):
        raise ActionRefused("not_applicable", "This connection cannot export rows")
    found = await _relation(source, [item.node_id], gone=GONE)
    if isinstance(found, str):
        raise ActionRefused("not_applicable", found)
    columns = [column.name for column in found.columns]
    if not columns:
        raise ActionRefused("not_applicable", "The table has no columns")
    target = await report.in_thread(
        partial(
            _target,
            storage,
            transfer.destination_node_id,
            transfer.name or suggested_name(found.name),
            transfer.conflict,
        )
    )
    batches = source.export_rows(ExportRequest(node_id=item.node_id, columns=columns))
    pieces = downloads.csv_pieces(columns, batches)
    stack = ExitStack()
    try:
        arriving = await report.in_thread(partial(stack.enter_context, storage.incoming(target)))
        rows = 0
        async for piece, count in pieces:
            if transfer.bytes_done + len(piece) > MAX_TRANSFER_BYTES:
                raise ActionRefused("too_large", "The table exceeds 10 GB as CSV")
            await report.in_thread(partial(arriving.write, piece))
            transfer.bytes_done += len(piece)
            rows += count
            item.rows = rows
            await report.progressed()
        await report.in_thread(
            partial(arriving.publish, target, replace=transfer.conflict == "replace")
        )
    finally:
        await downloads.close_pieces(pieces, batches)
        await report.in_thread(stack.close)
    transfer.published += 1
    item.published_as = target.name
    item.arrived = 1
    item.outcome = "done"
