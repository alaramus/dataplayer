"""Files copied or moved between explorer connections (D161, D163, D168)."""

import asyncio
from contextlib import ExitStack
from functools import partial
from typing import Protocol, runtime_checkable

from anyio import to_thread

from app.adapters.actions import ActionRefused
from app.adapters.explorer.storage import (
    Entry,
    Place,
    Storage,
    VersionChanged,
    is_plain_name,
)
from app.adapters.protocol import AdapterError, DataAdapter
from app.connectors.paste.kinds import counted, offered
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
    PIECE_BYTES,
    Transfer,
    TransferItem,
    TransferPlan,
    TransferReport,
    TransferStopped,
)
from app.core.access import Access

MAX_TRANSFER_FILES = 1000
MAX_TRANSFER_BYTES = 10 * 1024 * 1024 * 1024
TOO_LARGE = "The selection exceeds 10 GB"


@runtime_checkable
class TransfersFiles(Protocol):
    @property
    def storage(self) -> Storage: ...


def storage_of(adapter: DataAdapter) -> Storage:
    if not isinstance(adapter, TransfersFiles):
        raise ActionRefused("not_applicable", "This connection does not hold files")
    return adapter.storage


def destination_folder(storage: Storage, folder_id: str | None) -> Place:
    place = storage.place(folder_id)
    found = storage.entry(place)
    if found is None or not found.is_directory:
        raise ActionRefused("not_applicable", "Choose a destination folder")
    return place


def place_for(storage: Storage, folder: Place, name: str, conflict: Conflict) -> Place:
    """Where a file of this name lands under a conflict rule, or why it cannot."""
    target = storage.child(folder, name)
    existing = storage.entry(target)
    if existing is None:
        return target
    if existing.is_directory:
        raise ActionRefused("not_applicable", f"{name} is a folder here")
    if conflict == "refuse":
        raise ActionRefused("conflict", f"{name} is already there")
    if conflict == "replace":
        return target
    stem, dot, suffix = name.rpartition(".")
    if not dot:
        stem, suffix = name, ""
    for number in range(1, 10_001):
        candidate = storage.child(
            folder, f"{stem} ({number}){'.' + suffix if suffix else ''}"
        )
        if storage.entry(candidate) is None:
            return candidate
    raise ActionRefused("conflict", "No free file name is available")


def source_files(source: Storage, node_ids: list[str]) -> list[Entry]:
    """The selected files, or why they cannot leave this connection."""
    if len(node_ids) > MAX_TRANSFER_FILES:
        raise ActionRefused(
            "not_applicable", f"Paste at most {MAX_TRANSFER_FILES} files at a time"
        )
    if len(set(node_ids)) != len(node_ids):
        raise ActionRefused("not_applicable", "The selection contains a file twice")
    entries: list[Entry] = []
    names: set[str] = set()
    total = 0
    for node_id in node_ids:
        entry = source.entry(source.place(node_id))
        if entry is None:
            raise ActionRefused("not_applicable", "A copied file no longer exists")
        if entry.is_directory or entry.is_link:
            raise ActionRefused("not_applicable", "Copy files, not folders or links")
        if not is_plain_name(entry.name):
            raise ActionRefused("not_applicable", "A file has an invalid name")
        if entry.name in names:
            raise ActionRefused("not_applicable", "Two files have the same name")
        total += entry.size_bytes
        if total > MAX_TRANSFER_BYTES:
            raise ActionRefused("not_applicable", TOO_LARGE)
        names.add(entry.name)
        entries.append(entry)
    return entries


def checked_files(
    source: Storage,
    destination: Storage,
    node_ids: list[str],
    folder_id: str | None,
    conflict: Conflict,
) -> tuple[list[Entry], Place]:
    """The files and the folder they go into, or why not, without opening a byte."""
    entries = source_files(source, node_ids)
    folder = destination_folder(destination, folder_id)
    for entry in entries:
        place_for(destination, folder, entry.name, conflict)
    return entries, folder


def inspect_files(
    source: Storage,
    destination: Storage,
    node_ids: list[str],
    folder_id: str | None,
    conflict: Conflict = "refuse",
) -> ActionRefused | None:
    """Why the files cannot be pasted now, checked without opening their bytes."""
    try:
        checked_files(source, destination, node_ids, folder_id, conflict)
    except ActionRefused as refusal:
        return refusal
    except (OSError, ValueError):
        return ActionRefused("not_applicable", "A source or destination is unavailable")
    return None


