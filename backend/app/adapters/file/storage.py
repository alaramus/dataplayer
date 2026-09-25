"""The server's own disk below one folder of a person's home, as a storage (D150).

The containment rule of D8 is judged here and nowhere else: every node id
becomes a place through `place`, which follows links and refuses anything that
lands outside the root. The old application checked it in one branch of one
method, and the check let through any ancestor of the root.

On this disk the explorer's local file is the file itself, so nothing is
copied: reading a table, a workbook or an archive opens it where it lies.
"""

import os
import shutil
import stat as filestat
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import BinaryIO, cast

from app.adapters.actions import ActionRefused, ConnectorDraft
from app.adapters.explorer.storage import (
    LOCAL_SEARCH,
    ROOT,
    Entry,
    Incoming,
    PathPlaces,
    Place,
    VersionChanged,
)
from app.adapters.file.options import FileOptions
from app.adapters.protocol import ConnectionCheckResult


class LocalStorage(PathPlaces):
    search_limits = LOCAL_SEARCH

    def __init__(self, root: Path, *, home_dir: Path | None = None) -> None:
        self._root = root
        self._home_dir = home_dir if home_dir is not None else root

    @property
    def root(self) -> Path:
        return self._root

    @property
    def resolved_root(self) -> Path:
        """The root with symlinks followed: what containment is judged against."""
        return self._root.resolve()

    def path_of(self, place: Place) -> Path:
        """Where a place is on this disk. Only a place from `place` is inside."""
        return self.resolved_root.joinpath(*self.path_at(place).parts)

    # --- where an id lands ---------------------------------------------------

    def place(self, node_id: str | None) -> Place:
        """The place an id names, links followed, never outside the root.

        The message names the node the caller sent and never the layout of
        the server.
        """
        relative = self.relative_path(node_id)
        if not relative.parts:
            return ROOT
        candidate = self._root.joinpath(*relative.parts).resolve()
        # resolve() follows symlinks, so a link out of the root fails here
        # rather than needing a check of its own.
        if not candidate.is_relative_to(self.resolved_root):
            raise ValueError(f"Path outside the connector root: {node_id}")
        below = candidate.relative_to(self.resolved_root)
        # A link inside the root may lead back to the root itself.
        return self.place_at(PurePosixPath(*below.parts))

    def unlinked_place(self, node_id: str) -> Place:
        relative = self.relative_path(node_id)
        candidate = self._root
        for part in relative.parts:
            candidate /= part
            if candidate.is_symlink():
                raise ValueError("Symbolic links are not downloaded")
        return self.place(node_id)

    def check(self) -> ConnectionCheckResult:
        started = time.perf_counter()
        readable = self._is_readable_directory()
        latency_ms = int((time.perf_counter() - started) * 1000)
        if not readable:
            return ConnectionCheckResult(
                ok=False,
                message="The directory does not exist or cannot be read",
                error_kind="config",
                latency_ms=latency_ms,
            )
        return ConnectionCheckResult(
            ok=True, message="Directory is readable", latency_ms=latency_ms
        )

    def _is_readable_directory(self) -> bool:
        try:
            return self._root.is_dir() and os.access(self._root, os.R_OK)
        except OSError:
            return False

    # --- what is there -------------------------------------------------------

    def entry(self, place: Place) -> Entry | None:
        path = self.path_of(place)
        try:
            return _entry(place, path.stat(), path.is_symlink())
        except OSError:
            return None

    def entries(self, place: Place) -> list[Entry]:
        found: list[Entry] = []
        root = self.resolved_root
        with os.scandir(self.path_of(place)) as listing:
            for item in listing:
                path = Path(item.path)
                try:
                    is_link = item.is_symlink()
                    # A link out of the root is not part of the source, and a
                    # broken one cannot be described at all.
                    if is_link and not path.resolve().is_relative_to(root):
                        continue
                    found.append(_entry(self.child(place, item.name), item.stat(), is_link))
                except OSError:
                    continue
        return found

    def has_entries(self, place: Place) -> bool:
        """At the cost of one entry read, rather than a whole listing."""
        try:
            with os.scandir(self.path_of(place)) as listing:
                return next(listing, None) is not None
        except OSError:
            return False

    def version(self, place: Place) -> str:
        facts = self.path_of(place).stat()
        return f"{facts.st_mtime_ns}:{facts.st_size}"

    # --- reading -------------------------------------------------------------

    def open(self, place: Place) -> BinaryIO:
        return self.path_of(place).open("rb")

    @contextmanager
    def local_file(self, place: Place) -> Iterator[Path]:
        yield self.path_of(place)

    def local_root(self) -> Path:
        return self.resolved_root

    @contextmanager
    def local_tree(self, place: Place) -> Iterator[Path]:
        yield self.path_of(place)

    # --- writing -------------------------------------------------------------

    @contextmanager
    def staged(
        self, near: Place, *, prefix: str = ".dataplayer-"
    ) -> Iterator[Path]:
        """Beside where it is going, so publishing is a link or a rename on one
        filesystem rather than a copy."""
        descriptor, temporary = tempfile.mkstemp(
            dir=self.path_of(self.parent(near)), prefix=prefix
        )
        os.close(descriptor)
        staged = Path(temporary)
        try:
            yield staged
        finally:
            staged.unlink(missing_ok=True)

    def publish(
        self,
        staged: Path,
        place: Place,
        *,
        replace: bool = False,
        expected_version: str | None = None,
    ) -> None:
        target = self.path_of(place)
        if not replace:
            # A link makes the name a claim rather than a check: a second
            # request between somebody's check and this line fails here
            # instead of replacing what the first one wrote.
            os.link(staged, target)
            return
        if expected_version is not None and self.version(place) != expected_version:
            raise VersionChanged
        try:
            os.chmod(staged, target.stat().st_mode)
        except FileNotFoundError:
            pass
        os.replace(staged, target)
        if expected_version is not None:
            # The version is the modification time, and two writes inside one
            # tick of a coarse clock would otherwise read as one.
            previous = int(expected_version.partition(":")[0])
            now = max(time.time_ns(), previous + 1)
            os.utime(target, ns=(now, now))

    @contextmanager
    def incoming(self, near: Place, *, prefix: str = ".dataplayer-") -> Iterator[Incoming]:
        # On this disk the staged file already lies beside its target, so
        # what arrives is written straight into it.
        with self.staged(near, prefix=prefix) as staged, staged.open("wb") as writable:
            yield _Arriving(self, staged, cast(BinaryIO, writable))

    @contextmanager
    def filled(self, place: Place) -> Iterator[Path]:
        yield self.path_of(place)

    def make_directory(self, place: Place) -> None:
        self.path_of(place).mkdir()

    def make_file(self, place: Place) -> None:
        # Exclusive creation: a name taken by a file, a folder or a link — even
        # one pointing nowhere — is refused by the call itself.
        target = self.path_of(place)
        try:
            target.touch(exist_ok=False)
        except PermissionError:
            # Windows answers a folder under the name with "access denied"
            # rather than "exists"; Linux says exists.
            if target.exists() or target.is_symlink():
                raise FileExistsError(place.key) from None
            raise

    def rename(self, place: Place, to: Place) -> None:
        target = self.path_of(to)
        # POSIX replaces an existing name silently; the check keeps the answer
        # the same on both platforms.
        if target.exists() or target.is_symlink():
            raise FileExistsError(to.key)
        shutil.move(str(self.path_of(place)), str(target))

    def copy(self, place: Place, to: Place) -> None:
        source = self.path_of(place)
        if source.is_dir():
            shutil.copytree(source, self.path_of(to), symlinks=True)
        else:
            shutil.copy2(source, self.path_of(to))

    def remove(self, place: Place) -> None:
        path = self.path_of(place)
        if not path.is_dir():
            path.unlink()
            return
        shutil.rmtree(path)

    def remove_empty(self, place: Place) -> None:
        self.path_of(place).rmdir()

    # --- a folder as a connection of its own ---------------------------------

    def connection_for(self, place: Place) -> ConnectorDraft:
        """A new file connection rooted in this folder, inside the home."""
        path = self.path_of(place)
        try:
            relative = path.relative_to(self._home_dir.resolve()).as_posix()
        except ValueError:
            raise ValueError("The folder must stay inside your personal storage") from None
        options = FileOptions(path=relative)
        if options.below_home != relative:
            raise ActionRefused(
                "not_applicable", "A connection path cannot start or end with spaces"
            )
        return ConnectorDraft(
            name=place.name,
            adapter_type="file",
            options=options.model_dump(mode="json"),
        )


