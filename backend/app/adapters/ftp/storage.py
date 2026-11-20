"""An FTP server's files as a storage for the explorer (D150, D384, D385).

A node is named by its path below the connection's folder, as on an SSH
server; that folder is where browsing stands, not a wall — the server's own
permissions are (D144) — so a link is followed wherever it leads.

ftplib blocks, which is what a storage does (D151): every method runs in the
worker thread that asked, on a connection lent by the pool. A method that
needs several commands keeps one connection for all of them rather than
taking a second while it holds the first, so a request never waits on itself.
"""

import ftplib
import io
import posixpath
import socket
import ssl
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import BinaryIO, TypeVar

from app.adapters.actions import ActionRefused
from app.adapters.explorer.copies import TooLargeToCopy, copies
from app.adapters.explorer.storage import (
    REMOTE_SEARCH,
    ROOT,
    Entry,
    Incoming,
    PathPlaces,
    Place,
    VersionChanged,
    is_plain_name,
    walk_iterator,
)
from app.adapters.ftp.client import (
    BROKEN,
    Connection,
    FtpPool,
    identity_of,
    pool_for,
    reduced,
)
from app.adapters.ftp.listing import (
    Listed,
    facts_of,
    from_facts,
    from_list_line,
    from_mlsd_line,
)
from app.adapters.ftp.options import FtpOptions
from app.adapters.protocol import AdapterError, ConnectionCheckResult
from app.core.translation import say

T = TypeVar("T")

# A ranged read is a REST and a RETR, a round trip and a data connection, so a
# header reader's seeks are served from a quarter of a megabyte, as on S3.
READ_BUFFER = 256 * 1024


