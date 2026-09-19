"""Changing what is in a tree of files.

A capability module like `catalog.py` and `fetch.py`: it knows what to do and
nothing about where the files are. Every place it touches — including the name
of an uploaded file, which is a client string like any other — goes through the
storage, so the containment rule of decision D8 stays in one place.

Each action does its work in one hop to a worker thread: a storage blocks
(D151), and an action that asked it anything on the event loop would stall
every other request while a remote server answered.
"""

from collections.abc import Mapping, Sequence
from contextlib import ExitStack
from functools import partial
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, ClassVar, Literal, Protocol

from anyio import to_thread
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.adapters.actions import (
    CHUNK_BYTES,
    Action,
    ActionDownload,
    ActionRefused,
    ActionResult,
    ActionSet,
    ActionType,
    ActsOn,
    ConnectorDraft,
    FileAction,
    FilePayload,
    JsonAction,
)
from app.adapters.catalog import NodeKind
from app.adapters.explorer.download import ExplorerDownload
from app.adapters.explorer.formats import format_of
from app.adapters.explorer.members import ResolvedNode, resolve_node
from app.adapters.explorer.packing import (
    MAX_BYTES,
    MAX_ENTRIES,
    PACK_SUFFIX,
    NotUnpackable,
    PackFormat,
    is_unpackable,
    pack,
    unpack,
    unpacked_name,
)
from app.adapters.explorer.storage import (
    ROOT,
    DraftsConnections,
    Storage,
    is_plain_name,
    node_id_of,
    walk_iterator,
)
from app.core.access import Access
from app.core.config import settings


def _plain_name(value: str) -> str:
    name = value.strip()
    if not is_plain_name(name):
        raise ValueError("A name must be a single plain name, without separators")
    return name


class NameParams(BaseModel):
    name: str = Field(default="new folder", title="Name")

    _check = field_validator("name")(_plain_name)


class FileNameParams(BaseModel):
    name: str = Field(title="Name")

    _check = field_validator("name")(_plain_name)


class RenameParams(BaseModel):
    new_name: str = Field(
        title="New name", json_schema_extra={"x-ui-purpose": "node-name"}
    )

    _check = field_validator("new_name")(_plain_name)


class DeleteParams(BaseModel):
    pass


class ConnectFolderParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UploadParams(BaseModel):
    conflict: Literal["refuse", "replace", "rename"] = Field(
        default="refuse",
        title="File conflict",
        json_schema_extra={"x-ui-purpose": "file-conflict", "x-ui-hidden": True},
    )


class DownloadParams(BaseModel):
    """Download has no form; its complete input is the selected nodes."""

    pass


class ArchiveParams(BaseModel):
    name: str = Field(default="archive", title="Name")
    # The suffix follows from this rather than from what is typed: a person
    # choosing tar.gz and writing "backup.zip" meant tar.gz.
    format: PackFormat = Field(default="zip", title="Format")

    _check = field_validator("name")(_plain_name)


class PasteParams(BaseModel):
    """Where something is going, and what it was picked up as.

    The two hidden fields are filled by the client from what the catalog is
    holding. They are declared by purpose rather than by name, so the form
    knows to fill them without knowing what this action is called.
    """

    sources: list[str] = Field(
        default_factory=list,
        title="What to put here",
        json_schema_extra={"x-ui-purpose": "clipboard-nodes", "x-ui-hidden": True},
    )
    mode: Literal["copy", "move"] = Field(
        default="copy",
        title="Copy or move",
        json_schema_extra={"x-ui-purpose": "clipboard-mode", "x-ui-hidden": True},
    )
    conflict: Literal["refuse", "replace", "rename"] = Field(
        default="refuse",
        title="Name conflict",
        json_schema_extra={"x-ui-purpose": "file-conflict", "x-ui-hidden": True},
    )


class ExtractParams(BaseModel):
    into_folder: bool = Field(
        default=True,
        title="Into a folder of its own",
        description=(
            "Off puts the contents beside the archive, which is what an "
            "archive of one file usually wants"
        ),
    )


class _Bound:
    """Common to every action here: the storage it works through."""

    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    def _directory(self, node_id: str | None) -> PurePosixPath:
        place = self._storage.place(node_id)
        found = self._storage.entry(place)
        if found is None or not found.is_directory:
            raise ValueError(f"Not a directory: {node_id}")
        return place


