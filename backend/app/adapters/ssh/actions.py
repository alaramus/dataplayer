"""Changing what is on a server: the five things the file source does (D144).

The forms are the file source's own: a new folder, an upload, a rename and a
delete ask the same questions of a folder on a server as of one in personal
storage, and a second copy of each would drift. What differs is how each is
carried out — over SFTP, and never by running a command, so no name typed
into a form is ever read by a shell.
"""

import posixpath
import stat
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any, ClassVar, Protocol

import asyncssh

from app.adapters.actions import (
    CHUNK_BYTES,
    Action,
    ActionDownload,
    ActionDownloadMetadata,
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
from app.adapters.file.actions import (
    DeleteParams,
    DownloadParams,
    NameParams,
    RenameParams,
    UploadParams,
)
from app.adapters.file.session import is_plain_name
from app.adapters.ssh.session import Remote, SshSession
from app.core.access import Access
from app.core.config import settings


class _Bound:
    """Common to every action here: the session it works through."""

    def __init__(self, session: SshSession) -> None:
        self._session = session


class _ActsOnNode(_Bound):
    """Changes the node it is given rather than what is inside it.

    Which is what keeps the folder a connection stands in safe: it can be added
    to, never renamed or removed — the rule the file source keeps for its root.
    """

    acts_on: ClassVar[ActsOn] = "node"

    @staticmethod
    def _below_root(node_id: str | None) -> str:
        if node_id is None or node_id == "":
            raise ActionRefused(
                "not_applicable", "The folder a connection starts in cannot be changed"
            )
        return node_id


class CreateFolder(_Bound, JsonAction[NameParams]):
    name: ClassVar[str] = "create_folder"
    title: ClassVar[str] = "New folder"
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"directory"})
    acts_on: ClassVar[ActsOn] = "children"
    params_model = NameParams

    async def run(self, node_id: str | None, params: NameParams) -> ActionResult:
        async with self._session.remote() as remote:
            parent = remote.path_of(node_id)
            target = await _available(remote, parent, params.name)
            await remote.sftp.mkdir(target)
        return ActionResult(
            message=f"Folder {posixpath.basename(target)} created",
            reload_node_ids=[node_id or None],
        )


class Rename(_ActsOnNode, JsonAction[RenameParams]):
    name: ClassVar[str] = "rename"
    title: ClassVar[str] = "Rename"
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"directory", "file"})
    params_model = RenameParams

    async def run(self, node_id: str | None, params: RenameParams) -> ActionResult:
        below = self._below_root(node_id)
        async with self._session.remote() as remote:
            path = remote.path_of(below)
            target = posixpath.join(posixpath.dirname(path), params.new_name)
            if await remote.sftp.exists(target):
                raise ActionRefused("conflict", f"{params.new_name} is already there")
            await remote.sftp.rename(path, target)
        return ActionResult(
            message=f"Renamed to {params.new_name}",
            reload_node_ids=[_parent_id(below)],
        )


class Delete(_ActsOnNode, JsonAction[DeleteParams]):
    name: ClassVar[str] = "delete"
    title: ClassVar[str] = "Delete"
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"directory", "file"})
    destructive: ClassVar[bool] = True
    bulk: ClassVar[bool] = True
    params_model = DeleteParams

    async def run(self, node_id: str | None, params: DeleteParams) -> ActionResult:
        below = self._below_root(node_id)
        async with self._session.remote() as remote:
            path = remote.path_of(below)
            # Asked without following a link: removing a link removes the link,
            # never the folder it points at.
            attrs = await remote.sftp.lstat(path)
            if attrs.permissions is not None and stat.S_ISDIR(attrs.permissions):
                await remote.sftp.rmtree(path)
            else:
                await remote.sftp.remove(path)
        return ActionResult(
            message=f"{posixpath.basename(path)} deleted",
            reload_node_ids=[_parent_id(below)],
        )


class Download(_ActsOnNode, Action[DownloadParams]):
    """One file, exactly as the server holds it."""

    name: ClassVar[str] = "download"
    title: ClassVar[str] = "Download"
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"file"})
    requires: ClassVar[Access] = "read"
    params_model = DownloadParams

    async def download(
        self, node_ids: Sequence[str], raw: Mapping[str, Any]
    ) -> ActionDownload:
        self._validated(raw)
        if len(node_ids) != 1:
            raise ActionRefused(
                "not_applicable", "Files on a server are downloaded one at a time"
            )
        below = self._below_root(node_ids[0])
        async with self._session.remote() as remote:
            attrs = await remote.sftp.stat(remote.path_of(below))
        if attrs.permissions is not None and not stat.S_ISREG(attrs.permissions):
            raise ActionRefused("not_applicable", "Only a file can be downloaded")
        return ActionDownload(
            metadata=ActionDownloadMetadata(
                filename=posixpath.basename(below),
                media_type="application/octet-stream",
                size_bytes=attrs.size or 0,
            ),
            body=self._bytes(below),
        )

    async def _bytes(self, node_id: str) -> AsyncIterator[bytes]:
        """The file, read as the browser takes it rather than all at once.

        Opened again here, because this runs after the request that prepared
        the download has answered — through the connection the connector keeps.
        """
        async with self._session.remote() as remote:
            async with remote.sftp.open(
                remote.path_of(node_id), "rb", encoding=None
            ) as handle:
                while chunk := await handle.read(CHUNK_BYTES):
                    yield chunk if isinstance(chunk, bytes) else chunk.encode()


