"""Walking a tree of files one level at a time."""

from pathlib import PurePosixPath

from anyio import to_thread

from app.adapters.catalog import (
    CatalogNode,
    DatasetNode,
    DirectoryNode,
    EntryNode,
    FileNode,
)
from app.adapters.explorer import archive, workbook
from app.adapters.explorer.formats import (
    TABLE,
    format_of,
    is_container,
    representations_inside_archive,
    representations_of,
)
from app.adapters.explorer.members import member_id, resolve_node
from app.adapters.explorer.storage import (
    ROOT,
    Entry,
    Place,
    Storage,
    ancestors,
    node_id_of,
)
from app.adapters.protocol import AdapterError, NodeNotFound

# A schema count is bounded, a directory is not. Beyond this the listing fails
# rather than being cut short: pagination of catalog children does not exist
# yet, and pretending a directory is smaller than it is would be a lie of the
# kind the old catalog told when it answered with the parent directory.
MAX_ENTRIES = 2000


class ExplorerCatalog:
    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    async def list_children(self, node_id: str | None) -> list[CatalogNode]:
        return await to_thread.run_sync(self._list_children, node_id)

    def _list_children(self, node_id: str | None) -> list[CatalogNode]:
        if node_id is not None and node_id != "":
            resolved = resolve_node(self._storage, node_id)
            if resolved.member is not None:
                return self._member_nodes(
                    resolved.place, node_id, inside=resolved.member
                )
        place = self._storage.place(node_id)
        return self._list(place, node_id)

    def _list(self, place: Place, node_id: str | None) -> list[CatalogNode]:
        found = self._storage.entry(place)
        if found is None:
            if node_id is None:
                raise AdapterError(
                    "config", "The directory of this connector does not exist"
                )
            raise ValueError(f"No such directory: {node_id}")
        if place != ROOT and not found.is_directory and is_container(place.name):
            # A container is opened once here, and what is inside it becomes
            # nodes of its own (D51, D53). This is the one place a file is read
            # while listing, and it happens because the user asked for it.
            return self._member_nodes(place, node_id or "", inside=None)
        if not found.is_directory:
            raise ValueError(f"Not a directory: {node_id}")

        try:
            entries = self._storage.entries(place)
        except OSError:
            raise AdapterError("unknown", "Could not read the directory") from None

        if len(entries) > MAX_ENTRIES:
            raise AdapterError(
                "unknown",
                f"The directory holds more than {MAX_ENTRIES} entries; "
                "pagination of catalog children is not implemented yet",
            )

        nodes = [node_of(self._storage, entry) for entry in entries]
        nodes.sort(key=lambda node: (node.kind != "directory", node.name.casefold()))
        return nodes

    async def path_to(self, node_id: str) -> list[CatalogNode]:
        return await to_thread.run_sync(self._walk, node_id)

    def _walk(self, node_id: str) -> list[CatalogNode]:
        """The node and every directory above it, root first.

        The root itself is left out: it is the connector. `place` has already
        judged containment, so what is left is to confirm the node is there
        and to describe each step — one look per level, and a path is a
        handful of levels.

        A member of a container file has one step more: the file it is in, and
        then the member itself, described exactly as the file's listing does.
        """
        resolved = resolve_node(self._storage, node_id)
        if resolved.entry is None:
            raise NodeNotFound(node_id)

        container_id = (
            node_id
            if resolved.member is None
            else _above(node_id, resolved.member)
        )
        nodes: list[CatalogNode] = []
        for step in ancestors(self._storage, resolved.place):
            entry = self._storage.entry(step)
            if entry is None:
                raise NodeNotFound(node_id)
            nodes.append(node_of(self._storage, entry))

        if resolved.member is not None:
            nodes.extend(self._member_path(resolved.place, container_id, node_id))
        return nodes

    def _member_path(
        self, place: Place, container_id: str, node_id: str
    ) -> list[CatalogNode]:
        """Every step inside a container, from its first level to the node."""
        member = PurePosixPath(node_id).relative_to(container_id).as_posix()
        if format_of(place.name) != "archive":
            found = next(
                (
                    node
                    for node in self._member_nodes(place, container_id, inside=None)
                    if node.id == node_id
                ),
                None,
            )
            if found is None:
                raise NodeNotFound(node_id)
            return [found]

        steps: list[CatalogNode] = []
        parts = PurePosixPath(member).parts
        with self._storage.local_file(place) as path:
            for depth in range(1, len(parts) + 1):
                inside = "/".join(parts[:depth])
                try:
                    entry = archive.entry_at(path, inside)
                except ValueError:
                    raise NodeNotFound(node_id) from None
                steps.append(_entry_node(container_id, entry))
        return steps

    def _member_nodes(
        self, place: Place, node_id: str, *, inside: str | None
    ) -> list[CatalogNode]:
        """What one container holds, one level at a time.

        A workbook holds sheets and nothing below them; an archive holds a tree,
        so the level being looked at is part of the question.
        """
        with self._storage.local_file(place) as path:
            if format_of(place.name) == "archive":
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


def node_of(storage: Storage, entry: Entry) -> CatalogNode:
    """A node from what the storage says of one place.

    Module level rather than a method because three readers need the identical
    answer: the listing of a level, the walk back up to one, and the search
    (D76). A node that differed between them would be a row that behaved
    differently depending on how it was found.
    """
    node_id = node_id_of(entry.place) or ""
    if entry.is_directory:
        return DirectoryNode(
            id=node_id,
            name=entry.name,
            has_children=storage.has_entries(entry.place),
            modified_at=entry.modified_at,
            representations=[],
            summarizable=True,
        )
    return FileNode(
        id=node_id,
        name=entry.name,
        # A workbook holds sheets, and they are read only when this node is
        # walked into.
        has_children=is_container(entry.name),
        size_bytes=entry.size_bytes,
        modified_at=entry.modified_at,
        representations=representations_of(entry.name),
        # A delimited header is editable structure even though it carries no
        # source types beyond text.
        describable=format_of(entry.name) in {"parquet", "delimited"},
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