class FtpStorage(PathPlaces):
    search_limits = REMOTE_SEARCH

    def __init__(self, options: FtpOptions) -> None:
        self._options = options
        self._pool = pool_for(options)
        # Whose copies these are: the server, the user and where it stands.
        self._owner = f"ftp:{identity_of(options)}"

    # --- asking the server ---------------------------------------------------------

    def _asked(self, work: Callable[[Connection], T]) -> T:
        """Work done on one lent connection, its failures as the explorer
        expects them: an OSError for an answer, a kind for a lost server.

        A kept connection the server has closed since — idle, or restarted —
        is found out only by the command it fails, so the work is done once
        more on a new one; a new one that fails is a server gone.
        """
        for attempt in range(2):
            reused = False
            try:
                with self._pool.connection() as connection:
                    reused = connection.reused
                    return work(connection)
            except ftplib.error_perm:
                raise OSError(say("The server refused that")) from None
            except ftplib.error_temp:
                raise OSError(say("The server is busy; try again")) from None
            except BROKEN as failure:
                if reused and attempt == 0:
                    continue
                raise reduced(failure) from None
        raise AssertionError("unreachable")  # pragma: no cover

    def root_path(self, connection: Connection) -> str:
        folder = self._options.path
        if folder.startswith("/"):
            return folder
        return (
            posixpath.normpath(posixpath.join(connection.home, folder))
            if folder
            else connection.home
        )

    def path_of(self, connection: Connection, place: Place) -> str:
        root = self.root_path(connection)
        return posixpath.join(root, place.key) if place.key else root

    def check(self) -> ConnectionCheckResult:
        def work(connection: Connection) -> bool:
            try:
                connection.ftp.cwd(self.root_path(connection))
            except ftplib.error_perm:
                return False
            return True

        try:
            found = self._asked(work)
        except AdapterError as failure:
            return ConnectionCheckResult(
                ok=False, message=failure.message, error_kind=failure.error_kind
            )
        except OSError:
            found = False
        if not found:
            return ConnectionCheckResult(
                ok=False,
                message=say("There is no such folder on the server"),
                error_kind="config",
            )
        return ConnectionCheckResult(ok=True, message=say("Connection successful"))

    # --- where a node is -------------------------------------------------------------

    def place(self, node_id: str | None) -> Place:
        return self.place_at(self.relative_path(node_id))

    def unlinked_place(self, node_id: str) -> Place:
        place = self.place(node_id)
        parts = self.path_at(place).parts

        def work(connection: Connection) -> None:
            for depth in range(1, len(parts) + 1):
                found = self._entry(
                    connection, self.place_at(PurePosixPath(*parts[:depth]))
                )
                if found is None:
                    return
                if found.is_link:
                    raise ValueError(say("Symbolic links are not downloaded"))

        self._asked(work)
        return place

    # --- what is there ---------------------------------------------------------------

    def entry(self, place: Place) -> Entry | None:
        return self._asked(lambda connection: self._entry(connection, place))

    def entries(self, place: Place) -> list[Entry]:
        return self._asked(lambda connection: self._entries(connection, place))

    def has_entries(self, place: Place) -> bool:
        # Claimed rather than asked, as on SFTP: asking would be a listing per
        # folder of a listing.
        return True

    def version(self, place: Place) -> str:
        def work(connection: Connection) -> str:
            found = self._entry(connection, place)
            if found is None or found.is_directory:
                raise FileNotFoundError(place.key)
            return _version(connection, self.path_of(connection, place), found)

        return self._asked(work)

    def _entries(self, connection: Connection, place: Place) -> list[Entry]:
        path = self.path_of(connection, place)
        found: list[Entry] = []
        for listed in self._listed(connection, path):
            if not _nameable(listed.name):
                continue
            child = self.child(place, listed.name)
            entry = self._described(connection, child, listed)
            if entry is not None:
                found.append(entry)
        return found

    def _entry(self, connection: Connection, place: Place) -> Entry | None:
        path = self.path_of(connection, place)
        if place == ROOT:
            try:
                connection.ftp.cwd(path)
            except ftplib.error_perm:
                return None
            return Entry(place=ROOT, is_directory=True, size_bytes=0, modified_at=None)
        if connection.has("MLST"):
            try:
                reply = connection.ftp.sendcmd(f"MLST {path}")
            except ftplib.error_perm:
                return None
            lines = [line for line in reply.splitlines() if line.startswith(" ")]
            if lines:
                facts, _ = facts_of(lines[0].strip())
                listed = from_facts(facts, place.name)
                return (
                    None
                    if listed is None
                    else self._described(connection, place, listed)
                )
        try:
            siblings = self._listed(
                connection, self.path_of(connection, self.parent(place))
            )
        except FileNotFoundError:
            return None
        for listed in siblings:
            if listed.name == place.name:
                return self._described(connection, place, listed)
        return None

    def _described(
        self, connection: Connection, place: Place, listed: Listed
    ) -> Entry | None:
        """An entry as listed; a link as what it points at, found by going
        into it and else asking its size, and left out when it points at
        nothing, as the local disk leaves a broken one out."""
        if listed.kind != "link":
            return Entry(
                place=place,
                is_directory=listed.kind == "directory",
                size_bytes=listed.size_bytes,
                modified_at=listed.modified_at,
                permissions=listed.permissions,
            )
        path = self.path_of(connection, place)
        try:
            connection.ftp.cwd(path)
            return Entry(
                place=place,
                is_directory=True,
                size_bytes=0,
                modified_at=listed.modified_at,
                is_link=True,
                permissions=listed.permissions,
            )
        except ftplib.error_perm:
            pass
        try:
            connection.binary()
            size = connection.ftp.size(path)
        except ftplib.error_perm, ftplib.error_temp:
            return None
        return Entry(
            place=place,
            is_directory=False,
            size_bytes=size or 0,
            modified_at=listed.modified_at,
            is_link=True,
            permissions=listed.permissions,
        )

    def _listed(self, connection: Connection, path: str) -> list[Listed]:
        """One folder as the server lists it: MLSD where it is spoken, LIST
        otherwise. A folder that is not there, or not this user's to read, is
        FileNotFoundError, which a walk leaves out and a listing refuses."""
        if connection.has("MLST"):
            try:
                lines = _lines(connection, f"MLSD {path}")
            except ftplib.error_perm:
                raise FileNotFoundError(path) from None
            return [
                listed for line in lines if (listed := from_mlsd_line(line)) is not None
            ]
        try:
            connection.ftp.cwd(path)
        except ftplib.error_perm:
            raise FileNotFoundError(path) from None
        try:
            # `-a` for the names that begin with a dot, which vsftpd hides
            # without it; a server that takes it for a path refuses it.
            lines = _lines(connection, "LIST -a")
        except ftplib.error_perm:
            lines = _lines(connection, "LIST")
        now = datetime.now(UTC)
        return [
            listed
            for line in lines
            if (listed := from_list_line(line, now)) is not None
        ]

    def _exists(self, connection: Connection, place: Place) -> bool:
        return self._entry(connection, place) is not None

    # --- reading -----------------------------------------------------------------------

    def open(self, place: Place) -> BinaryIO:
        found = self.entry(place)
        if found is None or found.is_directory:
            raise FileNotFoundError(place.key)
        raw = _RemoteFile(
            self._pool,
            lambda connection: self.path_of(connection, place),
            found.size_bytes,
        )
        return io.BufferedReader(raw, buffer_size=READ_BUFFER)

    @contextmanager
    def local_file(self, place: Place) -> Iterator[Path]:
        """A copy, or what the local disk would lend in its place, as SFTP's."""
        found = self.entry(place)
        if found is None or found.is_directory:
            with copies().scratch(self._owner) as folder:
                stand_in = folder / (place.name or "root")
                if found is not None:
                    stand_in.mkdir()
                yield stand_in
            return
        version = self.version(place)

        def fetch(target: Path) -> None:
            self._asked(
                lambda connection: self._download_file(connection, place, target)
            )

        with copies().held(
            self._owner, place.key, place.name, version, found.size_bytes, fetch
        ) as path:
            yield path

    def local_root(self) -> Path:
        return copies().folder_of(self._owner)

    @contextmanager
    def local_tree(self, place: Place) -> Iterator[Path]:
        """The tree fetched whole into a scratch folder, within what may pass
        through this server (D152), and never through a link."""
        found = self.entry(place)
        with copies().scratch(self._owner) as folder:
            target = folder / (place.name or "root")
            if found is not None:
                self._within_transfer(place, found)
                self._asked(
                    lambda connection: self._download(connection, place, found, target)
                )
            yield target

    def _download(
        self, connection: Connection, place: Place, found: Entry, target: Path
    ) -> None:
        if not found.is_directory:
            self._download_file(connection, place, target)
            return
        target.mkdir(parents=True, exist_ok=True)
        for entry in self._entries(connection, place):
            self._download(connection, entry.place, entry, target / entry.name)

    def _download_file(
        self, connection: Connection, place: Place, target: Path
    ) -> None:
        path = self.path_of(connection, place)
        connection.binary()
        with target.open("wb") as sink:
            try:
                connection.ftp.retrbinary(f"RETR {path}", sink.write)
            except ftplib.error_perm:
                raise FileNotFoundError(place.key) from None

    # --- writing ---------------------------------------------------------------------

    @contextmanager
    def staged(self, near: Place, *, prefix: str = ".dataplayer-") -> Iterator[Path]:
        with copies().scratch(self._owner) as folder:
            staged = folder / f"{prefix}{uuid.uuid4().hex}"
            staged.touch()
            yield staged

    def publish(
        self,
        staged: Path,
        place: Place,
        *,
        replace: bool = False,
        expected_version: str | None = None,
    ) -> None:
        """Sent beside its name and renamed into place, so nobody reading the
        folder sees half a file under the name they look for (D385)."""

        def work(connection: Connection) -> None:
            temporary = self._temporary(connection, place, ".dataplayer-")
            connection.binary()
            with staged.open("rb") as source:
                connection.ftp.storbinary(f"STOR {temporary}", source)
            self._put_in_place(connection, temporary, place, replace, expected_version)

        self._asked(work)
        self._forget(place)

    def _temporary(self, connection: Connection, near: Place, prefix: str) -> str:
        return posixpath.join(
            self.path_of(connection, self.parent(near)), f"{prefix}{uuid.uuid4().hex}"
        )

    def _put_in_place(
        self,
        connection: Connection,
        temporary: str,
        place: Place,
        replace: bool,
        expected_version: str | None,
    ) -> None:
        """A file sent under a temporary name, renamed to its own; removed
        when that fails, so nothing half-done is left beside it."""
        target = self.path_of(connection, place)
        try:
            if replace:
                self._replaced(connection, temporary, target, place, expected_version)
            else:
                # Asked first, then renamed: FTP has no rename that refuses a
                # taken name, and most servers overwrite one (D385).
                if self._exists(connection, place):
                    raise FileExistsError(place.key)
                connection.ftp.rename(temporary, target)
        except BaseException:
            with suppress(Exception):
                connection.ftp.delete(temporary)
            raise

    def _replaced(
        self,
        connection: Connection,
        temporary: str,
        target: str,
        place: Place,
        expected_version: str | None,
    ) -> None:
        current = self._entry(connection, place)
        if expected_version is not None and (
            current is None or _version(connection, target, current) != expected_version
        ):
            raise VersionChanged
        if current is not None and current.permissions is not None:
            # A script keeps being executable once it is saved, where the
            # server lets the mode be set at all.
            mode = _octal(current.permissions)
            if mode is not None:
                with suppress(ftplib.error_perm, ftplib.error_temp):
                    connection.ftp.voidcmd(f"SITE CHMOD {mode:o} {temporary}")
        try:
            connection.ftp.rename(temporary, target)
        except ftplib.error_perm:
            # A server that refuses to rename over a file — IIS — has it
            # removed first.
            if current is None:
                raise
            connection.ftp.delete(target)
            connection.ftp.rename(temporary, target)
        if connection.has("MFMT"):
            # The version is the modification time, counted in seconds, so two
            # writes inside one would otherwise read as one.
            previous = current.modified_at if current is not None else None
            moment = datetime.now(UTC).replace(microsecond=0)
            if previous is not None and moment <= previous:
                moment = previous + timedelta(seconds=1)
            with suppress(ftplib.error_perm, ftplib.error_temp):
                connection.ftp.voidcmd(f"MFMT {moment:%Y%m%d%H%M%S} {target}")

    @contextmanager
    def incoming(
        self, near: Place, *, prefix: str = ".dataplayer-"
    ) -> Iterator[Incoming]:
        """Written on the server as it arrives, into a temporary name beside
        its target: nothing is staged whole on this machine first (D168)."""
        arriving = _Arriving(self, near, prefix)
        try:
            yield arriving
        finally:
            arriving.discarded()

    @contextmanager
    def filled(self, place: Place) -> Iterator[Path]:
        with copies().scratch(self._owner) as folder:
            yield folder
            written = sum(
                path.stat().st_size for path in folder.rglob("*") if path.is_file()
            )
            if written > copies().largest_bytes:
                raise TooLargeToCopy(place.name or say("What came out"))

            def work(connection: Connection) -> None:
                for item in sorted(folder.iterdir()):
                    self._upload(connection, item, self.child(place, item.name))

            self._asked(work)
            self._forget(place)

    def _upload(self, connection: Connection, item: Path, place: Place) -> None:
        path = self.path_of(connection, place)
        if item.is_dir():
            try:
                connection.ftp.mkd(path)
            except ftplib.error_perm:
                # Already there is where it is filled; anything else is the
                # server's refusal, which the first file sent into it repeats.
                pass
            for child in sorted(item.iterdir()):
                self._upload(connection, child, self.child(place, child.name))
            return
        connection.binary()
        with item.open("rb") as source:
            connection.ftp.storbinary(f"STOR {path}", source)

    def make_directory(self, place: Place) -> None:
        def work(connection: Connection) -> None:
            if self._exists(connection, place):
                raise FileExistsError(place.key)
            connection.ftp.mkd(self.path_of(connection, place))

        self._asked(work)

    def make_file(self, place: Place) -> None:
        def work(connection: Connection) -> None:
            if self._exists(connection, place):
                raise FileExistsError(place.key)
            connection.binary()
            connection.ftp.storbinary(
                f"STOR {self.path_of(connection, place)}", io.BytesIO(b"")
            )

        self._asked(work)

    def rename(self, place: Place, to: Place) -> None:
        def work(connection: Connection) -> None:
            if self._exists(connection, to):
                raise FileExistsError(to.key)
            connection.ftp.rename(
                self.path_of(connection, place), self.path_of(connection, to)
            )

        self._asked(work)
        self._forget(place)

    def copy(self, place: Place, to: Place) -> None:
        """Through this server, within what may pass through it (D152): FTP
        has no copy of its own (D385)."""
        found = self.entry(place)
        if found is None:
            raise FileNotFoundError(place.key)
        self._within_transfer(place, found)
        with copies().scratch(self._owner) as folder:
            local = folder / (place.name or "root")

            def work(connection: Connection) -> None:
                self._download(connection, place, found, local)
                self._upload(connection, local, to)

            self._asked(work)

    def remove(self, place: Place) -> None:
        def work(connection: Connection) -> None:
            found = self._entry(connection, place)
            if found is None:
                raise FileNotFoundError(place.key)
            self._removed(connection, found)

        self._asked(work)
        self._forget(place)

    def _removed(self, connection: Connection, found: Entry) -> None:
        path = self.path_of(connection, found.place)
        if found.is_directory and not found.is_link:
            for child in self._entries(connection, found.place):
                self._removed(connection, child)
            connection.ftp.rmd(path)
        else:
            connection.ftp.delete(path)

    def remove_empty(self, place: Place) -> None:
        def work(connection: Connection) -> None:
            try:
                connection.ftp.rmd(self.path_of(connection, place))
            except ftplib.error_perm:
                # A folder that is not empty is an answer, not a server gone.
                raise OSError(place.key) from None

        self._asked(work)
        self._forget(place)

    def _forget(self, place: Place) -> None:
        """The copies of a node just written, and of everything below it."""
        copies().forget(
            self._owner,
            lambda key: self.contains(
                place, Place(key=key, name=posixpath.basename(key))
            ),
        )

    def _within_transfer(self, place: Place, found: Entry) -> None:
        """What would pass through this server, held to the one ceiling."""
        if not found.is_directory:
            total = found.size_bytes
        else:
            total = 0
            for entry in walk_iterator(self, place):
                if entry.is_link:
                    raise ActionRefused(
                        "not_applicable",
                        say("A folder holding a symbolic link is not copied here"),
                    )
                if not entry.is_directory:
                    total += entry.size_bytes
                if total > copies().largest_bytes:
                    break
        if total > copies().largest_bytes:
            raise TooLargeToCopy(place.name)


