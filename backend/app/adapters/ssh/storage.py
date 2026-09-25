"""An SSH server's files as a storage for the explorer (D150, D152).

Everything the explorer asks is carried out over SFTP through the session,
which signs in with the connection's own credentials and trusts only the
server key it pinned (D145, D147); nothing here runs a command on the server,
so no name typed into a form ever reaches a shell (D144).

The explorer asks from a worker thread (D151) and asyncssh answers on the
event loop, so every request goes back to the loop with `from_thread.run`.
Answers the explorer expects as an OSError — a taken name, a missing folder —
are carried past the session, which would otherwise reduce them to a failure
of the server.

A node is named by its path below the connection's folder, as it always was;
that folder is where browsing stands, not a wall — the server's own
permissions are the wall (D144) — so a link is followed wherever it leads.
"""

import io
import posixpath
import stat
import time
import uuid
from collections.abc import Awaitable, Callable, Iterator
from contextlib import AsyncExitStack, contextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO, TypeVar

import asyncssh
from anyio import from_thread

from app.adapters.actions import ActionRefused
from app.adapters.explorer.copies import TooLargeToCopy, copies
from app.adapters.explorer.storage import (
    REMOTE_SEARCH,
    Entry,
    Incoming,
    PathPlaces,
    Place,
    VersionChanged,
    is_plain_name,
    walk_iterator,
)
from app.adapters.protocol import ConnectionCheckResult
from app.adapters.ssh.session import Remote, SshSession

T = TypeVar("T")

_MISSING = (asyncssh.SFTPNoSuchFile, asyncssh.SFTPNoSuchPath)


class _Carried(Exception):
    """An answer the explorer expects as an OSError, carried past the session.

    The session reduces every OSError to "could not reach the server", which
    is right for a dropped network and wrong for a name that is taken.
    """

    def __init__(self, error: OSError) -> None:
        super().__init__(str(error))
        self.error = error