class Upload(_Bound, FileAction[UploadParams]):
    name: ClassVar[str] = "upload"
    title: ClassVar[str] = "Upload files"
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"directory"})
    acts_on: ClassVar[ActsOn] = "children"
    many_files: ClassVar[bool] = True
    params_model = UploadParams

    async def run(
        self, node_id: str | None, params: UploadParams, payload: FilePayload
    ) -> ActionResult:
        filename = (payload.filename or "").strip()
        if not is_plain_name(filename):
            raise ValueError("A name must be a single plain name, without separators")
        async with self._session.remote() as remote:
            parent = remote.path_of(node_id)
            target = posixpath.join(parent, filename)
            if await remote.sftp.exists(target):
                if params.conflict == "refuse":
                    raise ActionRefused("conflict", f"{filename} is already there")
                if params.conflict == "rename":
                    target = await _available(remote, parent, filename, numbered=True)
            # Written beside its destination and moved into place, so nobody
            # reading the folder sees half a file under the real name, and a
            # refused upload leaves nothing behind.
            temporary = posixpath.join(parent, f".upload-{filename}")
            try:
                await _write(remote, temporary, payload)
                if params.conflict == "replace":
                    await _replace(remote, temporary, target)
                else:
                    try:
                        # A plain SFTP rename refuses a name that is taken, so
                        # one that appeared since the check is refused here
                        # rather than overwritten.
                        await remote.sftp.rename(temporary, target)
                    except asyncssh.SFTPFailure:
                        raise ActionRefused(
                            "conflict", f"{posixpath.basename(target)} is already there"
                        ) from None
            except BaseException:
                try:
                    await remote.sftp.remove(temporary)
                except asyncssh.SFTPError:
                    pass
                raise
        return ActionResult(
            message=f"{posixpath.basename(target)} uploaded",
            reload_node_ids=[node_id or None],
        )


async def _write(remote: Remote, path: str, payload: FilePayload) -> None:
    """Stream the upload to the server, counting what arrives rather than
    trusting a size the client claimed."""
    written = 0
    async with remote.sftp.open(path, "wb", encoding=None) as handle:
        while chunk := await payload.read(CHUNK_BYTES):
            written += len(chunk)
            if written > settings.MAX_UPLOAD_BYTES:
                raise ActionRefused(
                    "too_large", "The file is larger than this server accepts"
                )
            await handle.write(chunk)


async def _replace(remote: Remote, temporary: str, target: str) -> None:
    """Put the upload in place of what is there, in one step where the server
    can: OpenSSH's own rename replaces atomically, the protocol's does not."""
    try:
        await remote.sftp.posix_rename(temporary, target)
    except asyncssh.SFTPOpUnsupported:
        if await remote.sftp.exists(target):
            await remote.sftp.remove(target)
        await remote.sftp.rename(temporary, target)


async def _available(
    remote: Remote, parent: str, name: str, *, numbered: bool = False
) -> str:
    """A path in `parent` that nothing holds yet, numbered the way the file
    source numbers a folder or a copy."""
    candidate = posixpath.join(parent, name)
    number = 1
    while await remote.sftp.exists(candidate):
        if numbered:
            stem, dot, suffix = name.rpartition(".")
            copy = f"{stem} ({number}).{suffix}" if dot and stem else f"{name} ({number})"
        else:
            copy = f"{name} ({number})"
        candidate = posixpath.join(parent, copy)
        number += 1
    return candidate


def _parent_id(node_id: str) -> str | None:
    """The node whose children changed, as the client names it."""
    parent = posixpath.dirname(node_id)
    return parent or None


class SshActionType(ActionType, Protocol):
    def __call__(self, session: SshSession) -> Action[Any]: ...


# Two readers, one tuple: `SshActions` builds its set from it, and the registry
# reads the titles off it to say what the type can do.
SSH_ACTION_TYPES: tuple[SshActionType, ...] = (
    CreateFolder,
    Upload,
    Download,
    Rename,
    Delete,
)


class SshActions:
    """What an SSH source offers on a given node."""

    def __init__(self, session: SshSession) -> None:
        self._session = session
        self._actions = ActionSet([action_type(session) for action_type in SSH_ACTION_TYPES])

    def action(self, name: str) -> Action[Any]:
        return self._actions.get(name)

    async def all_actions(self) -> list[Action[Any]]:
        return list(self._actions)

    async def available(self, node_id: str | None) -> list[Action[Any]]:
        if node_id in (None, ""):
            return [
                action
                for action in self._actions.for_kind("directory")
                if not isinstance(action, _ActsOnNode)
            ]
        async with self._session.remote() as remote:
            try:
                attrs = await remote.sftp.stat(remote.path_of(node_id))
            except asyncssh.SFTPNoSuchFile:
                raise ValueError(f"No such node: {node_id}") from None
        kind: NodeKind = (
            "directory"
            if attrs.permissions is not None and stat.S_ISDIR(attrs.permissions)
            else "file"
        )
        return self._actions.for_kind(kind)
