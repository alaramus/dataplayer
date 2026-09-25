"""Files copied or moved between explorer connections (D161, D163)."""

from functools import partial
from typing import Protocol, runtime_checkable

from anyio import to_thread

from app.adapters.actions import ActionRefused
from app.adapters.explorer.storage import Entry, Place, Storage, is_plain_name
from app.adapters.protocol import DataAdapter
from app.connectors.paste.kinds import counted, offered
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

MAX_TRANSFER_FILES = 20
MAX_TRANSFER_BYTES = 200 * 1024 * 1024


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
    total = 0
    for node_id in node_ids:
        entry = source.entry(source.place(node_id))
        if entry is None:
            raise ActionRefused("not_applicable", "A copied file no longer exists")
        if entry.is_directory or entry.is_link:
            raise ActionRefused("not_applicable", "Copy files, not folders or links")
        if not is_plain_name(entry.name):
            raise ActionRefused("not_applicable", "A file has an invalid name")
        if any(entry.name == other.name for other in entries):
            raise ActionRefused("not_applicable", "Two files have the same name")
        total += entry.size_bytes
        if total > MAX_TRANSFER_BYTES:
            raise ActionRefused("not_applicable", "The selection exceeds 200 MB")
        entries.append(entry)
    return entries


def inspect_files(
    source: Storage,
    destination: Storage,
    node_ids: list[str],
    folder_id: str | None,
    conflict: Conflict = "refuse",
) -> ActionRefused | None:
    """Why the files cannot be pasted now, checked without opening their bytes."""
    try:
        entries = source_files(source, node_ids)
        folder = destination_folder(destination, folder_id)
        for entry in entries:
            place_for(destination, folder, entry.name, conflict)
    except ActionRefused as refusal:
        return refusal
    except (OSError, ValueError):
        return ActionRefused("not_applicable", "A source or destination is unavailable")
    return None


def transfer_files(
    source: Storage, destination: Storage, request: PasteRun, *, move: bool
) -> int:
    """Stage every file at its destination; each published file is complete.

    A move removes each source file only after its copy is published and the
    source is unchanged since it was read.
    """
    problem = inspect_files(
        source,
        destination,
        request.source_node_ids,
        request.destination_node_id,
        request.conflict,
    )
    if problem is not None:
        raise problem
    folder = destination.place(request.destination_node_id)
    completed = 0
    remaining = MAX_TRANSFER_BYTES
    for node_id in request.source_node_ids:
        place = source.place(node_id)
        entry = source.entry(place)
        if entry is None or entry.is_directory or entry.is_link:
            raise ActionRefused("not_applicable", "A copied file changed")
        target = place_for(destination, folder, entry.name, request.conflict)
        try:
            version = source.version(place)
            written = 0
            with destination.staged(target) as staged:
                with source.open(place) as readable, staged.open("wb") as writable:
                    while chunk := readable.read(min(1024 * 1024, remaining + 1)):
                        remaining -= len(chunk)
                        written += len(chunk)
                        if remaining < 0:
                            raise ActionRefused(
                                "too_large", "The selection exceeds 200 MB"
                            )
                        writable.write(chunk)
                if written != entry.size_bytes or source.version(place) != version:
                    raise ActionRefused(
                        "not_applicable", f"{entry.name} changed during copying"
                    )
                destination.publish(
                    staged, target, replace=request.conflict == "replace"
                )
        except FileExistsError:
            raise ActionRefused("conflict", f"{target.name} is already there") from None
        except OSError:
            raise ActionRefused("not_applicable", "The file could not be copied") from None
        if move:
            try:
                if source.version(place) != version:
                    raise ActionRefused(
                        "not_applicable",
                        f"{entry.name} was copied, but its source changed and was kept",
                    )
                source.remove(place)
            except OSError:
                raise ActionRefused(
                    "not_applicable",
                    f"{entry.name} was copied, but its source could not be removed",
                ) from None
        completed += 1
    return completed


class _Files:
    name: PasteKindName
    title: str
    done: str
    mode: ClipboardMode
    can_replace: bool
    source_requires: Access
    changes_source: bool
    converts = False

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

    async def run(
        self, source: DataAdapter, destination: DataAdapter, request: PasteRun
    ) -> PasteResult:
        if request.conflict == "replace" and not self.can_replace:
            raise ActionRefused(
                "not_applicable", "A move between connections cannot replace a file"
            )
        count = await to_thread.run_sync(
            partial(
                transfer_files,
                storage_of(source),
                storage_of(destination),
                request,
                move=self.changes_source,
            )
        )
        return PasteResult(
            kind=self.name,
            message=f"{counted(count, 'file')} {self.done}",
            written=count,
            reload_node_ids=[request.destination_node_id],
        )


class FileCopy(_Files):
    name: PasteKindName = "file_copy"
    title = "Copy files"
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
    done = "moved"
    mode: ClipboardMode = "move"
    can_replace = False
    # Moving removes the source file, which is what writing there means.
    source_requires: Access = "write"
    changes_source = True