def _entry(place: Place, facts: os.stat_result, is_link: bool) -> Entry:
    """The facts of one stat, as the platform states them.

    A creation time is reported only where the platform keeps one. Linux keeps
    `st_ctime`, which is when the inode last changed — a different fact wearing
    the same name, and filling the field with it would be a plausible lie.
    """
    birth: float | None = getattr(facts, "st_birthtime", None)
    return Entry(
        place=place,
        is_directory=filestat.S_ISDIR(facts.st_mode),
        size_bytes=facts.st_size,
        modified_at=datetime.fromtimestamp(facts.st_mtime, tz=UTC),
        is_link=is_link,
        accessed_at=datetime.fromtimestamp(facts.st_atime, tz=UTC),
        created_at=None if birth is None else datetime.fromtimestamp(birth, tz=UTC),
        permissions=filestat.filemode(facts.st_mode),
    )


class _Arriving:
    def __init__(self, storage: LocalStorage, staged: Path, writable: BinaryIO) -> None:
        self._storage = storage
        self._staged = staged
        self._writable = writable

    def write(self, data: bytes) -> None:
        self._writable.write(data)

    def publish(self, place: Place, *, replace: bool = False) -> None:
        # Closed first: Windows neither links nor replaces a file held open.
        self._writable.close()
        self._storage.publish(self._staged, place, replace=replace)