class SftpStorage(PathPlaces):
    search_limits = REMOTE_SEARCH

    def __init__(self, session: SshSession, owner: str) -> None:
        self._session = session
        # Whose copies these are: the server, the account and its credentials.
        self._owner = f"ssh:{owner}"

    # --- carrying a request to the loop and back --------------------------------

    def _ask(self, work: Callable[[Remote], Awaitable[T]]) -> T:
        try:
            return from_thread.run(self._asked, work)
        except _Carried as carried:
            raise carried.error from None

    async def _asked(self, work: Callable[[Remote], Awaitable[T]]) -> T:
        async with self._session.remote() as remote:
            return await work(remote)

    def check(self) -> ConnectionCheckResult:
        return from_thread.run(self._session.check)

    # --- where a node is ---------------------------------------------------------

    def place(self, node_id: str | None) -> Place:
        return self.place_at(self.relative_path(node_id))

    def unlinked_place(self, node_id: str) -> Place:
        place = self.place(node_id)
        parts = self.path_at(place).parts

        async def work(remote: Remote) -> None:
            for depth in range(1, len(parts) + 1):
                try:
                    attrs = await remote.sftp.lstat(remote.path_of("/".join(parts[:depth])))
                except _MISSING:
                    return
                if _is_link(attrs):
                    raise ValueError("Symbolic links are not downloaded")

        self._ask(work)
        return place

    # --- what is there -----------------------------------------------------------

    def entry(self, place: Place) -> Entry | None:
        async def work(remote: Remote) -> Entry | None:
            return await _described(remote, place)

        return self._ask(work)

    def entries(self, place: Place) -> list[Entry]:
        async def work(remote: Remote) -> list[Entry]:
            try:
                names = await remote.sftp.readdir(remote.path_of(place.key))
            except asyncssh.SFTPError:
                # A folder that is not there, or not this user's to read, is a
                # folder a walk leaves out and a listing refuses.
                raise _Carried(FileNotFoundError(place.key)) from None
            found: list[Entry] = []
            for name in names:
                filename = str(name.filename)
                # A name the path rule refuses could never be opened again by
                # its id.
                if filename in (".", "..") or not is_plain_name(filename):
                    continue
                child = self.child(place, filename)
                attrs = name.attrs
                is_link = _is_link(attrs)
                if is_link:
                    # Described by what it points at; a broken one is left out,
                    # as the local disk leaves one out.
                    try:
                        attrs = await remote.sftp.stat(remote.path_of(child.key))
                    except asyncssh.SFTPError:
                        continue
                found.append(_entry(child, attrs, is_link))
            return found

        return self._ask(work)

    def has_entries(self, place: Place) -> bool:
        # Claimed rather than asked: asking would be one more round trip per
        # folder of a listing, and a listing may hold two thousand of them.
        return True

    def version(self, place: Place) -> str:
        async def work(remote: Remote) -> str:
            try:
                return _version(await remote.sftp.stat(remote.path_of(place.key)))
            except _MISSING:
                raise _Carried(FileNotFoundError(place.key)) from None

        return self._ask(work)

    # --- reading -----------------------------------------------------------------

    def open(self, place: Place) -> BinaryIO:
        raw = _RemoteFile(self._session, place)
        from_thread.run(raw.opened)
        # Small, because every seek of a header reader refills it: an MP4 read
        # for its duration is a handful of these. A read larger than the
        # buffer — a range a player streams — goes around it.
        return io.BufferedReader(raw, buffer_size=64 * 1024)

    @contextmanager
    def local_file(self, place: Place) -> Iterator[Path]:
        """A copy, or what the local disk would lend in its place.

        Nothing there is a path that does not exist, and a folder is an empty
        folder, so the explorer's own "no such file" and "a folder has no
        viewer" answer for a server as they do for the disk.
        """
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
            async def work(remote: Remote) -> None:
                await remote.sftp.get(remote.path_of(place.key), target)

            self._ask(work)

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

                async def work(remote: Remote) -> None:
                    await remote.sftp.get(remote.path_of(place.key), target, recurse=True)

                self._ask(work)
            yield target

    # --- writing -------------------------------------------------------------------

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
        """Sent beside its name and moved into place, so nobody reading the
        folder sees half a file under the name they look for."""

        async def work(remote: Remote) -> None:
            target = remote.path_of(place.key)
            temporary = posixpath.join(
                remote.path_of(self.parent(place).key), f".dataplayer-{uuid.uuid4().hex}"
            )
            await remote.sftp.put(staged, temporary)
            try:
                if replace:
                    await _replaced(remote, temporary, target, expected_version)
                else:
                    await _claimed(remote, temporary, target, place)
            except BaseException:
                try:
                    await remote.sftp.remove(temporary)
                except asyncssh.SFTPError:
                    pass
                raise

        self._ask(work)
        self._forget(place)

    @contextmanager
    def incoming(self, near: Place, *, prefix: str = ".dataplayer-") -> Iterator[Incoming]:
        """Written on the server as it arrives, into a temporary name beside
        its target: nothing is staged whole on this machine first (D168)."""
        arriving = _RemoteArriving(self._session, self.parent(near), prefix, self._forget)
        from_thread.run(arriving.opened)
        try:
            yield arriving
        finally:
            from_thread.run(arriving.discarded)

    @contextmanager
    def filled(self, place: Place) -> Iterator[Path]:
        with copies().scratch(self._owner) as folder:
            yield folder
            written = sum(path.stat().st_size for path in folder.rglob("*") if path.is_file())
            if written > copies().largest_bytes:
                raise TooLargeToCopy(place.name or "What came out")
            for item in sorted(folder.iterdir()):
                destination = self.child(place, item.name)

                async def work(remote: Remote, item: Path = item, to: Place = destination) -> None:
                    await remote.sftp.put(item, remote.path_of(to.key), recurse=True)

                self._ask(work)

    def make_directory(self, place: Place) -> None:
        async def work(remote: Remote) -> None:
            path = remote.path_of(place.key)
            if await remote.sftp.exists(path):
                raise _Carried(FileExistsError(place.key))
            await remote.sftp.mkdir(path)

        self._ask(work)

    def make_file(self, place: Place) -> None:
        async def work(remote: Remote) -> None:
            path = remote.path_of(place.key)
            if await remote.sftp.exists(path):
                raise _Carried(FileExistsError(place.key))
            handle = await remote.sftp.open(path, "wb", encoding=None)
            await handle.close()

        self._ask(work)

    def rename(self, place: Place, to: Place) -> None:
        async def work(remote: Remote) -> None:
            target = remote.path_of(to.key)
            if await remote.sftp.exists(target):
                raise _Carried(FileExistsError(to.key))
            # The plain rename, which a server refuses over an existing name.
            await remote.sftp.rename(remote.path_of(place.key), target)

        self._ask(work)
        self._forget(place)

    def copy(self, place: Place, to: Place) -> None:
        """By the server itself where it can; through this server otherwise,
        within what may pass through it (D152)."""

        async def on_the_server(remote: Remote) -> bool:
            try:
                await remote.sftp.copy(
                    remote.path_of(place.key),
                    remote.path_of(to.key),
                    recurse=True,
                    preserve=True,
                    remote_only=True,
                )
            except asyncssh.SFTPOpUnsupported:
                return False
            return True

        if self._ask(on_the_server):
            return
        found = self.entry(place)
        if found is None:
            raise FileNotFoundError(place.key)
        self._within_transfer(place, found)

        async def through_here(remote: Remote) -> None:
            await remote.sftp.copy(
                remote.path_of(place.key), remote.path_of(to.key), recurse=True, preserve=True
            )

        self._ask(through_here)

    def remove(self, place: Place) -> None:
        async def work(remote: Remote) -> None:
            path = remote.path_of(place.key)
            attrs = await remote.sftp.lstat(path)
            if _is_directory(attrs) and not _is_link(attrs):
                await remote.sftp.rmtree(path)
            else:
                await remote.sftp.remove(path)

        self._ask(work)
        self._forget(place)

    def _forget(self, place: Place) -> None:
        """The copies of a node just written, and of everything below it."""
        copies().forget(
            self._owner,
            lambda key: self.contains(place, Place(key=key, name=posixpath.basename(key))),
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
                        "not_applicable", "A folder holding a symbolic link is not copied here"
                    )
                if not entry.is_directory:
                    total += entry.size_bytes
                if total > copies().largest_bytes:
                    break
        if total > copies().largest_bytes:
            raise TooLargeToCopy(place.name)


