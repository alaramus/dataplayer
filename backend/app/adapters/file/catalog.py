"""Walking a directory tree one level at a time."""

import os
from datetime import UTC, datetime
from pathlib import Path

from anyio import to_thread

from app.adapters.catalog import CatalogNode, DirectoryNode, FileNode
from app.adapters.file.readers import classify
from app.adapters.file.session import FileSession
from app.adapters.protocol import AdapterError

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

    def _node(self, entry: os.DirEntry[str]) -> CatalogNode | None:
        """One entry, or None for an entry this source does not own.

        A symlink pointing out of the root is not part of the source, and a
        broken one cannot be described at all. Both are left out; everything
        else that goes wrong fails the whole listing.
        """
        try:
            if not Path(entry.path).resolve().is_relative_to(self._session.resolved_root):
                return None
            stat = entry.stat()
            is_directory = entry.is_dir()
        except OSError:
            return None

        node_id = self._session.relative_id(Path(entry.path))
        modified_at = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
        if is_directory:
            return DirectoryNode(
                id=node_id,
                name=entry.name,
                has_children=_has_entries(entry.path),
                modified_at=modified_at,
            )
        return FileNode(
            id=node_id,
            name=entry.name,
            size_bytes=stat.st_size,
            modified_at=modified_at,
            content_kind=classify(entry.name),
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
