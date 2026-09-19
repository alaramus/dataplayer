"""Walking a server's folders one level at a time, over SFTP (D144)."""

import stat
from datetime import UTC, datetime

import asyncssh

from app.adapters.catalog import CatalogNode, DirectoryNode, FileNode
from app.adapters.content import NodeRepresentation
from app.adapters.explorer.formats import MARKDOWN, TEXT, format_of
from app.adapters.explorer.storage import is_plain_name
from app.adapters.protocol import AdapterError, NodeNotFound
from app.adapters.ssh.session import Remote, SshSession

# A folder is not bounded, and there is no paging of catalog children: past
# this the listing is refused rather than cut short, the rule the file source
# keeps (D2a).
MAX_ENTRIES = 2000


def representations_of(name: str) -> list[NodeRepresentation]:
    """What a remote file may be opened as: its text, and a document for Markdown.

    Decided by the name, by the same rules the file source uses, and narrowed
    to what this source reads — text, a whole page at a time. A table, an
    image or a player over SFTP are later slices, and a file offering one it
    cannot open would be a button that fails.
    """
    match format_of(name):
        case "markdown":
            return [MARKDOWN, TEXT]
        case "text" | "log" | "delimited" | "json" | "jsonl":
            return [TEXT]
        case _:
            return []


class SshCatalog:
    def __init__(self, session: SshSession) -> None:
        self._session = session

    async def list_children(self, node_id: str | None) -> list[CatalogNode]:
        async with self._session.remote() as remote:
            path = remote.path_of(node_id)
            try:
                entries = await remote.sftp.readdir(path)
            except asyncssh.SFTPNoSuchFile:
                if node_id in (None, ""):
                    raise AdapterError(
                        "config", "The folder of this connection does not exist"
                    ) from None
                raise ValueError(f"No such folder: {node_id}") from None
            named = [entry for entry in entries if entry.filename not in (".", "..")]
            if len(named) > MAX_ENTRIES:
                raise AdapterError(
                    "unknown",
                    f"The folder holds more than {MAX_ENTRIES} entries; "
                    "pagination of catalog children is not implemented yet",
                )
            nodes: list[CatalogNode] = []
            for entry in named:
                node = await _node(remote, node_id, str(entry.filename), entry.attrs)
                if node is not None:
                    nodes.append(node)
        nodes.sort(key=lambda node: (node.kind != "directory", node.name.casefold()))
        return nodes

    async def path_to(self, node_id: str) -> list[CatalogNode]:
        """The node and every folder above it, root first and the root left out."""
        async with self._session.remote() as remote:
            remote.path_of(node_id)
            parts = node_id.split("/")
            nodes: list[CatalogNode] = []
            for depth in range(1, len(parts) + 1):
                step = "/".join(parts[:depth])
                try:
                    attrs = await remote.sftp.stat(remote.path_of(step))
                except asyncssh.SFTPNoSuchFile:
                    raise NodeNotFound(node_id) from None
                parent = "/".join(parts[: depth - 1]) or None
                nodes.append(_described(parent, parts[depth - 1], attrs))
        return nodes


async def _node(
    remote: Remote, parent_id: str | None, name: str, attrs: asyncssh.SFTPAttrs
) -> CatalogNode | None:
    """One entry of a listing, or None for one this source will not show.

    A link is described by what it points at, which is one more question to
    the server; a broken one cannot be described at all and is left out, as
    the file source leaves one out.
    """
    if not is_plain_name(name):
        # A name the path rule refuses could never be opened again by its id.
        return None
    if attrs.permissions is not None and stat.S_ISLNK(attrs.permissions):
        child = name if parent_id in (None, "") else f"{parent_id}/{name}"
        try:
            attrs = await remote.sftp.stat(remote.path_of(child))
        except asyncssh.SFTPError:
            return None
    return _described(parent_id, name, attrs)


def _described(
    parent_id: str | None, name: str, attrs: asyncssh.SFTPAttrs
) -> CatalogNode:
    node_id = name if parent_id in (None, "") else f"{parent_id}/{name}"
    modified_at = (
        datetime.fromtimestamp(attrs.mtime, tz=UTC) if attrs.mtime is not None else None
    )
    if _is_directory(attrs):
        # Claimed to have children rather than asked: asking would be one more
        # round trip per folder of a listing, and a listing may hold two
        # thousand of them.
        return DirectoryNode(
            id=node_id,
            name=name,
            has_children=True,
            modified_at=modified_at,
            representations=[],
        )
    return FileNode(
        id=node_id,
        name=name,
        size_bytes=attrs.size or 0,
        modified_at=modified_at,
        representations=representations_of(name),
    )


def _is_directory(attrs: asyncssh.SFTPAttrs) -> bool:
    if attrs.permissions is not None:
        return stat.S_ISDIR(attrs.permissions)
    return attrs.type == asyncssh.FILEXFER_TYPE_DIRECTORY
