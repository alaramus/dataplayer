"""Copy or move files between independent explorer connections."""

from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from app.adapters.actions import ActionRefused
from app.adapters.explorer.storage import Storage, is_plain_name

MAX_TRANSFER_FILES = 20
MAX_TRANSFER_BYTES = 200 * 1024 * 1024


@runtime_checkable
class TransfersFiles(Protocol):
    @property
    def storage(self) -> Storage: ...


class FileCopyRequest(BaseModel):
    source_connector_id: str
    source_node_ids: list[str] = Field(min_length=1, max_length=MAX_TRANSFER_FILES)
    destination_node_id: str | None = None
    conflict: Literal["refuse", "replace", "rename"] = "refuse"


class FileCopyOffer(BaseModel):
    available: bool
    reason: str | None = None
    name_conflict: bool = False


class FileCopyResult(BaseModel):
    copied: int
    reload_node_ids: list[str | None]


class FileMoveResult(BaseModel):
    moved: int
    reload_node_ids: list[str | None]


def inspect_copy(
    source: Storage, destination: Storage, request: FileCopyRequest
) -> FileCopyOffer:
    """Check the pair without opening file bytes or changing either source."""
    try:
        if len(set(request.source_node_ids)) != len(request.source_node_ids):
            return FileCopyOffer(
                available=False, reason="The selection contains a file twice"
            )
        target_folder = destination.place(request.destination_node_id)
        folder = destination.entry(target_folder)
        if folder is None or not folder.is_directory:
            return FileCopyOffer(available=False, reason="Choose a destination folder")
        total = 0
        names: set[str] = set()
        for node_id in request.source_node_ids:
            place = source.place(node_id)
            entry = source.entry(place)
            if entry is None:
                return FileCopyOffer(
                    available=False, reason="A copied file no longer exists"
                )
            if entry.is_directory or entry.is_link:
                return FileCopyOffer(
                    available=False, reason="Copy files, not folders or links"
                )
            if not is_plain_name(entry.name):
                return FileCopyOffer(
                    available=False, reason="A file has an invalid name"
                )
            if entry.name in names:
                return FileCopyOffer(available=False, reason="Two files have the same name")
            names.add(entry.name)
            total += entry.size_bytes
            if total > MAX_TRANSFER_BYTES:
                return FileCopyOffer(available=False, reason="The selection exceeds 200 MB")
            target = destination.child(target_folder, entry.name)
            existing = destination.entry(target)
            if existing is not None and existing.is_directory:
                return FileCopyOffer(
                    available=False, reason=f"{entry.name} is a folder here"
                )
            if existing is not None and request.conflict == "refuse":
                return FileCopyOffer(
                    available=False,
                    reason=f"{entry.name} is already there",
                    name_conflict=True,
                )
        return FileCopyOffer(available=True)
    except (OSError, ValueError):
        return FileCopyOffer(available=False, reason="A source or destination is unavailable")


def inspect_move(
    source: Storage, destination: Storage, request: FileCopyRequest
) -> FileCopyOffer:
    """A move cannot replace a name that may alias its own source."""
    if request.conflict == "replace":
        return FileCopyOffer(
            available=False,
            reason="Keep both or cancel a move when the name is already taken",
        )
    return inspect_copy(source, destination, request)


def copy_files(
    source: Storage, destination: Storage, request: FileCopyRequest
) -> FileCopyResult:
    """Copy file bytes and leave the source in place."""
    copied = _transfer_files(source, destination, request, move=False)
    return FileCopyResult(
        copied=copied, reload_node_ids=[request.destination_node_id]
    )


def move_files(
    source: Storage, destination: Storage, request: FileCopyRequest
) -> FileMoveResult:
    """Publish each copy before removing its unchanged source file."""
    if request.conflict == "replace":
        raise ActionRefused(
            "not_applicable", "A cross-connection move cannot replace a file"
        )
    moved = _transfer_files(source, destination, request, move=True)
    return FileMoveResult(moved=moved, reload_node_ids=[request.destination_node_id])


def _transfer_files(
    source: Storage,
    destination: Storage,
    request: FileCopyRequest,
    *,
    move: bool,
) -> int:
    """Stage every file at its destination; each published file is complete."""
    offer = inspect_copy(source, destination, request)
    if not offer.available:
        raise ActionRefused(
            "conflict" if offer.name_conflict else "not_applicable",
            offer.reason or "File copy is unavailable",
        )
    folder = destination.place(request.destination_node_id)
    completed = 0
    remaining = MAX_TRANSFER_BYTES
    for node_id in request.source_node_ids:
        place = source.place(node_id)
        entry = source.entry(place)
        if entry is None or entry.is_directory or entry.is_link:
            raise ActionRefused("not_applicable", "A copied file changed")
        target = destination.child(folder, entry.name)
        existing = destination.entry(target)
        if existing is not None:
            if request.conflict == "refuse":
                raise ActionRefused("conflict", f"{entry.name} is already there")
            if request.conflict == "rename":
                stem, dot, suffix = entry.name.rpartition(".")
                if not dot:
                    stem, suffix = entry.name, ""
                for number in range(1, 10_001):
                    candidate = f"{stem} ({number}){'.' + suffix if suffix else ''}"
                    target = destination.child(folder, candidate)
                    if destination.entry(target) is None:
                        break
                else:
                    raise ActionRefused("conflict", "No free file name is available")
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
