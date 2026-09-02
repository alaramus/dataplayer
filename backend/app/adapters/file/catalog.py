"""Walking a directory tree one level at a time."""

import os
from datetime import UTC, datetime
from functools import partial
from pathlib import Path, PurePosixPath

from anyio import to_thread

from app.adapters.catalog import (
    CatalogNode,
    DatasetNode,
    DirectoryNode,
    EntryNode,
    FileNode,
)
from app.adapters.file import archive, workbook
from app.adapters.file.formats import (
    TABLE,
    format_of,
    is_container,
    representations_inside_archive,
    representations_of,
)
from app.adapters.file.members import member_id, resolve_node
from app.adapters.file.session import FileSession
from app.adapters.protocol import AdapterError, NodeNotFound

# A schema count is bounded, a directory is not. Beyond this the listing fails
# rather than being cut short: pagination of catalog children does not exist
# yet, and pretending a directory is smaller than it is would be a lie of the
# kind the old catalog told when it answered with the parent directory.
MAX_ENTRIES = 2000


class FileCatalog:
    def __init__(self, session: FileSession) -> None:
        self._session = session

    async def list_children(self, node_id: str | None) -> list[CatalogNode]:
        if node_id is not None and node_id != "":
            resolved = await to_thread.run_sync(
                resolve_node, self._session, node_id
            )
            if resolved.member is not None:
                return await to_thread.run_sync(
                    partial(
                        self._member_nodes,
                        resolved.path,
                        node_id,
                        inside=resolved.member,
                    )
                )
        path = self._session.resolve(node_id)
        return await to_thread.run_sync(self._list, path, node_id)

    def _list(self, path: Path, node_id: str | None) -> list[CatalogNode]:
        if not path.exists():
            if node_id is None:
                raise AdapterError(
                    "config", "The directory of this connector does not exist"
                )
            raise ValueError(f"No such directory: {node_id}")
        if node_id is not None and path.is_file() and is_container(path.name):
            # A container is opened once here, and what is inside it becomes
            # nodes of its own (D51, D53). This is the one place a file is read
            # while listing, and it happens because the user asked for it.
            return self._member_nodes(path, node_id, inside=None)
        if not path.is_dir():
            raise ValueError(f"Not a directory: {node_id}")

        try:
            entries = list(os.scandir(path))
        except OSError:
            raise AdapterError("unknown", "Could not read the directory") from None

        if len(entries) > MAX_ENTRIES:
            raise AdapterError(
                "unknown",
                f"The directory holds more than {MAX_ENTRIES} entries; "
                "pagination of catalog children is not implemented yet",
            )

        nodes = [node for node in map(self._node, entries) if node is not None]
        nodes.sort(key=lambda node: (node.kind != "directory", node.name.casefold()))
        return nodes

    async def path_to(self, node_id: str) -> list[CatalogNode]:
        return await to_thread.run_sync(self._walk, node_id)

    def _walk(self, node_id: str) -> list[CatalogNode]:
        """The node and every directory above it, root first.

        The root itself is left out: it is the connector. `resolve` has
        already judged containment, so what is left is to confirm the node is
        there and to describe each step — one stat per level, and a path is a
        handful of levels.

        A member of a container file has one step more: the file it is in, and
        then the member itself, described exactly as the file's listing does.
        """
        resolved = resolve_node(self._session, node_id)
        if not resolved.path.exists():
            raise NodeNotFound(node_id)

        container_id = (
            node_id
            if resolved.member is None
            else _above(node_id, resolved.member)
        )
        parts = PurePosixPath(container_id).parts
        nodes: list[CatalogNode] = []
        for depth in range(1, len(parts) + 1):
            step = self._session.resolve("/".join(parts[:depth]))
            node = self._node_at(step)
            if node is None:
                raise NodeNotFound(node_id)
            nodes.append(node)

        if resolved.member is not None:
            nodes.extend(self._member_path(resolved.path, container_id, node_id))
        return nodes

    def _member_path(
        self, path: Path, container_id: str, node_id: str
    ) -> list[CatalogNode]:
        """Every step inside a container, from its first level to the node."""
        member = PurePosixPath(node_id).relative_to(container_id).as_posix()
        if format_of(path.name) != "archive":
            found = next(
                (
                    node
                    for node in self._member_nodes(path, container_id, inside=None)
                    if node.id == node_id
                ),
                None,
            )
            if found is None:
                raise NodeNotFound(node_id)
            return [found]

        steps: list[CatalogNode] = []
        parts = PurePosixPath(member).parts
        for depth in range(1, len(parts) + 1):
            inside = "/".join(parts[:depth])
            try:
                entry = archive.entry_at(path, inside)
            except ValueError:
                raise NodeNotFound(node_id) from None
            steps.append(_entry_node(container_id, entry))
        return steps

    def _member_nodes(
        self, path: Path, node_id: str, *, inside: str | None
    ) -> list[CatalogNode]:
        """What one container holds, one level at a time.

        A workbook holds sheets and nothing below them; an archive holds a tree,
        so the level being looked at is part of the question.
        """
        if format_of(path.name) == "archive":
            container_id = node_id if inside is None else _above(node_id, inside)
            return [
                _entry_node(container_id, entry)
                for entry in archive.children(path, inside)
            ]
        return [
            DatasetNode(
                id=member_id(node_id, str(facts.position)),
                name=facts.title,
                representations=[TABLE],
                describable=True,
                summarizable=True,
                row_count=facts.rows,
                column_count=facts.columns,
                hidden=facts.hidden,
            )
            for facts in workbook.sheets(path)
        ]

    def _node(self, entry: os.DirEntry[str]) -> CatalogNode | None:
        """One entry of a listing, or None for one this source does not own.

        Takes the facts from the directory entry, which already carries them:
        asking the path again would cost one more stat per entry, and a
        listing may hold two thousand.
        """
        try:
            return self._describe(
                Path(entry.path), entry.name, entry.stat(), entry.is_dir()
            )
        except OSError:
            return None

    def _node_at(self, path: Path) -> CatalogNode | None:
        """One node named by its path, for a walk that has no listing to read."""
        try:
            return self._describe(path, path.name, path.stat(), path.is_dir())
        except OSError:
            return None

    def _describe(
        self, path: Path, name: str, stat: os.stat_result, is_directory: bool
    ) -> CatalogNode | None:
        """A node from facts already gathered, or None for what is not ours.

        A symlink pointing out of the root is not part of the source, and a
        broken one cannot be described at all. Both answer None; everything
        else that goes wrong is the caller's to raise.
        """
        if not path.resolve().is_relative_to(self._session.resolved_root):
            return None

        node_id = self._session.relative_id(path)
        modified_at = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
        if is_directory:
            return DirectoryNode(
                id=node_id,
                name=name,
                has_children=_has_entries(str(path)),
                modified_at=modified_at,
                representations=[],
                summarizable=True,
            )
        return FileNode(
            id=node_id,
            name=name,
            # A workbook holds sheets, and they are read only when this node
            # is walked into.
            has_children=is_container(name),
            size_bytes=stat.st_size,
            modified_at=modified_at,
            representations=representations_of(name),
            # A delimited header is editable structure even though it carries
            # no source types beyond text.
            describable=format_of(name) in {"parquet", "delimited"},
            # Every node of this source answers what it is, whatever it can be
            # opened as — which is the point of D75.
            summarizable=True,
        )


def _entry_node(container_id: str, entry: archive.Entry) -> CatalogNode:
    """One member of an archive as a node the client can walk into or open."""
    return EntryNode(
        id=member_id(container_id, entry.path),
        name=entry.name,
        has_children=entry.is_directory,
        representations=(
            representations_inside_archive(entry.name) if entry.readable else []
        ),
        size_bytes=None if entry.is_directory else entry.size_bytes,
        compressed_bytes=None if entry.is_directory else entry.compressed_bytes,
        modified_at=entry.modified_at,
        is_link=entry.is_link,
        is_encrypted=entry.is_encrypted,
        summarizable=True,
    )


def _above(node_id: str, member: str) -> str:
    """The id of the container a member is in, taken off the member's own id."""
    return node_id[: -(len(member) + 1)]


def _has_entries(path: str) -> bool:
    """Whether a directory holds anything, at the cost of one entry read.

    Claiming children unconditionally would show an expander on every empty
    directory; counting them all would cost a full listing per node.
    """
    try:
        with os.scandir(path) as entries:
            return next(entries, None) is not None
    except OSError:
        return False
