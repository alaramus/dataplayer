"""Where a tree of files is kept, and the one way the explorer reaches it (D150).

Everything the explorer does — the catalog, formats read as text or tables,
SQL, the editor, search, actions — is written once, over this. A source that is
a tree of files brings a storage: the server's own disk under a person's home,
an SSH server over SFTP, whatever comes next. The storage says where a node is
and moves bytes there and back; the explorer says what the bytes are.

Blocking, and called from worker threads only (D151). The explorer's walks and
the libraries formats are read with are synchronous; a storage whose library
is asynchronous brings its answers into the thread, rather than the explorer
being written a second time.

A place is opaque to the explorer. It is what a node id becomes once the
storage has judged it, and the explorer never builds one by joining strings: a
folder's child, a node's parent and whether one node is inside another are
the storage's to answer. A disk names a node by its path below the root, and a
store that names files by id — where two files in one folder may share a name
— names it by that id; the explorer is the same over both.
"""

from collections.abc import Iterator
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import BinaryIO, Protocol, runtime_checkable

from app.adapters.actions import ConnectorDraft
from app.adapters.protocol import ConnectionCheckResult
from app.core.translation import say


@dataclass(frozen=True)
class Place:
    """A node as its storage names it.

    `key` is the storage's own name for the node, and the node id a client
    holds is built from it; `name` is what a person reads. The root of every
    storage is `ROOT`, whatever the storage calls it inside.
    """

    key: str
    name: str


ROOT = Place(key="", name="")


def node_id_of(place: Place) -> str | None:
    """The node id of a place, as the client gets it back; the root has none."""
    return None if place == ROOT else place.key


def is_plain_name(part: str) -> bool:
    """A string that names one entry and nothing else.

    Judged by the rules of both platforms at once, so a node id means the same
    thing everywhere. On Windows a segment like "C:" is a drive reference and
    joining silently drops everything before it, turning one path into another
    without any error — the segment is refused instead. A separator of either
    platform makes it more than one entry, which is equally refused.

    Public because a name typed into a form — a new folder, the target of a
    rename, the name of an uploaded file — is the same kind of string as a
    path segment and must not get a second rule.
    """
    return (
        part not in {"", ".", ".."}
        and not PureWindowsPath(part).drive
        and not PureWindowsPath(part).root
        and len(PureWindowsPath(part).parts) == 1
        and len(PurePosixPath(part).parts) == 1
    )


def stays_inside_root(relative: str) -> bool:
    """Whether a relative path can only ever land inside the root it joins.

    Used both for a node id and by the options of a source for the folder it
    points at, so both judge a path by one rule.
    """
    path = PurePosixPath(relative)
    return not path.is_absolute() and all(map(is_plain_name, path.parts))


@dataclass(frozen=True)
class Entry:
    """What a storage knows of one place without opening it.

    The facts are of what a link points at, as reading it gives it; `is_link`
    says the place itself is one, which is what a walk refuses to go down.
    """

    place: Place
    is_directory: bool
    size_bytes: int
    modified_at: datetime | None
    is_link: bool = False
    # What a summary states beyond a listing, where the storage keeps it.
    accessed_at: datetime | None = None
    created_at: datetime | None = None
    permissions: str | None = None

    @property
    def name(self) -> str:
        return self.place.name


class VersionChanged(Exception):
    """The file is no longer the version a write was prepared against."""


@dataclass(frozen=True)
class SearchLimits:
    """What a search by content may read: per file, and for the whole search.

    A storage's own, because reading a file costs a disk read on one and a
    transfer on another.
    """

    file_bytes: int
    total_bytes: int


# The local disk reads a file where it lies.
LOCAL_SEARCH = SearchLimits(file_bytes=8 * 1024 * 1024, total_bytes=256 * 1024 * 1024)
# A remote storage sends every byte it is asked for over the network, so a
# search there reads only small files, and far fewer of them (D152).
REMOTE_SEARCH = SearchLimits(file_bytes=1024 * 1024, total_bytes=32 * 1024 * 1024)