def _planned(source: Storage, destination: Storage, request: PasteRun) -> TransferPlan:
    try:
        entries, folder = checked_files(
            source,
            destination,
            request.source_node_ids,
            request.destination_node_id,
            request.conflict,
        )
    except (OSError, ValueError):
        raise ActionRefused(
            "not_applicable", "A source or destination is unavailable"
        ) from None
    return TransferPlan(
        items=[
            TransferItem(node_id=node_id, name=entry.name, size_bytes=entry.size_bytes)
            for node_id, entry in zip(request.source_node_ids, entries, strict=True)
        ],
        bytes_total=sum(entry.size_bytes for entry in entries),
        place=folder.name,
    )


class _Failed(Exception):
    """This file did not arrive; the next one may."""


class _Files:
    name: PasteKindName
    title: str
    needs: str
    doing: str
    done: str
    mode: ClipboardMode
    can_replace: bool
    source_requires: Access
    changes_source: bool
    converts = False
    workflow: PasteWorkflow = "run"
    destination_requires: Access = "write"

    def takes_from(self, source: DataAdapter) -> bool:
        return isinstance(source, TransfersFiles)

    def serves(self, source: DataAdapter, destination: DataAdapter) -> bool:
        return isinstance(source, TransfersFiles) and isinstance(
            destination, TransfersFiles
        )

    async def supply(self, source: DataAdapter, node_ids: list[str]) -> Availability:
        try:
            await to_thread.run_sync(source_files, storage_of(source), node_ids)
        except ActionRefused as refusal:
            return Availability(available=False, reason=refusal.message)
        except (OSError, ValueError):
            return Availability(available=False, reason="The selection is unavailable")
        return Availability(available=True)

    async def offer(
        self, source: DataAdapter, destination: DataAdapter, pair: PastePair
    ) -> PasteOffer:
        problem = await to_thread.run_sync(
            inspect_files,
            storage_of(source),
            storage_of(destination),
            pair.source_node_ids,
            pair.destination_node_id,
        )
        if problem is None:
            return offered(self, available=True)
        return offered(
            self,
            available=False,
            reason=problem.message,
            name_conflict=problem.reason == "conflict",
        )

    async def plan(
        self, source: DataAdapter, destination: DataAdapter, request: PasteRun
    ) -> TransferPlan:
        if request.conflict == "replace" and not self.can_replace:
            raise ActionRefused(
                "not_applicable", "A move between connections cannot replace a file"
            )
        return await to_thread.run_sync(
            _planned, storage_of(source), storage_of(destination), request
        )

    async def transfer(
        self,
        source: DataAdapter,
        destination: DataAdapter,
        transfer: Transfer,
        report: TransferReport,
    ) -> None:
        """One file at a time; a file that fails is its own outcome (D168)."""
        from_storage, to_storage = storage_of(source), storage_of(destination)
        folder = await _folder(report, to_storage, transfer.destination_node_id)
        settled = 0
        for item in transfer.items:
            item.outcome = "running"
            await report.changed()
            try:
                await self._one(from_storage, to_storage, folder, item, transfer, report, settled)
            except asyncio.CancelledError:
                item.outcome = "stopped"
                item.message = (
                    f"{item.name} was stopped while it was being copied; "
                    "nothing is left under its name"
                )
                transfer.bytes_done = settled
                raise
            except _Failed as failure:
                item.outcome, item.message = "failed", str(failure)
            except (ActionRefused, VersionChanged, ValueError) as failure:
                item.outcome, item.message = "failed", _said(failure, item.name)
            except AdapterError as failure:
                item.outcome, item.message = "pending", None
                raise TransferStopped(failure.message) from None
            except FileExistsError:
                item.outcome, item.message = "failed", f"{item.name} is already there"
            except OSError:
                item.outcome, item.message = "failed", f"{item.name} could not be copied"
                # One file, or everything after it? The folder answers.
                await _folder(report, to_storage, transfer.destination_node_id)
            settled += item.size_bytes or 0
            transfer.bytes_done = settled
            await report.changed()

    async def _one(
        self,
        source: Storage,
        destination: Storage,
        folder: Place,
        item: TransferItem,
        transfer: Transfer,
        report: TransferReport,
        settled: int,
    ) -> None:
        place = await report.in_thread(partial(source.place, item.node_id))
        entry = await report.in_thread(partial(source.entry, place))
        if entry is None:
            raise _Failed(f"{item.name} no longer exists")
        if entry.is_directory or entry.is_link:
            raise _Failed(f"{item.name} is no longer a file")
        target = await report.in_thread(
            partial(place_for, destination, folder, entry.name, transfer.conflict)
        )
        version = await report.in_thread(partial(source.version, place))
        changed = _Failed(f"{item.name} changed while it was being copied")
        stack = ExitStack()
        try:
            arriving = await report.in_thread(
                partial(stack.enter_context, destination.incoming(target))
            )
            readable = await report.in_thread(partial(source.open, place))
            stack.callback(readable.close)
            written = 0
            while chunk := await report.in_thread(partial(readable.read, PIECE_BYTES)):
                written += len(chunk)
                if written > entry.size_bytes:
                    raise changed
                await report.in_thread(partial(arriving.write, chunk))
                transfer.bytes_done = settled + written
                await report.progressed()
            if written != entry.size_bytes:
                raise changed
            if await report.in_thread(partial(source.version, place)) != version:
                raise changed
            await report.in_thread(
                partial(arriving.publish, target, replace=transfer.conflict == "replace")
            )
        finally:
            await report.in_thread(stack.close)
        transfer.published += 1
        if target.name != item.name:
            item.published_as = target.name
        item.outcome = "done"
        if self.changes_source:
            await _let_go(report, source, place, version, item)

    def told(self, transfer: Transfer, stopped: str | None = None) -> str:
        return told_files(self.done.capitalize(), transfer, stopped)


