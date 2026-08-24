"""Walking a directory tree one level at a time."""

import os
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from anyio import to_thread

from app.adapters.catalog import CatalogNode, DirectoryNode, FileNode
from app.adapters.file.readers import classify
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
        path = self._session.resolve(node_id)
        return await to_thread.run_sync(self._list, path, node_id)

    def _list(self, path: Path, node_id: str | None) -> list[CatalogNode]:
        if not path.exists():
            if node_id is None:
                raise AdapterError(
                    "config", "The directory of this connector does not exist"
                )
            raise ValueError(f"No such directory: {node_id}")
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
        path = self._session.resolve(node_id)
        return await to_thread.run_sync(self._walk, path, node_id)

    def _walk(self, path: Path, node_id: str) -> list[CatalogNode]:
        """The node and every directory above it, root first.

        The root itself is left out: it is the connector. `resolve` has
        already judged containment, so what is left is to confirm the node is
        there and to describe each step — one stat per level, and a path is a
        handful of levels.
        """
        if not path.exists():
            raise NodeNotFound(node_id)

        parts = PurePosixPath(node_id).parts
        nodes: list[CatalogNode] = []
        for depth in range(1, len(parts) + 1):
            step = self._session.resolve("/".join(parts[:depth]))
            node = self._node_at(step)
            if node is None:
                raise NodeNotFound(node_id)
            nodes.append(node)
        return nodes

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
            )
        return FileNode(
            id=node_id,
            name=name,
            size_bytes=stat.st_size,
            modified_at=modified_at,
            content_kind=classify(name),
        )


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
