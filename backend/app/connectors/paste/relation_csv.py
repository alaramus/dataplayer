"""Tables pasted into a folder become CSV files, one each (D165, D168, D171).

A table is anything its source describes and exports whole: a PostgreSQL
relation, a Redis key, folder or database. One is saved under the name
its window asks for; several go straight to Save, each named after itself.
"""

import asyncio
from contextlib import ExitStack
from functools import partial

from anyio import to_thread

from app.adapters.actions import ActionRefused
from app.adapters.explorer.storage import Place, Storage, is_plain_name, node_id_of
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
    free_place,
    place_for,
    storage_of,
)
from app.connectors.paste.kinds import counted, offered, refused, text_column
from app.connectors.paste.models import (
    Availability,
    ClipboardMode,
    Conflict,
    Foreseen,
    PairEnd,
    PasteColumn,
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
# Each one is described at every change of a tick; a hundred bounds that.
MAX_TABLES = 100
TOO_LARGE = "The tables exceed 10 GB as CSV"


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
    makes = True
    pipelines = True
    outranks: tuple[PasteKindName, ...] = ()

    def takes_from(self, source: DataAdapter) -> bool:
        return isinstance(source, SupportsExport) and isinstance(
            source, SupportsRelationModel
        )

    def serves(self, source: DataAdapter, destination: DataAdapter) -> bool:
        return self.takes_from(source) and isinstance(destination, TransfersFiles)

    async def supply(self, source: DataAdapter, node_ids: list[str]) -> Availability:
        # The selection is on screen, so a node the source cannot describe is
        # one that is not a relation rather than one that went away.
        found = await _relations(source, node_ids, gone=NOT_A_RELATION)
        if isinstance(found, str):
            return Availability(available=False, reason=found)
        return Availability(available=True)

    async def offer(
        self, source: DataAdapter, destination: DataAdapter, pair: PastePair
    ) -> PasteOffer:
        found = await _relations(source, pair.source_node_ids, gone=GONE)
        if isinstance(found, str):
            return refused(self, found)
        names = [suggested_name(model.name) for model in found]
        taken = await _taken_in(destination, pair.destination_node_id, names)
        if isinstance(taken, str):
            return refused(self, taken)
        if len(found) == 1:
            return offered(
                self, available=True, name_conflict=bool(taken), suggested_name=names[0]
            )
        # Several are named after themselves, so no window asks for a name; a
        # taken one asks once, for all of them (D171).
        return offered(
            self,
            available=not taken,
            reason=_already_there(taken),
            name_conflict=bool(taken),
            workflow="run",
        )

    def made(
        self, source: Foreseen, name: str | None, columns: list[PasteColumn] | None
    ) -> Foreseen | None:
        del columns  # every column goes, as the window saves them
        if source.kind != "table":
            return None
        try:
            file = csv_name(name) if name else suggested_name(source.name)
        except ActionRefused:
            file = suggested_name(source.name)
        # Read back, a CSV names what it holds and types none of it.
        return Foreseen(
            kind="file", name=file, columns=[text_column(column.name) for column in source.columns]
        )

    async def foresee(
        self,
        source: DataAdapter,
        destination: DataAdapter,
        source_end: PairEnd,
        target_end: PairEnd,
    ) -> PasteOffer:
        if isinstance(source_end, Foreseen):
            if source_end.kind != "table":
                return refused(self, NOT_A_RELATION)
            relation = source_end.name
        elif source_end is None or not isinstance(source, SupportsRelationModel):
            return refused(self, NOT_A_RELATION)
        else:
            found = await _relation(source, source_end, gone=GONE)
            if isinstance(found, str):
                return refused(self, found)
            relation = found.name
        suggested = suggested_name(relation)
        if isinstance(target_end, Foreseen):
            if target_end.kind != "folder":
                return refused(self, "Choose a destination folder")
            # A folder a link has yet to make holds no name to be taken.
            return offered(self, available=True, suggested_name=suggested)
        taken = await _taken_in(destination, target_end, [suggested])
        if isinstance(taken, str):
            return refused(self, taken)
        return offered(self, available=True, name_conflict=bool(taken), suggested_name=suggested)

    async def plan(
        self, source: DataAdapter, destination: DataAdapter, request: PasteRun
    ) -> TransferPlan:
        found = await _relations(source, request.source_node_ids, gone=GONE)
        if isinstance(found, str):
            raise ActionRefused("not_applicable", found)
        empty = next((model for model in found if not model.columns), None)
        if empty is not None:
            raise ActionRefused("not_applicable", f"{empty.name} has no columns")
        one = len(found) == 1
        names = (
            [csv_name(request.name or suggested_name(found[0].name))]
            if one
            else [suggested_name(model.name) for model in found]
        )
        storage = storage_of(destination)
        try:
            folder = await to_thread.run_sync(
                _checked, storage, request.destination_node_id, names, request.conflict
            )
        except (OSError, ValueError):
            raise ActionRefused("not_applicable", "The destination is unavailable") from None
        return TransferPlan(
            items=[
                TransferItem(node_id=node_id, name=model.name[:255])
                for node_id, model in zip(request.source_node_ids, found, strict=True)
            ],
            bytes_total=None,
            place=folder.name,
            name=names[0] if one else None,
        )

    async def transfer(
        self,
        source: DataAdapter,
        destination: DataAdapter,
        transfer: Transfer,
        report: TransferReport,
    ) -> None:
        """One file after another; one failing does not stop the next."""
        storage = storage_of(destination)
        written: set[str] = set()
        for item in transfer.items:
            item.outcome = "running"
            transfer.current = item.name
            await report.progressed()
            try:
                await _saved(source, storage, transfer, item, report, written)
            except asyncio.CancelledError:
                item.outcome = "stopped"
                item.message = f"{_file_of(transfer, item)} was stopped while it was being written; no file was left"
                raise
            except TransferStopped as stop:
                item.outcome, item.failed = "failed", 1
                item.message = _about(transfer, item, stop.message)
                raise
            except ActionRefused as refusal:
                item.outcome = "failed"
                item.message = _about(transfer, item, refusal.message)
            except AdapterError as failure:
                item.outcome = "failed"
                item.message = _about(transfer, item, failure.message)
            except FileExistsError:
                item.outcome = "failed"
                item.message = f"{_file_of(transfer, item)} is already there"
            except (OSError, ValueError):
                item.outcome = "failed"
                item.message = _about(transfer, item, "The file could not be written")
            if item.outcome == "failed":
                item.failed = 1
            await report.progressed()
        transfer.current = None

    def told(self, transfer: Transfer, stopped: str | None = None) -> str:
        items = transfer.items
        if len(items) == 1:
            item = items[0]
            if item.outcome == "done":
                return (
                    f"{item.published_as} saved in {transfer.place_label} "
                    f"with {counted(item.rows or 0, 'row')}"
                )
            if item.outcome == "stopped":
                return f"{transfer.name} was not saved: it was stopped"
            if item.message is not None:
                return item.message
            return f"{transfer.name} was not saved: {stopped or 'it failed'}"
        saved = sum(1 for item in items if item.outcome == "done")
        where = f"in {transfer.place_label}"
        if saved == len(items):
            return f"{counted(saved, 'file')} saved {where}"
        failed = sum(1 for item in items if item.outcome == "failed")
        halted = any(item.outcome == "stopped" for item in items)
        missing = sum(1 for item in items if item.outcome in ("pending", "running"))
        parts = [
            *([f"{failed} failed"] if failed else []),
            *(["stopped"] if halted else []),
            *([f"{missing} not attempted"] if missing else []),
        ]
        sentence = f"{saved} of {counted(len(items), 'file')} saved {where}"
        if parts:
            sentence += f"; {', '.join(parts)}"
        return sentence if stopped is None else f"{sentence}. {stopped}"


async def _relations(
    source: DataAdapter, node_ids: list[str], *, gone: str
) -> list[RelationModel] | str:
    """Each relation on the clipboard, or why they cannot all be saved."""
    if not isinstance(source, SupportsRelationModel):
        return NOT_A_RELATION
    if len(node_ids) > MAX_TABLES:
        return f"Save at most {MAX_TABLES} tables at a time"
    if len(set(node_ids)) != len(node_ids):
        return "The selection contains a table twice"
    found: list[RelationModel] = []
    for node_id in node_ids:
        one = await _relation(source, node_id, gone=gone)
        if isinstance(one, str):
            return one
        found.append(one)
    return found


async def _relation(
    source: SupportsRelationModel, node_id: str, *, gone: str
) -> RelationModel | str:
    try:
        return await source.relation_model(node_id)
    except NodeNotFound:
        return gone
    except ValueError:
        return NOT_A_RELATION
    except AdapterError:
        return "The copied connection is unavailable"


async def _taken_in(
    destination: DataAdapter, folder_id: str | None, names: list[str]
) -> list[str] | str:
    """Which of these names the folder holds already, or why it cannot say."""
    try:
        return await to_thread.run_sync(_taken, storage_of(destination), folder_id, names)
    except ActionRefused as refusal:
        return refusal.message
    except (OSError, ValueError):
        return "The destination is unavailable"


def _taken(storage: Storage, folder_id: str | None, names: list[str]) -> list[str]:
    folder = destination_folder(storage, folder_id)
    return sorted(
        name for name in set(names) if storage.entry(storage.child(folder, name)) is not None
    )


def _already_there(taken: list[str]) -> str | None:
    if not taken:
        return None
    if len(taken) == 1:
        return f"{taken[0]} is already there"
    return f"{taken[0]} and {counted(len(taken) - 1, 'other file')} are already there"


def _checked(
    storage: Storage, folder_id: str | None, names: list[str], conflict: Conflict
) -> Place:
    """The destination folder, once every name has a place under the conflict rule."""
    folder = destination_folder(storage, folder_id)
    for name in dict.fromkeys(names):
        place_for(storage, folder, name, conflict)
    return folder


def _target(
    storage: Storage,
    folder_id: str | None,
    name: str,
    conflict: Conflict,
    written: set[str],
) -> Place:
    """Where one file goes; a name this transfer already wrote keeps both."""
    folder = destination_folder(storage, folder_id)
    if name in written:
        return free_place(storage, folder, name)
    return place_for(storage, folder, name, conflict)


def _file_of(transfer: Transfer, item: TransferItem) -> str:
    """The file an item is saved as, before it is known what it was published as."""
    if len(transfer.items) == 1 and transfer.name:
        return transfer.name
    return suggested_name(item.name)


def _about(transfer: Transfer, item: TransferItem, reason: str) -> str:
    """Why one file was not saved, in a sentence that names it."""
    return f"{_file_of(transfer, item)} was not saved: {reason[:1].lower()}{reason[1:]}"


async def _saved(
    source: DataAdapter,
    storage: Storage,
    transfer: Transfer,
    item: TransferItem,
    report: TransferReport,
    written: set[str],
) -> None:
    """Stream the rows into the file where it is going; publish it only whole."""
    if not isinstance(source, SupportsExport) or not isinstance(
        source, SupportsRelationModel
    ):
        raise ActionRefused("not_applicable", "This connection cannot export rows")
    found = await _relation(source, item.node_id, gone=GONE)
    if isinstance(found, str):
        raise ActionRefused("not_applicable", found)
    columns = [column.name for column in found.columns]
    if not columns:
        raise ActionRefused("not_applicable", "The table has no columns")
    name = _file_of(transfer, item)
    target = await report.in_thread(
        partial(
            _target,
            storage,
            transfer.destination_node_id,
            name,
            transfer.conflict,
            written,
        )
    )
    batches = source.export_rows(ExportRequest(node_id=item.node_id, columns=columns))
    pieces = downloads.csv_pieces(columns, batches)
    stack = ExitStack()
    try:
        arriving = await report.in_thread(partial(stack.enter_context, storage.incoming(target)))
        rows = 0
        try:
            async for piece, count in pieces:
                if transfer.bytes_done + len(piece) > MAX_TRANSFER_BYTES:
                    raise TransferStopped(TOO_LARGE)
                await report.in_thread(partial(arriving.write, piece))
                transfer.bytes_done += len(piece)
                rows += count
                item.rows = rows
                await report.progressed()
        except ValueError as refusal:
            # What the source refused to read, in its own safe words: a folder
            # of more keys than can be listed, for one (D171).
            raise ActionRefused("not_applicable", str(refusal)) from None
        await report.in_thread(
            partial(arriving.publish, target, replace=transfer.conflict == "replace")
        )
    finally:
        await downloads.close_pieces(pieces, batches)
        await report.in_thread(stack.close)
    written.add(name)
    transfer.published += 1
    item.published_as = target.name
    item.published_id = node_id_of(target)
    item.arrived = 1
    item.outcome = "done"