@runtime_checkable
class Storage(Protocol):
    """A tree of files below one root. Every method blocks.

    Failures of the storage itself are OSError, as a disk's are, so a walk can
    leave out what it cannot read in one place for every storage. A name that
    is taken is FileExistsError, a place that is not there FileNotFoundError.
    """

    # What a search by content may read here.
    search_limits: SearchLimits

    def check(self) -> ConnectionCheckResult: ...

    # --- where a node is -------------------------------------------------------

    def place(self, node_id: str | None) -> Place:
        """Where an id lands, or ValueError if it names nothing this storage
        could hold — for a disk, anything outside the root."""
        ...

    def unlinked_place(self, node_id: str) -> Place:
        """Where an id lands, refusing a link in any segment it names.

        For what walks a tree whole — packing, an archive download — where a
        link could duplicate the tree or point back at its own parent.
        """
        ...

    def parent(self, place: Place) -> Place:
        """The folder a node is in; the root is its own."""
        ...

    def child(self, folder: Place, name: str) -> Place:
        """The place a name has, or would have once made, in a folder."""
        ...

    def contains(self, ancestor: Place, place: Place) -> bool:
        """Whether a place is the ancestor itself or anywhere below it."""
        ...

    # --- what is there ---------------------------------------------------------

    def entry(self, place: Place) -> Entry | None:
        """What is at a place, or None when nothing is."""
        ...

    def entries(self, place: Place) -> list[Entry]:
        """One level of a folder, leaving out what is not the source's own.

        A link whose target cannot be described is not an entry, and neither is
        one the storage refuses to follow — for a disk, one out of the root.
        """
        ...

    def has_entries(self, place: Place) -> bool:
        """Whether a folder holds anything, as cheaply as the storage can say.

        A storage for which asking costs a round trip may answer yes for every
        folder: an expander on an empty folder costs less than a request per
        row of a listing.
        """
        ...

    def version(self, place: Place) -> str:
        """A token that changes whenever the file's bytes may have."""
        ...

    # --- reading ---------------------------------------------------------------

    def open(self, place: Place) -> BinaryIO:
        """The bytes of a file, seekable, closed by the caller."""
        ...

    def local_file(self, place: Place) -> AbstractContextManager[Path]:
        """A file on this machine holding the bytes, for the libraries that
        read a path: the file itself on the local disk, a copy elsewhere.

        It carries the place's own name, which is what a format is told by.
        """
        ...

    def local_root(self) -> Path:
        """The folder on this machine every local file of this storage is in.

        For the one reader that is told where it may read, the SQL engine
        (D78), and for taking that folder out of what the engine says. Does
        not block.
        """
        ...

    def local_tree(self, place: Place) -> AbstractContextManager[Path]:
        """A folder on this machine holding the tree below a place, for the
        walks that read one whole: packing and an archive download."""
        ...

    # --- writing ---------------------------------------------------------------

    def staged(
        self, near: Place, *, prefix: str = ".dataplayer-"
    ) -> AbstractContextManager[Path]:
        """A new local file to write, to be published at `near`.

        Whatever is not published by the end of the block is thrown away. The
        prefix names it for whoever finds one a crash left behind.
        """
        ...

    def publish(
        self,
        staged: Path,
        place: Place,
        *,
        replace: bool = False,
        expected_version: str | None = None,
    ) -> None:
        """Put a staged file at a place in one step.

        Without `replace` the name is claimed, and a taken one raises
        FileExistsError rather than being overwritten. With it the file there
        is replaced, keeping its permissions, and when a version is expected
        a file that has changed since raises VersionChanged instead.
        """
        ...

    def incoming(
        self, near: Place, *, prefix: str = ".dataplayer-"
    ) -> AbstractContextManager[Incoming]:
        """A new file written piece by piece where it is going, to be
        published at `near`.

        Unlike `staged`, nothing is held whole on this machine first: a
        transfer of gigabytes passes through in pieces (D168). Whatever is
        not published by the end of the block is thrown away.
        """
        ...

    def filled(self, place: Place) -> AbstractContextManager[Path]:
        """A local folder whose contents become those of an existing folder.

        What lands in it by the end of the block is in the folder afterwards;
        on the local disk it is the folder itself.
        """
        ...

    def make_directory(self, place: Place) -> None: ...

    def make_file(self, place: Place) -> None:
        """An empty file under a name nothing else has, or FileExistsError."""
        ...

    def rename(self, place: Place, to: Place) -> None:
        """Move a node to a name nothing has, or FileExistsError."""
        ...

    def copy(self, place: Place, to: Place) -> None:
        """A copy of a file or of a whole folder, links copied as links."""
        ...

    def remove(self, place: Place) -> None:
        """A file, or a folder with everything in it."""
        ...

    def remove_empty(self, place: Place) -> None:
        """A folder, only while nothing is in it; OSError otherwise.

        The storage refuses rather than the caller checking first, so a file
        added in between is never removed with the folder (D169).
        """
        ...


class Incoming(Protocol):
    """A file on its way into a storage, beside the place it will take."""

    def write(self, data: bytes) -> None: ...

    def publish(self, place: Place, *, replace: bool = False) -> None:
        """Put what was written at a place in one step, by `publish`'s rules."""
        ...


class PathPlaces:
    """Places of a storage that names a node by its path below the root.

    The disk and an SSH server both do: a key is the node id itself, and a
    parent or a child is a pure operation on it.
    """

    @staticmethod
    def place_at(path: PurePosixPath) -> Place:
        return ROOT if path == PurePosixPath() else Place(key=path.as_posix(), name=path.name)

    @staticmethod
    def path_at(place: Place) -> PurePosixPath:
        return PurePosixPath(place.key)

    @staticmethod
    def relative_path(node_id: str | None) -> PurePosixPath:
        """A node id as a path below the root, by the containment rule alone.

        Raises ValueError for an id that could leave the root. Whether it does
        once links are followed is the storage's to say.
        """
        if node_id is None or node_id == "":
            return PurePosixPath()
        if not stays_inside_root(node_id):
            raise ValueError(
                say("Path outside the connector root: {node_id}", node_id=node_id)
            )
        return PurePosixPath(node_id)

    def parent(self, place: Place) -> Place:
        return self.place_at(self.path_at(place).parent)

    def child(self, folder: Place, name: str) -> Place:
        return self.place_at(self.path_at(folder) / name)

    def contains(self, ancestor: Place, place: Place) -> bool:
        return self.path_at(place).is_relative_to(self.path_at(ancestor))


@runtime_checkable
class DraftsConnections(Protocol):
    """A storage one of whose folders can become a connection of its own."""

    def connection_for(self, place: Place) -> ConnectorDraft: ...


def walk_iterator(storage: Storage, place: Place) -> Iterator[Entry]:
    """Every entry below a place, depth first, links not followed.

    For the walks that need everything and have their own ceiling: the size of
    what is about to be copied or moved.
    """
    for entry in storage.entries(place):
        yield entry
        if entry.is_directory and not entry.is_link:
            yield from walk_iterator(storage, entry.place)


def ancestors(storage: Storage, place: Place) -> list[Place]:
    """Every folder from the root's first child down to the place, the place
    included and the root left out."""
    found: list[Place] = []
    current = place
    while current != ROOT:
        found.append(current)
        current = storage.parent(current)
    found.reverse()
    return found
