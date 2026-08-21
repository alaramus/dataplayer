"""Changing what is in a personal directory.

A capability module like `catalog.py` and `fetch.py`: it knows what to do and
nothing about how the root was decided. Every path it touches — including the
name of an uploaded file, which is a client string like any other — goes
through the session, so the containment rule of decision D8 stays in one place.
"""

import os
import shutil
import tempfile
from functools import partial
from pathlib import Path
from typing import Any, ClassVar

from anyio import to_thread
from pydantic import BaseModel, Field, field_validator

from app.adapters.actions import (
    Action,
    ActionRefused,
    ActionResult,
    ActionSet,
    FileAction,
    FilePayload,
    JsonAction,
)
from app.adapters.catalog import NodeKind
from app.adapters.file.session import FileSession, is_plain_name
from app.core.config import settings

# Big enough that a large upload is not a million round trips, small enough
# that a refused one is caught long before it is all in memory.
CHUNK_BYTES = 64 * 1024


def _plain_name(value: str) -> str:
    name = value.strip()
    if not is_plain_name(name):
        raise ValueError("A name must be a single plain name, without separators")
    return name


class NameParams(BaseModel):
    name: str = Field(title="Name")

    _check = field_validator("name")(_plain_name)


class RenameParams(BaseModel):
    new_name: str = Field(title="New name")

    _check = field_validator("new_name")(_plain_name)


class DeleteParams(BaseModel):
    recursive: bool = Field(
        default=False,
        title="Delete everything inside",
        description="Required to delete a folder that is not empty",
    )


class UploadParams(BaseModel):
    overwrite: bool = Field(
        default=False,
        title="Replace an existing file",
        description="Required when a file of that name is already there",
    )


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
    params_model = NameParams

    async def run(self, node_id: str | None, params: NameParams) -> ActionResult:
        parent = self._directory(node_id)
        target = parent / params.name
        await to_thread.run_sync(partial(_make_directory, target))
        return ActionResult(
            message=f"Folder {params.name} created", reload_node_id=node_id or None
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
    params_model = DeleteParams

    async def run(self, node_id: str | None, params: DeleteParams) -> ActionResult:
        path = self._target(node_id)
        reload_node_id = self._parent_id(path)
        await to_thread.run_sync(partial(_remove, path, params.recursive))
        return ActionResult(
            message=f"{path.name} deleted", reload_node_id=reload_node_id
        )


class Upload(_Bound, FileAction[UploadParams]):
    name: ClassVar[str] = "upload"
    title: ClassVar[str] = "Upload a file"
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"directory"})
    params_model = UploadParams

    async def run(
        self, node_id: str | None, params: UploadParams, payload: FilePayload
    ) -> ActionResult:
        parent = self._directory(node_id)
        filename = _plain_name(payload.filename or "")
        target = parent / filename
        if target.exists() and not params.overwrite:
            raise ActionRefused("conflict", f"{filename} is already there")

        await self._stream_into(parent, target, payload)
        return ActionResult(
            message=f"{filename} uploaded", reload_node_id=node_id or None
        )

    async def _stream_into(
        self, parent: Path, target: Path, payload: FilePayload
    ) -> None:
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
            await to_thread.run_sync(partial(os.replace, path, target))
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


def _remove(path: Path, recursive: bool) -> None:
    if not path.is_dir():
        path.unlink()
        return
    if recursive:
        shutil.rmtree(path)
        return
    try:
        path.rmdir()
    except OSError:
        raise ActionRefused(
            "conflict",
            f"{path.name} is not empty; say so explicitly to delete what is inside",
        ) from None


class FileActions:
    """What a file source offers on a given node."""

    def __init__(self, session: FileSession) -> None:
        self._session = session
        self._actions = ActionSet(
            [CreateFolder(session), Upload(session), Rename(session), Delete(session)]
        )

    def action(self, name: str) -> Action[Any]:
        return self._actions.get(name)

    async def available(self, node_id: str | None) -> list[Action[Any]]:
        path = self._session.resolve(node_id)
        kind = await to_thread.run_sync(partial(_kind_of, path, node_id))
        offered = self._actions.for_kind(kind)
        if path == self._session.resolved_root:
            # The root is an ordinary directory, and its state — not its kind —
            # is what rules the two actions out.
            return [action for action in offered if not isinstance(action, _ActsOnNode)]
        return offered


def _kind_of(path: Path, node_id: str | None) -> NodeKind:
    if path.is_dir():
        return "directory"
    if path.is_file():
        return "file"
    raise ValueError(f"No such node: {node_id}")