class _ActsOnNode(_Bound):
    """Changes the node it is given, rather than what is inside it.

    The distinction is what keeps the root of a connector safe: it can be
    added to, never renamed or removed. Stating it as a class rather than a
    list of names means a new action of either sort is classified when it is
    written, not remembered later.
    """

    acts_on: ClassVar[ActsOn] = "node"

    def _target(self, node_id: str | None) -> PurePosixPath:
        place = self._storage.place(node_id)
        if place == ROOT or node_id in (None, ""):
            raise ActionRefused(
                "not_applicable", "The root folder of a connector cannot be changed"
            )
        if self._storage.entry(place) is None:
            raise ValueError(f"No such node: {node_id}")
        return place


class ConnectFolder(_ActsOnNode, Action[ConnectFolderParams]):
    name: ClassVar[str] = "connect_folder"
    title: ClassVar[str] = "Connect folder"
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"directory"})
    # A new file connection is rooted in its creator's home. A grantee cannot
    # turn access to somebody else's folder into an independently owned source.
    requires: ClassVar[Access] = "own"
    params_model = ConnectFolderParams

    async def prepare_connector(
        self, node_id: str | None, raw: Mapping[str, Any]
    ) -> ConnectorDraft:
        self._validated(raw)
        return await to_thread.run_sync(partial(self._draft, node_id))

    def _draft(self, node_id: str | None) -> ConnectorDraft:
        place = self._target(node_id)
        found = self._storage.entry(place)
        if found is None or not found.is_directory:
            raise ActionRefused("not_applicable", "Choose a folder to connect")
        if not isinstance(self._storage, DraftsConnections):
            raise ActionRefused(
                "not_applicable", "A folder of this source cannot become a connection"
            )
        draft = self._storage.connection_for(place)
        # Named as the person named the folder, which a link inside the root
        # may spell differently from where it leads.
        return draft.model_copy(update={"name": PurePosixPath(node_id or "").name})


class CreateFolder(_Bound, JsonAction[NameParams]):
    name: ClassVar[str] = "create_folder"
    title: ClassVar[str] = "New folder"
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"directory"})
    acts_on: ClassVar[ActsOn] = "children"
    params_model = NameParams

    async def run(self, node_id: str | None, params: NameParams) -> ActionResult:
        made = await to_thread.run_sync(self._make, node_id, params.name)
        return ActionResult(
            message=f"Folder {made.name} created",
            reload_node_ids=[node_id or None],
        )

    def _make(self, node_id: str | None, name: str) -> PurePosixPath:
        target = _available(self._storage, self._directory(node_id), name)
        try:
            self._storage.make_directory(target)
        except FileExistsError:
            raise ActionRefused("conflict", f"{target.name} is already there") from None
        return target


class CreateFile(_Bound, JsonAction[FileNameParams]):
    """An empty file under the name typed, in the folder being looked at.

    A taken name is refused rather than numbered, unlike a folder's: whoever
    named the file — a person or the agent (D133) — refers to it by that name
    next, and a quiet "notes (1).txt" would be another file than the one they
    think they made.
    """

    name: ClassVar[str] = "create_file"
    title: ClassVar[str] = "New file"
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"directory"})
    acts_on: ClassVar[ActsOn] = "children"
    params_model = FileNameParams

    async def run(self, node_id: str | None, params: FileNameParams) -> ActionResult:
        made = await to_thread.run_sync(self._make, node_id, params.name)
        return ActionResult(
            message=f"{made.name} created", reload_node_ids=[node_id or None]
        )

    def _make(self, node_id: str | None, name: str) -> PurePosixPath:
        target = self._directory(node_id) / name
        try:
            self._storage.make_file(target)
        except FileExistsError:
            raise ActionRefused("conflict", f"{target.name} is already there") from None
        return target


class Rename(_ActsOnNode, JsonAction[RenameParams]):
    name: ClassVar[str] = "rename"
    title: ClassVar[str] = "Rename"
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"directory", "file"})
    params_model = RenameParams

    async def run(self, node_id: str | None, params: RenameParams) -> ActionResult:
        place = await to_thread.run_sync(self._rename, node_id, params.new_name)
        return ActionResult(
            message=f"Renamed to {params.new_name}",
            reload_node_ids=[node_id_of(place.parent)],
        )

    def _rename(self, node_id: str | None, new_name: str) -> PurePosixPath:
        place = self._target(node_id)
        try:
            self._storage.rename(place, place.parent / new_name)
        except FileExistsError:
            raise ActionRefused("conflict", f"{new_name} is already there") from None
        return place