class _RemoteFile(io.RawIOBase):
    """A remote file read at any offset, from a worker thread.

    A read where the last one ended goes on reading the transfer already
    open; any other starts a new one with REST, the one before cut short.
    Holds a connection of its own while it is open: a download is read long
    after the request that opened it has answered.
    """

    def __init__(
        self, pool: FtpPool, path_of: Callable[[Connection], str], size: int
    ) -> None:
        super().__init__()
        self._pool = pool
        self._path_of = path_of
        self._size = size
        self._position = 0
        self._connection: Connection | None = None
        self._data: socket.socket | None = None
        self._data_at = 0

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def readinto(self, buffer: memoryview) -> int:  # type: ignore[override]  # io's own signature takes a writable buffer
        if self._position >= self._size or len(buffer) == 0:
            return 0
        try:
            if self._data is None or self._data_at != self._position:
                self._cut_short()
                self._start()
            assert self._data is not None
            count = self._data.recv_into(buffer)
        except ftplib.error_perm:
            self._drop()
            raise FileNotFoundError(
                say("The file is no longer on the server")
            ) from None
        except (*BROKEN, OSError):
            self._drop()
            raise OSError(say("The file could not be read from the server")) from None
        if count == 0:
            self._finish()
            return 0
        self._position += count
        self._data_at += count
        return count

    def _start(self) -> None:
        if self._connection is None:
            self._connection = self._pool.take(checked=True)
        self._connection.binary()
        path = self._path_of(self._connection)
        self._data = self._connection.ftp.transfercmd(
            f"RETR {path}", rest=self._position or None
        )
        self._data_at = self._position

    def _finish(self) -> None:
        """The transfer read to its end, and the server's word on it read."""
        if self._data is None or self._connection is None:
            return
        data, self._data = self._data, None
        try:
            if isinstance(data, ssl.SSLSocket):
                with suppress(OSError, ssl.SSLError):
                    data.unwrap()
            data.close()
            self._connection.ftp.voidresp()
        except ftplib.error_temp, ftplib.error_perm:
            pass
        except (*BROKEN, OSError):
            self._drop()

    def _cut_short(self) -> None:
        """The transfer abandoned, and the connection kept only if the
        server's replies to it can be read past."""
        if self._data is None:
            return
        data, self._data = self._data, None
        with suppress(OSError):
            data.close()
        if self._connection is not None and not self._connection.in_step():
            self._drop()

    def _drop(self) -> None:
        if self._data is not None:
            with suppress(OSError):
                self._data.close()
            self._data = None
        if self._connection is not None:
            connection, self._connection = self._connection, None
            self._pool.give(connection, broken=True)

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self._position, io.SEEK_END: self._size}[
            whence
        ]
        self._position = max(0, base + offset)
        return self._position

    def tell(self) -> int:
        return self._position

    def close(self) -> None:
        if not self.closed:
            if self._data is not None:
                if self._data_at >= self._size:
                    self._finish()
                else:
                    self._cut_short()
            if self._connection is not None:
                connection, self._connection = self._connection, None
                self._pool.give(connection)
        super().close()