class _RemoteFile(io.RawIOBase):
    """A remote file read in pieces, from a worker thread, at any offset.

    Holds its own use of the session for as long as it is open: a download is
    read long after the request that opened it has answered.
    """

    def __init__(self, session: SshSession, place: Place) -> None:
        super().__init__()
        self._session = session
        self._place = place
        self._stack = AsyncExitStack()
        self._file: asyncssh.SFTPClientFile | None = None
        self._size = 0
        self._position = 0

    async def opened(self) -> None:
        remote = await self._stack.enter_async_context(self._session.remote())
        try:
            self._file = await remote.sftp.open(
                remote.path_of(self._place.key), "rb", encoding=None
            )
            self._size = (await self._file.stat()).size or 0
        except asyncssh.SFTPError:
            await self._stack.aclose()
            raise FileNotFoundError(self._place.key) from None

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def readinto(self, buffer: memoryview) -> int:  # type: ignore[override]  # io's own signature takes a writable buffer
        if self._file is None or self._position >= self._size:
            return 0
        data = from_thread.run(self._read, len(buffer))
        buffer[: len(data)] = data
        self._position += len(data)
        return len(data)

    async def _read(self, size: int) -> bytes:
        if self._file is None:
            return b""
        try:
            chunk = await self._file.read(size, self._position)
        except (asyncssh.Error, TimeoutError):
            raise OSError("The file could not be read from the server") from None
        return chunk if isinstance(chunk, bytes) else chunk.encode()

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self._position, io.SEEK_END: self._size}[whence]
        self._position = max(0, base + offset)
        return self._position

    def tell(self) -> int:
        return self._position

    def close(self) -> None:
        if not self.closed and self._file is not None:
            try:
                from_thread.run(self._closed)
            except RuntimeError:
                # Closed from a thread that is no worker — a collector — where
                # the loop cannot be reached; the session closes it in time.
                pass
            self._file = None
        super().close()

    async def _closed(self) -> None:
        if self._file is not None:
            await self._file.close()
        await self._stack.aclose()


