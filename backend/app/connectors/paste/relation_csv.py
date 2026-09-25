"""A table pasted into a folder becomes a CSV file (D165)."""

from collections.abc import AsyncIterator
from contextlib import ExitStack
from functools import partial

from anyio import to_thread

from app.adapters.actions import ActionRefused
from app.adapters.explorer.storage import Place, Storage, is_plain_name
from app.adapters.export import ExportBatch, ExportRequest
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
    PasteResult,
    PasteRun,
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
    mode: ClipboardMode = "copy"
    converts = True
    # Allowed, unlike a move's (D163): the source is not a file, so the file
    # replaced cannot be the source itself.
    can_replace = True
    source_requires: Access = "read"
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

    async def run(
        self, source: DataAdapter, destination: DataAdapter, request: PasteRun
    ) -> PasteResult:
        if not isinstance(source, SupportsExport):
            raise ActionRefused("not_applicable", "This connection cannot export rows")
        found = await _relation(source, request.source_node_ids, gone=GONE)
        if isinstance(found, str):
            raise ActionRefused("not_applicable", found)
        columns = [column.name for column in found.columns]
        if not columns:
            raise ActionRefused("not_applicable", "The table has no columns")
        name = csv_name(request.name or suggested_name(found.name))
        storage = storage_of(destination)
        target = await to_thread.run_sync(
            _target, storage, request.destination_node_id, name, request.conflict
        )
        rows = await _write(
            storage,
            target,
            columns,
            source.export_rows(
                ExportRequest(node_id=request.source_node_ids[0], columns=columns)
            ),
            replace=request.conflict == "replace",
        )
        return PasteResult(
            kind=self.name,
            message=f"{target.name} saved with {counted(rows, 'row')}",
            written=1,
            rows=rows,
            name=target.name,
            reload_node_ids=[request.destination_node_id],
        )


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


async def _write(
    storage: Storage,
    target: Place,
    columns: list[str],
    batches: AsyncIterator[ExportBatch],
    *,
    replace: bool,
) -> int:
    """Stream the rows into a staged file and publish it only when complete."""
    staging = ExitStack()
    try:
        staged = await to_thread.run_sync(staging.enter_context, storage.staged(target))
        try:
            rows = await downloads.write_csv(
                staged, columns=columns, batches=batches, max_bytes=MAX_TRANSFER_BYTES
            )
        except downloads.CsvTooLarge:
            raise ActionRefused("too_large", "The table exceeds 200 MB as CSV") from None
        await to_thread.run_sync(partial(storage.publish, staged, target, replace=replace))
    except FileExistsError:
        raise ActionRefused("conflict", f"{target.name} is already there") from None
    except OSError:
        raise ActionRefused("not_applicable", "The file could not be saved") from None
    finally:
        await to_thread.run_sync(staging.close)
    return rows