class _Arriving:
    """A remote file written in pieces from a worker thread, then renamed
    into place — or removed, when the block ends without that."""

    def __init__(self, storage: FtpStorage, near: Place, prefix: str) -> None:
        self._storage = storage
        self._pool = storage._pool
        self._connection: Connection | None = self._pool.take(checked=True)
        self._data: socket.socket | None = None
        self._published = False
        try:
            self._temporary = storage._temporary(self._connection, near, prefix)
            self._connection.binary()
            self._data = self._connection.ftp.transfercmd(f"STOR {self._temporary}")
        except ftplib.error_perm:
            self._give(broken=False)
            raise FileNotFoundError(near.key) from None
        except (*BROKEN, OSError, ftplib.error_temp):
            self._give(broken=True)
            raise OSError(say("The file could not be created on the server")) from None

    def write(self, data: bytes) -> None:
        if self._data is None:
            raise OSError(say("The file is no longer open"))
        try:
            self._data.sendall(data)
        except OSError:
            raise OSError(say("The file could not be written on the server")) from None

    def publish(self, place: Place, *, replace: bool = False) -> None:
        connection, data = self._connection, self._data
        if connection is None or data is None:
            raise OSError(say("The file is no longer open"))
        self._data = None
        try:
            if isinstance(data, ssl.SSLSocket):
                data.unwrap()
            data.close()
            connection.ftp.voidresp()
            self._storage._put_in_place(
                connection, self._temporary, place, replace, None
            )
        except FileExistsError, VersionChanged:
            self._published = True  # the temporary is already removed
            raise
        except (*BROKEN, OSError, ftplib.Error):
            raise OSError(
                say("The file could not be put in place on the server")
            ) from None
        self._published = True
        self._storage._forget(place)

    def discarded(self) -> None:
        connection = self._connection
        if connection is None:
            return
        broken = False
        if self._data is not None:
            data, self._data = self._data, None
            with suppress(OSError):
                data.close()
            broken = not connection.in_step()
        if not self._published and not broken:
            with suppress(Exception):
                connection.ftp.delete(self._temporary)
        self._give(broken=broken)

    def _give(self, *, broken: bool) -> None:
        if self._connection is not None:
            connection, self._connection = self._connection, None
            self._pool.give(connection, broken=broken, doubtful=True)