class Delete(_ActsOnNode, JsonAction[DeleteParams]):
    name: ClassVar[str] = "delete"
    title: ClassVar[str] = "Delete"
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"directory", "file"})
    destructive: ClassVar[bool] = True
    # One form, many files: the parameters of a delete say nothing about which
    # file they are for.
    bulk: ClassVar[bool] = True
    params_model = DeleteParams

    async def run(self, node_id: str | None, params: DeleteParams) -> ActionResult:
        place = await to_thread.run_sync(self._remove, node_id)
        return ActionResult(
            message=f"{place.name} deleted", reload_node_ids=[node_id_of(place.parent)]
        )

    def _remove(self, node_id: str | None) -> PurePosixPath:
        place = self._target(node_id)
        self._storage.remove(place)
        return place


class Download(_ActsOnNode, Action[DownloadParams]):
    """Return one original file, or archive the whole selected set."""

    name: ClassVar[str] = "download"
    title: ClassVar[str] = "Download"
    # An entry too, because a file inside an archive is exactly what a reader
    # wants out of it (D53); everything that changes a node keeps to the two
    # kinds that exist in the storage.
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset(
        {"directory", "file", "entry"}
    )
    requires: ClassVar[Access] = "read"
    bulk: ClassVar[bool] = True
    params_model = DownloadParams

    async def download(
        self, node_ids: Sequence[str], raw: Mapping[str, Any]
    ) -> ActionDownload:
        """The selection is the whole input; this download asks nothing else."""
        resolved = await to_thread.run_sync(self._resolved, node_ids)
        entries = [one for one in resolved if one.member is not None]
        if entries:
            if len(node_ids) > 1:
                raise ActionRefused(
                    "not_applicable",
                    "A file inside an archive is downloaded on its own",
                )
            return await ExplorerDownload(self._storage).entry(entries[0])
        return await ExplorerDownload(self._storage).prepare(node_ids)

    def _resolved(self, node_ids: Sequence[str]) -> list[ResolvedNode]:
        found = [resolve_node(self._storage, node_id) for node_id in node_ids]
        if not any(one.member is not None for one in found):
            # Reapply the same root and existence rule the availability check
            # uses; tickets are redeemed later, when the source may have changed.
            for node_id in node_ids:
                self._target(node_id)
        return found


class PasteHere(_Bound, JsonAction[PasteParams]):
    """Put what was copied or cut into the folder being looked at.

    The destination is where the user is standing, which is why this acts on
    a place's children rather than on a node: a file manager pastes *here*,
    and the alternative — naming a destination in a form — is asking somebody
    to type a path they are looking at.

    What was picked up travels in the request rather than being remembered by
    the server. A selection held for ten minutes in a browser is not a thing
    this source should be keeping, and every id in it is judged on arrival by
    the same containment rule as any other.
    """

    name: ClassVar[str] = "paste"
    title: ClassVar[str] = "Paste"
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"directory"})
    acts_on: ClassVar[ActsOn] = "children"
    requires: ClassVar[Access] = "write"
    params_model = PasteParams

    async def run(self, node_id: str | None, params: PasteParams) -> ActionResult:
        if not params.sources:
            raise ActionRefused("not_applicable", "Copy or cut something first")
        sources = await to_thread.run_sync(self._paste, node_id, params)
        # Both ends change: the folder that gained the nodes, and — for a move
        # — every folder that lost one. Named by the server, because deriving
        # them from the action's name is the rule this exists to avoid.
        changed: list[str | None] = [node_id or None]
        if params.mode == "move":
            for source in sources:
                parent = node_id_of(source.parent)
                if parent not in changed:
                    changed.append(parent)
        verb = "copied" if params.mode == "copy" else "moved"
        return ActionResult(
            message=f"{_counted(len(sources))} {verb}", reload_node_ids=changed
        )

    def _paste(
        self, node_id: str | None, params: PasteParams
    ) -> list[PurePosixPath]:
        """Copy or move every source into one folder.

        Bounded by the same two ceilings an archive is: a copy of a hundred
        thousand files is a request nobody should be waiting on, and the count
        is taken before anything is written.
        """
        destination = self._directory(node_id)
        sources = [self._source(one) for one in params.sources]
        for source in sources:
            _may_go_into(source, destination)
        _within_bounds(self._storage, sources)
        for source in sources:
            target = destination / source.name
            if self._storage.entry(target) is not None:
                if params.conflict == "refuse":
                    raise ActionRefused("conflict", f"{source.name} is already there")
                if params.conflict == "rename":
                    target = _available(self._storage, destination, source.name)
                else:
                    self._storage.remove(target)
            if params.mode == "move":
                self._storage.rename(source, target)
            else:
                self._storage.copy(source, target)
        return sources

    def _source(self, node_id: str) -> PurePosixPath:
        place = self._storage.place(node_id)
        if place == ROOT:
            raise ActionRefused(
                "not_applicable", "The root folder of a connector cannot be moved"
            )
        if self._storage.entry(place) is None:
            raise ValueError(f"No such node: {node_id}")
        return place


