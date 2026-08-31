"""Reading a node id that may name something inside a file.

A workbook holds sheets, and a sheet is a catalog node of its own (D51). Its id
is the workbook's id plus one more segment, so every id in this source is still
a relative path judged by the containment rule of D8 — the extra segment is
read only after that rule has been applied to the whole of it.

The split happens only when the whole id names nothing on disk, and at the
longest prefix that is a container. A directory called `book.xlsx` holding a
file called `1` therefore keeps its ordinary meaning, and no id can mean two
things at once. What follows the container is one segment for a workbook sheet
and a path for an archive entry (D53), and it has already passed the
containment rule as part of the whole id.
"""

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from app.adapters.file.formats import is_container
from app.adapters.file.session import FileSession


@dataclass(frozen=True)
class ResolvedNode:
    """Where a node id lands: a path, and what of it was named inside."""

    path: Path
    # The segment naming a member of `path`, or None when the id is the path.
    member: str | None

    @property
    def is_member(self) -> bool:
        return self.member is not None


def resolve_node(session: FileSession, node_id: str) -> ResolvedNode:
    """The path a node id names, and the member inside it when there is one.

    Blocking: it asks the filesystem what exists. Raises ValueError for an id
    that leaves the root, exactly as `FileSession.resolve` does, and for one
    whose container is not a file that can hold members.
    """
    path = session.resolve(node_id)
    if path.exists():
        return ResolvedNode(path=path, member=None)

    parts = PurePosixPath(node_id).parts
    # The longest prefix first, so an archive inside a folder is found before
    # the folder is, and a member path may itself have several segments.
    for cut in range(len(parts) - 1, 0, -1):
        container = session.resolve("/".join(parts[:cut]))
        if container.is_file() and is_container(container.name):
            return ResolvedNode(path=container, member="/".join(parts[cut:]))
    # Not a container: the id names something that is simply not there, and
    # the caller's own "no such node" message is the honest answer.
    return ResolvedNode(path=path, member=None)


def member_id(container_id: str, member: str) -> str:
    """The id of one member, composed by the source and never by a client."""
    return f"{container_id}/{member}"