def _lines(connection: Connection, command: str) -> list[str]:
    """What a listing command sends on its data channel, line by line, names
    kept as bytes wherever they are not UTF-8."""
    connection.text()
    data = connection.ftp.transfercmd(command)
    try:
        with data.makefile("rb") as stream:
            raw = stream.read()
        if isinstance(data, ssl.SSLSocket):
            with suppress(OSError, ssl.SSLError):
                data.unwrap()
    finally:
        data.close()
    connection.ftp.voidresp()
    text = raw.decode("utf-8", "surrogateescape")
    return [line.rstrip("\r") for line in text.split("\n") if line.strip()]


def _nameable(name: str) -> bool:
    """A name an id can carry and a browser can show: plain by the path rule,
    and UTF-8 — a name in another encoding is left out (D384)."""
    if not is_plain_name(name):
        return False
    try:
        name.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _version(connection: Connection, path: str, found: Entry) -> str:
    """The modification time and the size. MDTM gives the time to the second
    where a listing may give it to the minute or the day."""
    moment = found.modified_at.isoformat() if found.modified_at else ""
    if connection.has("MDTM") and not found.is_directory:
        with suppress(ftplib.error_perm, ftplib.error_temp):
            moment = connection.ftp.sendcmd(f"MDTM {path}").split(" ", 1)[-1].strip()
    return f"{moment}:{found.size_bytes}"


def _octal(permissions: str) -> int | None:
    """`-rwxr-xr-x` as 0o755; None for a text that is not one. `S` and `T`
    are setuid and sticky without the execute bit beneath them."""
    letters = permissions[1:10]
    if len(letters) != 9:
        return None
    bits = (0o400, 0o200, 0o100, 0o40, 0o20, 0o10, 0o4, 0o2, 0o1)
    return sum(
        bit for letter, bit in zip(letters, bits, strict=True) if letter not in "-ST"
    )