def _may_go_into(source: PurePosixPath, destination: PurePosixPath) -> None:
    """A folder cannot be put inside itself, however deep.

    The check is on the resolved places rather than on the ids, because two
    ids can name one place and only one of them looks like a prefix of the
    other.
    """
    if source == destination or destination.is_relative_to(source):
        raise ActionRefused(
            "not_applicable", f"{source.name} cannot be put inside itself"
        )


def _counted(number: int) -> str:
    return "1 item" if number == 1 else f"{number} items"


def _within_bounds(storage: Storage, sources: Sequence[PurePosixPath]) -> None:
    entries = 0
    total = 0
    for source in sources:
        found = storage.entry(source)
        if found is not None and not found.is_directory:
            entries += 1
            total += found.size_bytes
            continue
        for entry in walk_iterator(storage, source):
            entries += 1
            if entries > MAX_ENTRIES:
                raise ActionRefused("too_large", "That is too many files to move")
            if not entry.is_directory:
                total += entry.size_bytes
        if total > MAX_BYTES:
            raise ActionRefused("too_large", "That is too much data to move")
    if entries > MAX_ENTRIES:
        raise ActionRefused("too_large", "That is too many files to move")
    if total > MAX_BYTES:
        raise ActionRefused("too_large", "That is too much data to move")


class CreateArchive(_ActsOnNode, JsonAction[ArchiveParams]):
    """Pack the whole selection into one new archive beside it.

    A set action rather than a repeated one (D68): five files chosen for one
    archive are one archive, and sending them one at a time would make five.
    """

    name: ClassVar[str] = "create_archive"
    title: ClassVar[str] = "Archive"
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"directory", "file"})
    requires: ClassVar[Access] = "write"
    bulk: ClassVar[bool] = True
    params_model = ArchiveParams

    async def run(self, node_id: str | None, params: ArchiveParams) -> ActionResult:
        return await self._archive([node_id], params)

    async def perform_on_set(
        self, node_ids: Sequence[str], raw: dict[str, Any]
    ) -> ActionResult:
        return await self._archive(list(node_ids), self._validated(raw))

    def _packable(self, node_id: str | None) -> PurePosixPath:
        """One target of the walk, refusing a link named in the selection.

        The walk refuses every symbolic link it meets among the children, and
        a link named directly has to go the same way: resolving one first would
        pack the tree it points at, so the same link would be archived or
        refused depending only on how it was reached.
        """
        target = self._target(node_id)
        if node_id is not None:
            try:
                self._storage.unlinked_place(node_id)
            except ValueError:
                raise ActionRefused(
                    "not_applicable", "Symbolic links are not archived"
                ) from None
        return target

    async def _archive(
        self, node_ids: Sequence[str | None], params: ArchiveParams
    ) -> ActionResult:
        into = await to_thread.run_sync(self._pack, node_ids, params)
        return ActionResult(
            message=f"{into.name} created",
            reload_node_ids=[node_id_of(into.parent)],
        )

    def _pack(
        self, node_ids: Sequence[str | None], params: ArchiveParams
    ) -> PurePosixPath:
        targets = [self._packable(node_id) for node_id in node_ids]
        parents = {target.parent for target in targets}
        if len(parents) != 1:
            raise ActionRefused(
                "not_applicable", "One archive is made of one folder's contents"
            )
        into = _available(self._storage, parents.pop(), _archive_filename(params))
        try:
            with ExitStack() as held:
                local = [held.enter_context(self._storage.local_tree(t)) for t in targets]
                with self._storage.staged(into, prefix=".dataplayer-packing-") as staged:
                    pack(local, staged, params.format)
                    self._storage.publish(staged, into)
        except FileExistsError:
            raise ActionRefused("conflict", f"{into.name} is already there") from None
        except OSError:
            raise ValueError("The archive could not be written") from None
        return into


