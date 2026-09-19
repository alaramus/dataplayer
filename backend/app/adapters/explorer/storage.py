"""Where a tree of files is kept, and the one way the explorer reaches it (D150).

Everything the explorer does — the catalog, formats read as text or tables,
SQL, the editor, search, actions — is written once, over this. A source that is
a tree of files brings a storage: the server's own disk under a person's home,
an SSH server over SFTP, whatever comes next. The storage says where a place
is and moves bytes there and back; the explorer says what the bytes are.

Blocking, and called from worker threads only (D151). The explorer's walks and
the libraries formats are read with are synchronous; a storage whose library
is asynchronous brings its answers into the thread, rather than the explorer
being written a second time.

A place is a path below the root, `ROOT` for the root itself. It is what a node
id becomes once the containment rule has passed it, and the only kind of path
the explorer builds: joining, taking a parent or a name are pure operations on
it, and nothing but the storage turns one into bytes.
"""

from collections.abc import Iterator
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import BinaryIO, Protocol, runtime_checkable

from app.adapters.actions import ConnectorDraft
from app.adapters.protocol import ConnectionCheckResult

ROOT = PurePosixPath()


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


def place_of(node_id: str | None) -> PurePosixPath:
    """A node id as a place, judged by the containment rule and nothing else.

    Raises ValueError for an id that could leave the root. Whether it does
    once links are followed is the storage's to say (`Storage.place`).
    """
    if node_id is None or node_id == "":
        return ROOT
    if not stays_inside_root(node_id):
        raise ValueError(f"Path outside the connector root: {node_id}")
    return PurePosixPath(node_id)


def node_id_of(place: PurePosixPath) -> str | None:
    """The node id of a place, as the client gets it back; the root has none."""
    return None if place == ROOT else place.as_posix()


@dataclass(frozen=True)
class Entry:
    """What a storage knows of one place without opening it.

    The facts are of what a link points at, as reading it gives it; `is_link`
    says the place itself is one, which is what a walk refuses to go down.
    """

    place: PurePosixPath
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


@runtime_checkable
class Storage(Protocol):
    """A tree of files below one root. Every method blocks.

    Failures of the storage itself are OSError, as a disk's are, so a walk can
    leave out what it cannot read in one place for every storage. A name that
    is taken is FileExistsError, a place that is not there FileNotFoundError.
    """

    def check(self) -> ConnectionCheckResult: ...

    def place(self, node_id: str | None) -> PurePosixPath:
        """Where an id lands, links followed, or ValueError if that is outside."""
        ...

    def unlinked_place(self, node_id: str) -> PurePosixPath:
        """Where an id lands, refusing a link in any segment it names.

        For what walks a tree whole — packing, an archive download — where a
        link could duplicate the tree or point back at its own parent.
        """
        ...

    def entry(self, place: PurePosixPath) -> Entry | None:
        """What is at a place, or None when nothing is."""
        ...

    def entries(self, place: PurePosixPath) -> list[Entry]:
        """One level of a folder, leaving out what is not the source's own.

        A link out of the root, or one whose target has gone, is not an entry.
        """
        ...

    def has_entries(self, place: PurePosixPath) -> bool:
        """Whether a folder holds anything, as cheaply as the storage can say."""
        ...

    def version(self, place: PurePosixPath) -> str:
        """A token that changes whenever the file's bytes may have."""
        ...

    def open(self, place: PurePosixPath) -> BinaryIO:
        """The bytes of a file, seekable, closed by the caller."""
        ...

    def local_file(self, place: PurePosixPath) -> AbstractContextManager[Path]:
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

    def local_tree(self, place: PurePosixPath) -> AbstractContextManager[Path]:
        """A folder on this machine holding the tree below a place, for the
        walks that read one whole: packing and an archive download."""
        ...

    def staged(
        self, near: PurePosixPath, *, prefix: str = ".dataplayer-"
    ) -> AbstractContextManager[Path]:
        """A new local file to write, to be published beside `near`.

        Whatever is not published by the end of the block is thrown away. The
        prefix names it for whoever finds one a crash left behind.
        """
        ...

    def publish(
        self,
        staged: Path,
        place: PurePosixPath,
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

    def filled(self, place: PurePosixPath) -> AbstractContextManager[Path]:
        """A local folder whose contents become those of an existing folder.

        What lands in it by the end of the block is in the folder afterwards;
        on the local disk it is the folder itself.
        """
        ...

    def make_directory(self, place: PurePosixPath) -> None: ...

    def make_file(self, place: PurePosixPath) -> None:
        """An empty file under a name nothing else has, or FileExistsError."""
        ...

    def rename(self, place: PurePosixPath, to: PurePosixPath) -> None:
        """Move a node to a name nothing has, or FileExistsError."""
        ...

    def copy(self, place: PurePosixPath, to: PurePosixPath) -> None:
        """A copy of a file or of a whole folder, links copied as links."""
        ...

    def remove(self, place: PurePosixPath) -> None:
        """A file, or a folder with everything in it."""
        ...


@runtime_checkable
class DraftsConnections(Protocol):
    """A storage one of whose folders can become a connection of its own."""

    def connection_for(self, place: PurePosixPath) -> ConnectorDraft: ...


def walk_iterator(storage: Storage, place: PurePosixPath) -> Iterator[Entry]:
    """Every entry below a place, depth first, links not followed.

    For the walks that need everything and have their own ceiling: the size of
    what is about to be copied or moved.
    """
    for entry in storage.entries(place):
        yield entry
        if entry.is_directory and not entry.is_link:
            yield from walk_iterator(storage, entry.place)