class _RemoteArriving:
    """A remote file written in pieces from a worker thread, then renamed
    into place — or removed, when the block ends without that.

    Holds its own use of the session while it is open, as a file being read
    does: a transfer writes long after the request that started it answered.
    """

    def __init__(
        self,
        session: SshSession,
        folder: Place,
        prefix: str,
        forget: Callable[[Place], None],
    ) -> None:
        self._session = session
        self._folder = folder
        self._prefix = prefix
        self._forget = forget
        self._stack = AsyncExitStack()
        self._remote: Remote | None = None
        self._file: asyncssh.SFTPClientFile | None = None
        self._temporary = ""
        self._offset = 0
        self._published = False

    async def opened(self) -> None:
        remote = await self._stack.enter_async_context(self._session.remote())
        self._remote = remote
        self._temporary = posixpath.join(
            remote.path_of(self._folder.key), f"{self._prefix}{uuid.uuid4().hex}"
        )
        try:
            self._file = await remote.sftp.open(self._temporary, "wb", encoding=None)
        except _MISSING:
            await self._stack.aclose()
            raise FileNotFoundError(self._folder.key) from None
        except (asyncssh.Error, TimeoutError):
            await self._stack.aclose()
            raise OSError("The file could not be created on the server") from None

    def write(self, data: bytes) -> None:
        from_thread.run(self._write, data)

    async def _write(self, data: bytes) -> None:
        if self._file is None:
            raise OSError("The file is no longer open")
        try:
            await self._file.write(data, self._offset)
        except (asyncssh.Error, TimeoutError):
            raise OSError("The file could not be written on the server") from None
        self._offset += len(data)

    def publish(self, place: Place, *, replace: bool = False) -> None:
        try:
            from_thread.run(self._publish, place, replace)
        except _Carried as carried:
            raise carried.error from None
        self._forget(place)

    async def _publish(self, place: Place, replace: bool) -> None:
        remote, file = self._remote, self._file
        if remote is None or file is None:
            raise OSError("The file is no longer open")
        self._file = None
        try:
            await file.close()
            target = remote.path_of(place.key)
            if replace:
                await _replaced(remote, self._temporary, target, None)
            else:
                await _claimed(remote, self._temporary, target, place)
        except (asyncssh.Error, TimeoutError):
            raise OSError("The file could not be put in place on the server") from None
        self._published = True

    async def discarded(self) -> None:
        try:
            if self._file is not None:
                with suppress(asyncssh.Error, OSError, TimeoutError):
                    await self._file.close()
                self._file = None
            if not self._published and self._remote is not None:
                with suppress(asyncssh.Error, OSError, TimeoutError):
                    await self._remote.sftp.remove(self._temporary)
        finally:
            await self._stack.aclose()


async def _described(remote: Remote, place: Place) -> Entry | None:
    path = remote.path_of(place.key)
    try:
        attrs = await remote.sftp.lstat(path)
    except _MISSING:
        return None
    is_link = _is_link(attrs)
    if is_link:
        try:
            attrs = await remote.sftp.stat(path)
        except asyncssh.SFTPError:
            return None
    return _entry(place, attrs, is_link)


async def _claimed(remote: Remote, temporary: str, target: str, place: Place) -> None:
    if await remote.sftp.exists(target):
        raise _Carried(FileExistsError(place.key))
    try:
        # The plain rename refuses an existing name, which is the claim.
        await remote.sftp.rename(temporary, target)
    except asyncssh.SFTPFailure:
        if await remote.sftp.exists(target):
            raise _Carried(FileExistsError(place.key)) from None
        raise


async def _replaced(
    remote: Remote, temporary: str, target: str, expected_version: str | None
) -> None:
    try:
        current: asyncssh.SFTPAttrs | None = await remote.sftp.stat(target)
    except _MISSING:
        current = None
    if expected_version is not None and (current is None or _version(current) != expected_version):
        raise VersionChanged
    if current is not None and current.permissions is not None:
        # A script keeps being executable once it is saved.
        await remote.sftp.chmod(temporary, current.permissions & 0o7777)
    try:
        await remote.sftp.posix_rename(temporary, target)
    except asyncssh.SFTPOpUnsupported:
        if current is not None:
            await remote.sftp.remove(target)
        await remote.sftp.rename(temporary, target)
    # The version is the modification time and a server counts it in seconds,
    # so two writes inside one would otherwise read as one.
    previous = current.mtime if current is not None and current.mtime is not None else 0
    moment = max(int(time.time()), int(previous) + 1)
    await remote.sftp.utime(target, (moment, moment))


def _entry(place: Place, attrs: asyncssh.SFTPAttrs, is_link: bool) -> Entry:
    return Entry(
        place=place,
        is_directory=_is_directory(attrs),
        size_bytes=attrs.size or 0,
        modified_at=_moment(attrs.mtime),
        is_link=is_link,
        accessed_at=_moment(attrs.atime),
        permissions=(
            stat.filemode(attrs.permissions) if attrs.permissions is not None else None
        ),
    )


def _version(attrs: asyncssh.SFTPAttrs) -> str:
    return f"{attrs.mtime}:{attrs.size}"


def _moment(seconds: float | None) -> datetime | None:
    return None if seconds is None else datetime.fromtimestamp(seconds, tz=UTC)


def _is_link(attrs: asyncssh.SFTPAttrs) -> bool:
    if attrs.permissions is not None:
        return stat.S_ISLNK(attrs.permissions)
    return attrs.type == asyncssh.FILEXFER_TYPE_SYMLINK


def _is_directory(attrs: asyncssh.SFTPAttrs) -> bool:
    if attrs.permissions is not None:
        return stat.S_ISDIR(attrs.permissions)
    return attrs.type == asyncssh.FILEXFER_TYPE_DIRECTORY