class ExtractArchive(_ActsOnNode, JsonAction[ExtractParams]):
    """Expand one archive where it lies.

    Repeated rather than taken as a set: three archives are three expansions,
    and one of them being refused says nothing about the other two.
    """

    name: ClassVar[str] = "extract_archive"
    title: ClassVar[str] = "Extract"
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"file"})
    requires: ClassVar[Access] = "write"
    bulk: ClassVar[bool] = True
    params_model = ExtractParams

    async def run(self, node_id: str | None, params: ExtractParams) -> ActionResult:
        place, entries, made = await to_thread.run_sync(
            self._extract, node_id, params
        )
        return ActionResult(
            message=_extracted(entries, made),
            reload_node_ids=[node_id_of(place.parent)],
        )

    def _extract(
        self, node_id: str | None, params: ExtractParams
    ) -> tuple[PurePosixPath, int, PurePosixPath | None]:
        place = self._target(node_id)
        if not is_unpackable(place.name):
            raise ActionRefused(
                "not_applicable", f"{place.name} is not an archive this source opens"
            )
        made: PurePosixPath | None = None
        if params.into_folder:
            made = _available(self._storage, place.parent, unpacked_name(place.name))
            try:
                self._storage.make_directory(made)
            except FileExistsError:
                raise ActionRefused("conflict", f"{made.name} is already there") from None
        destination = made or place.parent
        try:
            with (
                self._storage.local_file(place) as archive_path,
                self._storage.filled(destination) as into,
            ):
                unpacked = unpack(archive_path, into)
        except NotUnpackable as exc:
            self._undo(made)
            raise ActionRefused("not_applicable", str(exc)) from None
        except BaseException:
            # A refused archive leaves nothing behind: the folder this made a
            # moment ago is part of the refusal, not a result of it.
            self._undo(made)
            raise
        return place, unpacked.entries, made

    def _undo(self, made: PurePosixPath | None) -> None:
        if made is None:
            return
        try:
            self._storage.remove(made)
        except OSError:
            return


def _archive_filename(params: ArchiveParams) -> str:
    """The name of the archive, with the suffix its format asks for.

    Appended rather than assumed: somebody who types the suffix gets it once,
    and somebody who does not gets a file their computer will open.
    """
    suffix = PACK_SUFFIX[params.format]
    if params.name.lower().endswith(suffix):
        return params.name
    return f"{params.name}{suffix}"


def _extracted(entries: int, made: PurePosixPath | None) -> str:
    what = "1 file" if entries == 1 else f"{entries} files"
    return f"{what} extracted" + ("" if made is None else f" into {made.name}")


class Upload(_Bound, FileAction[UploadParams]):
    name: ClassVar[str] = "upload"
    title: ClassVar[str] = "Upload files"
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"directory"})
    acts_on: ClassVar[ActsOn] = "children"
    # A folder takes as many files as are handed to it, and each one is a
    # whole upload of its own: one refused name does not spoil the rest.
    many_files: ClassVar[bool] = True
    params_model = UploadParams

    async def run(
        self, node_id: str | None, params: UploadParams, payload: FilePayload
    ) -> ActionResult:
        filename = _plain_name(payload.filename or "")
        target = await to_thread.run_sync(self._target, node_id, filename, params)
        # Written beside its destination, then moved into place: a reader of
        # the catalog never sees a half-written file under the real name, and a
        # refused upload leaves nothing behind.
        staging = self._storage.staged(target, prefix=".upload-")
        staged = await to_thread.run_sync(staging.__enter__)
        try:
            await _stream_into(staged, payload)
            published = await to_thread.run_sync(
                self._publish, staged, target, params.conflict
            )
        finally:
            await to_thread.run_sync(staging.__exit__, None, None, None)
        return ActionResult(
            message=f"{published.name} uploaded", reload_node_ids=[node_id or None]
        )

    def _target(
        self, node_id: str | None, filename: str, params: UploadParams
    ) -> PurePosixPath:
        target = self._directory(node_id) / filename
        if params.conflict == "refuse" and self._storage.entry(target) is not None:
            raise ActionRefused("conflict", f"{filename} is already there")
        return target

    def _publish(
        self,
        staged: Path,
        target: PurePosixPath,
        conflict: Literal["refuse", "replace", "rename"],
    ) -> PurePosixPath:
        if conflict == "replace":
            self._storage.publish(staged, target, replace=True)
            return target
        if conflict == "refuse":
            # A file that appeared after the first check is not replaced.
            try:
                self._storage.publish(staged, target)
            except FileExistsError:
                raise ActionRefused("conflict", f"{target.name} is already there") from None
            return target
        number = 1
        while True:
            numbered = target.parent / _numbered_name(target.name, number)
            try:
                self._storage.publish(staged, numbered)
            except FileExistsError:
                number += 1
                continue
            return numbered


