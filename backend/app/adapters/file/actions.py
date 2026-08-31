"""Changing what is in a personal directory.

A capability module like `catalog.py` and `fetch.py`: it knows what to do and
nothing about how the root was decided. Every path it touches — including the
name of an uploaded file, which is a client string like any other — goes
through the session, so the containment rule of decision D8 stays in one place.
"""

import os
import shutil
import tempfile
from collections.abc import Sequence
from functools import partial
from pathlib import Path
from typing import Any, ClassVar, Literal, Protocol

from anyio import to_thread
from pydantic import BaseModel, Field, field_validator

from app.adapters.actions import (
    CHUNK_BYTES,
    Action,
    ActionDownload,
    ActionRefused,
    ActionResult,
    ActionSet,
    ActionType,
    ActsOn,
    FileAction,
    FilePayload,
    JsonAction,
)
from app.adapters.catalog import NodeKind
from app.adapters.file.download import FileDownload
from app.adapters.file.formats import format_of
from app.adapters.file.members import resolve_node
from app.adapters.file.session import FileSession, is_plain_name
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


class RenameParams(BaseModel):
    new_name: str = Field(
        title="New name", json_schema_extra={"x-ui-purpose": "node-name"}
    )

    _check = field_validator("new_name")(_plain_name)


class DeleteParams(BaseModel):
    pass


class UploadParams(BaseModel):
    conflict: Literal["refuse", "replace", "rename"] = Field(
        default="refuse",
        title="File conflict",
        json_schema_extra={"x-ui-purpose": "file-conflict", "x-ui-hidden": True},
    )


class DownloadParams(BaseModel):
    """Download has no form; its complete input is the selected nodes."""

    pass


class _Bound:
    """Common to every action here: the session it works through."""

    def __init__(self, session: FileSession) -> None:
        self._session = session

    def _directory(self, node_id: str | None) -> Path:
        path = self._session.resolve(node_id)
        if not path.is_dir():
            raise ValueError(f"Not a directory: {node_id}")
        return path

    def _parent_id(self, path: Path) -> str | None:
        """The node whose children changed, as the client names it."""
        if path.parent == self._session.resolved_root:
            return None
        return self._session.relative_id(path.parent)


class _ActsOnNode(_Bound):
    """Changes the node it is given, rather than what is inside it.

    The distinction is what keeps the root of a connector safe: it can be
    added to, never renamed or removed. Stating it as a class rather than a
    list of names means a new action of either sort is classified when it is
    written, not remembered later.
    """

    acts_on: ClassVar[ActsOn] = "node"

    def _target(self, node_id: str | None) -> Path:
        path = self._session.resolve(node_id)
        if path == self._session.resolved_root or node_id in (None, ""):
            raise ActionRefused(
                "not_applicable", "The root folder of a connector cannot be changed"
            )
        if not path.exists():
            raise ValueError(f"No such node: {node_id}")
        return path


class CreateFolder(_Bound, JsonAction[NameParams]):
    name: ClassVar[str] = "create_folder"
    title: ClassVar[str] = "New folder"
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"directory"})
    acts_on: ClassVar[ActsOn] = "children"
    params_model = NameParams

    async def run(self, node_id: str | None, params: NameParams) -> ActionResult:
        parent = self._directory(node_id)
        target = await to_thread.run_sync(partial(_available_path, parent, params.name))
        await to_thread.run_sync(partial(_make_directory, target))
        return ActionResult(
            message=f"Folder {target.name} created", reload_node_id=node_id or None
        )


class Rename(_ActsOnNode, JsonAction[RenameParams]):
    name: ClassVar[str] = "rename"
    title: ClassVar[str] = "Rename"
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"directory", "file"})
    params_model = RenameParams

    async def run(self, node_id: str | None, params: RenameParams) -> ActionResult:
        path = self._target(node_id)
        target = path.parent / params.new_name
        await to_thread.run_sync(partial(_rename, path, target))
        return ActionResult(
            message=f"Renamed to {params.new_name}",
            reload_node_id=self._parent_id(path),
        )


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
        path = self._target(node_id)
        reload_node_id = self._parent_id(path)
        await to_thread.run_sync(partial(_remove, path))
        return ActionResult(
            message=f"{path.name} deleted", reload_node_id=reload_node_id
        )