async def _folder(report: TransferReport, storage: Storage, folder_id: str | None) -> Place:
    """The destination folder, or the end of the transfer."""
    try:
        return await report.in_thread(partial(destination_folder, storage, folder_id))
    except ActionRefused:
        raise TransferStopped("The destination folder is no longer there") from None
    except AdapterError as failure:
        raise TransferStopped(failure.message) from None
    except (OSError, ValueError):
        raise TransferStopped("The destination folder could not be reached") from None


async def _let_go(
    report: TransferReport, source: Storage, place: Place, version: str, item: TransferItem
) -> None:
    """A move removes the source only once its copy is in place and it is
    unchanged since it was read (D163)."""
    try:
        if await report.in_thread(partial(source.version, place)) != version:
            item.outcome = "kept"
            item.message = f"{item.name} was copied, but its source changed and was kept"
            return
        await report.in_thread(partial(source.remove, place))
    except (OSError, AdapterError):
        item.outcome = "kept"
        item.message = f"{item.name} was copied, but its source could not be removed"


def _said(failure: Exception, name: str) -> str:
    if isinstance(failure, ActionRefused):
        return failure.message
    if isinstance(failure, VersionChanged):
        return f"{name} changed while it was being copied"
    return f"{name} is not a file here"


def told_files(verb: str, transfer: Transfer, stopped: str | None = None) -> str:
    """"Copied 3 of 5 files to reports; 1 failed, 1 not attempted"."""
    total = len(transfer.items)
    done = sum(1 for item in transfer.items if item.outcome == "done")
    where = f"to {transfer.place_label}"
    if done == total and stopped is None:
        return f"{verb} {counted(total, 'file')} {where}"
    counts = {
        "kept its source": sum(1 for item in transfer.items if item.outcome == "kept"),
        "failed": sum(1 for item in transfer.items if item.outcome == "failed"),
        "stopped": sum(1 for item in transfer.items if item.outcome == "stopped"),
        "not attempted": sum(
            1 for item in transfer.items if item.outcome in {"pending", "running"}
        ),
    }
    parts = [f"{count} {words}" for words, count in counts.items() if count]
    sentence = f"{verb} {done} of {counted(total, 'file')} {where}"
    if parts:
        sentence += f"; {', '.join(parts)}"
    return sentence if stopped is None else f"{sentence}. {stopped}"


class FileCopy(_Files):
    name: PasteKindName = "file_copy"
    title = "Copy files"
    needs = "Tick files to copy"
    doing = "Copying"
    done = "copied"
    mode: ClipboardMode = "copy"
    can_replace = True
    source_requires: Access = "read"
    changes_source = False


class FileMove(_Files):
    """Replace is withheld: two connections may name the same backing file,
    and replacing it before removing the source would remove the copy (D163)."""

    name: PasteKindName = "file_move"
    title = "Move files"
    needs = "Tick files to move"
    doing = "Moving"
    done = "moved"
    mode: ClipboardMode = "move"
    can_replace = False
    # Moving removes the source file, which is what writing there means.
    source_requires: Access = "write"
    changes_source = True