async def _stream_into(staged: Path, payload: FilePayload) -> None:
    """The upload's bytes into the staged file, counted as they arrive.

    The size is counted rather than read from a header, which is a claim by
    the client.
    """
    handle = await to_thread.run_sync(_opened_for_writing, staged)
    try:
        written = 0
        while chunk := await payload.read(CHUNK_BYTES):
            written += len(chunk)
            if written > settings.MAX_UPLOAD_BYTES:
                raise ActionRefused(
                    "too_large", "The file is larger than this server accepts"
                )
            await to_thread.run_sync(handle.write, chunk)
    finally:
        await to_thread.run_sync(handle.close)


def _opened_for_writing(path: Path) -> BinaryIO:
    return path.open("wb")


def _numbered_name(name: str, number: int) -> str:
    """Put a copy number before the uploaded file's suffix."""
    path = PurePosixPath(name)
    suffix = path.suffix if path.suffix != name else ""
    stem = name[: -len(suffix)] if suffix else name
    return f"{stem} ({number}){suffix}"


def _available(storage: Storage, parent: PurePosixPath, name: str) -> PurePosixPath:
    candidate = parent / name
    number = 1
    while storage.entry(candidate) is not None:
        candidate = parent / f"{name} ({number})"
        number += 1
    return candidate


class ExplorerActionType(ActionType, Protocol):
    """One of the classes below, seen from outside.

    Both halves are needed and neither alone is enough: the registry reads
    `title` off the class, and `ExplorerActions` builds an instance from a
    storage.
    """

    def __call__(self, storage: Storage) -> Action[Any]: ...


# The actions a tree of files has, as classes.
#
# Two readers, one tuple: `ExplorerActions` builds its set from it, and the
# registry reads the titles off it to say what the type can do. A second list
# would be a list to forget — the same reasoning that derives secret fields
# from `SecretStr` rather than from a register of names. A source whose folders
# cannot become connections of their own leaves `ConnectFolder` out.
EXPLORER_ACTION_TYPES: tuple[ExplorerActionType, ...] = (
    CreateFolder,
    CreateFile,
    ConnectFolder,
    Upload,
    PasteHere,
    Download,
    CreateArchive,
    ExtractArchive,
    Rename,
    Delete,
)


class ExplorerActions:
    """What a tree of files offers on a given node."""

    def __init__(
        self,
        storage: Storage,
        action_types: tuple[ExplorerActionType, ...] = EXPLORER_ACTION_TYPES,
    ) -> None:
        self._storage = storage
        self._actions = ActionSet([action_type(storage) for action_type in action_types])

    def action(self, name: str) -> Action[Any]:
        return self._actions.get(name)

    async def all_actions(self) -> list[Action[Any]]:
        return list(self._actions)

    async def available(self, node_id: str | None) -> list[Action[Any]]:
        place, kind = await to_thread.run_sync(self._look_at, node_id)
        offered = self._actions.for_kind(kind)
        if place == ROOT:
            # The root is an ordinary directory, and its state — not its kind —
            # is what rules the two actions out.
            return [action for action in offered if not isinstance(action, _ActsOnNode)]
        if kind == "file" and not is_unpackable(place.name):
            # Said here rather than in `applies_to`, which speaks about kinds:
            # every file is a file, and only some of them are archives.
            return [
                action
                for action in offered
                if not isinstance(action, ExtractArchive)
            ]
        return offered

    def _look_at(self, node_id: str | None) -> tuple[PurePosixPath, NodeKind]:
        """What the id names, and of what kind. Blocking: it asks the storage.

        A member of a container file is a node like any other, and answering
        with its kind is what leaves it out of every action: the four that act
        on a file and the one that acts on a directory name those kinds, and a
        dataset is neither (D51).
        """
        if node_id is None or node_id == "":
            return ROOT, "directory"
        resolved = resolve_node(self._storage, node_id)
        if resolved.member is not None:
            kind: NodeKind = (
                "entry" if format_of(resolved.name) == "archive" else "dataset"
            )
            return resolved.place, kind
        if resolved.entry is None:
            raise ValueError(f"No such node: {node_id}")
        return resolved.place, "directory" if resolved.entry.is_directory else "file"