class Download(_ActsOnNode, Action[DownloadParams]):
    """Return one original file, or archive the whole selected set."""

    name: ClassVar[str] = "download"
    title: ClassVar[str] = "Download"
    # An entry too, because a file inside an archive is exactly what a reader
    # wants out of it (D53); everything that changes a node keeps to the two
    # kinds that exist on disk.
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset(
        {"directory", "file", "entry"}
    )
    requires: ClassVar[Access] = "read"
    bulk: ClassVar[bool] = True
    params_model = DownloadParams

    async def download(self, node_ids: Sequence[str]) -> ActionDownload:
        entries = [
            resolved
            for node_id in node_ids
            if (resolved := resolve_node(self._session, node_id)).member is not None
        ]
        if entries:
            if len(node_ids) > 1:
                raise ActionRefused(
                    "not_applicable",
                    "A file inside an archive is downloaded on its own",
                )
            return await FileDownload(self._session).entry(entries[0])
        # Reapply the same root and existence rule the availability check uses;
        # tickets are redeemed later, when the source may have changed.
        for node_id in node_ids:
            self._target(node_id)
        return await FileDownload(self._session).prepare(node_ids)


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
        parent = self._directory(node_id)
        filename = _plain_name(payload.filename or "")
        target = parent / filename
        if target.exists() and params.conflict == "refuse":
            raise ActionRefused("conflict", f"{filename} is already there")
        temporary = await self._stream_into(parent, payload)
        try:
            if params.conflict == "replace":
                await to_thread.run_sync(partial(os.replace, temporary, target))
            elif params.conflict == "rename":
                target = await to_thread.run_sync(
                    partial(_publish_with_available_name, temporary, parent, filename)
                )
            else:
                await to_thread.run_sync(partial(_publish_new, temporary, target))
        finally:
            await to_thread.run_sync(partial(temporary.unlink, missing_ok=True))
        return ActionResult(
            message=f"{target.name} uploaded", reload_node_id=node_id or None
        )

    async def _stream_into(self, parent: Path, payload: FilePayload) -> Path:
        """Write the upload beside its destination, then move it into place.

        A reader of the catalog never sees a half-written file under the real
        name, and a refused upload leaves nothing behind. The size is counted
        as the bytes arrive rather than read from a header, which is a claim
        by the client.
        """
        descriptor, temporary = await to_thread.run_sync(
            partial(tempfile.mkstemp, dir=parent, prefix=".upload-")
        )
        path = Path(temporary)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                written = 0
                while chunk := await payload.read(CHUNK_BYTES):
                    written += len(chunk)
                    if written > settings.MAX_UPLOAD_BYTES:
                        raise ActionRefused(
                            "too_large",
                            "The file is larger than this server accepts",
                        )
                    await to_thread.run_sync(handle.write, chunk)
            return path
        except BaseException:
            await to_thread.run_sync(partial(path.unlink, missing_ok=True))
            raise


def _make_directory(target: Path) -> None:
    try:
        target.mkdir()
    except FileExistsError:
        raise ActionRefused("conflict", f"{target.name} is already there") from None


def _rename(path: Path, target: Path) -> None:
    if target.exists():
        raise ActionRefused("conflict", f"{target.name} is already there")
    path.rename(target)


def _remove(path: Path) -> None:
    if not path.is_dir():
        path.unlink()
        return
    shutil.rmtree(path)


def _numbered_name(name: str, number: int) -> str:
    """Put a copy number before the uploaded file's suffix."""
    path = Path(name)
    suffix = path.suffix if path.suffix != name else ""
    stem = name[: -len(suffix)] if suffix else name
    return f"{stem} ({number}){suffix}"


def _available_path(parent: Path, name: str) -> Path:
    candidate = parent / name
    number = 1
    while candidate.exists():
        candidate = parent / f"{name} ({number})"
        number += 1
    return candidate


def _publish_new(temporary: Path, target: Path) -> None:
    """Publish without replacing a file that appeared after the first check."""
    try:
        os.link(temporary, target)
    except FileExistsError:
        raise ActionRefused("conflict", f"{target.name} is already there") from None


def _publish_with_available_name(temporary: Path, parent: Path, name: str) -> Path:
    number = 1
    while True:
        target = parent / _numbered_name(name, number)
        try:
            os.link(temporary, target)
        except FileExistsError:
            number += 1
            continue
        return target


class FileActionType(ActionType, Protocol):
    """One of the classes below, seen from outside.

    Both halves are needed and neither alone is enough: the registry reads
    `title` off the class, and `FileActions` builds an instance from a session.
    """

    def __call__(self, session: FileSession) -> Action[Any]: ...


# The actions a file source has, as classes.
#
# Two readers, one tuple: `FileActions` builds its set from it, and the
# registry reads the titles off it to say what the type can do. A second list
# would be a list to forget — the same reasoning that derives secret fields
# from `SecretStr` rather than from a register of names.
FILE_ACTION_TYPES: tuple[FileActionType, ...] = (
    CreateFolder,
    Upload,
    Download,
    Rename,
    Delete,
)


class FileActions:
    """What a file source offers on a given node."""

    def __init__(self, session: FileSession) -> None:
        self._session = session
        self._actions = ActionSet(
            [action_type(session) for action_type in FILE_ACTION_TYPES]
        )

    def action(self, name: str) -> Action[Any]:
        return self._actions.get(name)

    def all_actions(self) -> list[Action[Any]]:
        return list(self._actions)

    async def available(self, node_id: str | None) -> list[Action[Any]]:
        path, kind = await to_thread.run_sync(partial(self._look_at, node_id))
        offered = self._actions.for_kind(kind)
        if path == self._session.resolved_root:
            # The root is an ordinary directory, and its state — not its kind —
            # is what rules the two actions out.
            return [action for action in offered if not isinstance(action, _ActsOnNode)]
        return offered

    def _look_at(self, node_id: str | None) -> tuple[Path, NodeKind]:
        """What the id names, and of what kind. Blocking: it stats the path.

        A member of a container file is a node like any other, and answering
        with its kind is what leaves it out of every action: the four that act
        on a file and the one that acts on a directory name those kinds, and a
        dataset is neither (D51).
        """
        if node_id is None or node_id == "":
            return self._session.root, "directory"
        resolved = resolve_node(self._session, node_id)
        if resolved.member is not None:
            kind: NodeKind = (
                "entry" if format_of(resolved.path.name) == "archive" else "dataset"
            )
            return resolved.path, kind
        return resolved.path, _kind_of(resolved.path, node_id)


def _kind_of(path: Path, node_id: str | None) -> NodeKind:
    if path.is_dir():
        return "directory"
    if path.is_file():
        return "file"
    raise ValueError(f"No such node: {node_id}")
