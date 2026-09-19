"""Reading a node id that may name something inside a file.

A workbook holds sheets, and a sheet is a catalog node of its own (D51). Its id
is the workbook's id plus one more segment, so every id in this source is still
a relative path judged by the containment rule of D8 — the extra segment is
read only after that rule has been applied to the whole of it.

The split happens only when the whole id names nothing in the storage, and at
the longest prefix that is a container. A directory called `book.xlsx` holding
a file called `1` therefore keeps its ordinary meaning, and no id can mean two
things at once. What follows the container is one segment for a workbook sheet
and a path for an archive entry (D53), and it has already passed the
containment rule as part of the whole id.
"""

from dataclasses import dataclass
from pathlib import PurePosixPath

from app.adapters.explorer.formats import is_container
from app.adapters.explorer.storage import Entry, Place, Storage


@dataclass(frozen=True)
class ResolvedNode:
    """Where a node id lands: a place, and what of it was named inside."""

    place: Place
    # The segment naming a member of `place`, or None when the id is the place.
    member: str | None
    # What is at `place`, or None when nothing is.
    entry: Entry | None

    @property
    def is_member(self) -> bool:
        return self.member is not None

    @property
    def name(self) -> str:
        return self.place.name


def resolve_node(storage: Storage, node_id: str) -> ResolvedNode:
    """The place a node id names, and the member inside it when there is one.

    Blocking: it asks the storage what exists. Raises ValueError for an id
    that leaves the root, exactly as `Storage.place` does.
    """
    place = storage.place(node_id)
    entry = storage.entry(place)
    if entry is not None:
        return ResolvedNode(place=place, member=None, entry=entry)

    parts = PurePosixPath(node_id).parts
    # The longest prefix first, so an archive inside a folder is found before
    # the folder is, and a member path may itself have several segments.
    for cut in range(len(parts) - 1, 0, -1):
        try:
            container = storage.place("/".join(parts[:cut]))
        except ValueError:
            # A prefix of an id a storage names by id rather than by path
            # need not be an id of its own.
            continue
        found = storage.entry(container)
        if found is not None and not found.is_directory and is_container(container.name):
            return ResolvedNode(
                place=container, member="/".join(parts[cut:]), entry=found
            )
    # Not a container: the id names something that is simply not there, and
    # the caller's own "no such node" message is the honest answer.
    return ResolvedNode(place=place, member=None, entry=None)


def member_id(container_id: str, member: str) -> str:
    """The id of one member, composed by the source and never by a client."""
    return f"{container_id}/{member}"
