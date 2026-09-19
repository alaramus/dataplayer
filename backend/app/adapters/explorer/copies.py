"""Local copies of remote files, for the libraries that read a path (D152).

A table, a workbook, an archive and SQL are read by libraries that open a file
on this machine. A storage that is not this machine's disk lends them a copy,
and this is where every copy lives: one folder beside the personal homes, where
no file source can reach it, emptied when the process starts.

The copies are bounded three ways, as agreed with the owner: a file larger than
`LARGEST_BYTES` is not copied at all — it is downloaded instead — the copies
together hold at most `CAPACITY_BYTES`, and a copy nobody has read for
`IDLE_SECONDS` goes. A copy is kept per version of the file, so a new version
is fetched beside the old one rather than over it while somebody still reads
the old one, and a copy that is being read is never taken away.
"""

import hashlib
import shutil
import tempfile
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import settings

LARGEST_BYTES = 200 * 1024 * 1024
CAPACITY_BYTES = 1024 * 1024 * 1024
IDLE_SECONDS = 60 * 60


class TooLargeToCopy(ValueError):
    """What a file larger than a copy may be is refused with."""

    def __init__(self, name: str) -> None:
        super().__init__(
            f"{name} is larger than {LARGEST_BYTES // (1024 * 1024)} MB; "
            "download it to open it"
        )


@dataclass
class _Copy:
    path: Path
    size_bytes: int
    users: int = 0
    used_at: float = 0.0
    ready: bool = False
    # Held by whoever fetches it, so a second reader of the same version waits
    # for the one fetch rather than starting its own.
    fetching: threading.Lock = field(default_factory=threading.Lock)


class Copies:
    """Every copy this process holds. One process is what makes it correct (D124)."""

    def __init__(
        self,
        root: Path,
        *,
        largest_bytes: int = LARGEST_BYTES,
        capacity_bytes: int = CAPACITY_BYTES,
        idle_seconds: float = IDLE_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.root = root
        self.largest_bytes = largest_bytes
        self._capacity = capacity_bytes
        self._idle = idle_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._copies: dict[tuple[str, str, str], _Copy] = {}

    def clear(self) -> None:
        """Everything a previous process left, gone. Blocking."""
        with self._lock:
            self._copies.clear()
        shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir(parents=True, exist_ok=True)

    def folder_of(self, owner: str) -> Path:
        """Where one storage's copies are: what its SQL engine may read."""
        folder = self.root / _digest(owner)
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    @contextmanager
    def held(
        self,
        owner: str,
        key: str,
        name: str,
        version: str,
        size_bytes: int,
        fetch: Callable[[Path], None],
    ) -> Iterator[Path]:
        """A local file with the bytes of one version of one remote file.

        `fetch` writes those bytes to the path it is given, and is called only
        when no copy of this version is held already. Blocking.
        """
        if size_bytes > self.largest_bytes:
            raise TooLargeToCopy(name)
        identity = (owner, key, version)
        copy = self._taken(identity, name, size_bytes)
        try:
            self._fetched(identity, copy, fetch)
            yield copy.path
        finally:
            with self._lock:
                copy.users -= 1
                copy.used_at = self._clock()
            self._tidy()

    def forget(self, owner: str, keys: Callable[[str], bool]) -> None:
        """Every copy of the nodes `keys` picks that nobody is reading, gone:
        the storage has just written them, and a clock that counts in seconds
        may not say so. Which keys lie below a folder is the storage's to say."""
        with self._lock:
            gone = [
                self._copies.pop(identity)
                for identity, copy in list(self._copies.items())
                if identity[0] == owner and keys(identity[1]) and copy.users == 0
            ]
        for copy in gone:
            shutil.rmtree(copy.path.parent, ignore_errors=True)

    @contextmanager
    def scratch(self, owner: str) -> Iterator[Path]:
        """An empty folder of one storage's own, gone at the end of the block.

        For what is written here on its way to the storage, and for a tree
        fetched whole: neither is kept, and both are under the one root the
        process empties when it starts.
        """
        folder = Path(tempfile.mkdtemp(prefix="scratch-", dir=self.folder_of(owner)))
        try:
            yield folder
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def _taken(self, identity: tuple[str, str, str], name: str, size_bytes: int) -> _Copy:
        owner, key, version = identity
        with self._lock:
            copy = self._copies.get(identity)
            if copy is None:
                path = self.folder_of(owner) / _digest(key) / _digest(version) / name
                copy = _Copy(path=path, size_bytes=size_bytes)
                self._copies[identity] = copy
            copy.users += 1
            copy.used_at = self._clock()
            return copy

    def _fetched(
        self, identity: tuple[str, str, str], copy: _Copy, fetch: Callable[[Path], None]
    ) -> None:
        with copy.fetching:
            if copy.ready:
                return
            copy.path.parent.mkdir(parents=True, exist_ok=True)
            # Written beside its name and moved into place, so a reader never
            # opens half a file under the name the libraries are given.
            partial = copy.path.with_name(f".{uuid.uuid4().hex}.part")
            try:
                fetch(partial)
                partial.replace(copy.path)
            except BaseException:
                partial.unlink(missing_ok=True)
                with self._lock:
                    if self._copies.get(identity) is copy and copy.users <= 1:
                        del self._copies[identity]
                raise
            copy.ready = True

    def _tidy(self) -> None:
        """Forget what nobody has read for a while, then the oldest, down to
        the capacity. A copy in use stays whatever it costs."""
        now = self._clock()
        with self._lock:
            idle = [
                identity
                for identity, copy in self._copies.items()
                if copy.users == 0 and now - copy.used_at > self._idle
            ]
            gone = [self._copies.pop(identity) for identity in idle]
            held = sum(copy.size_bytes for copy in self._copies.values())
            for identity, copy in sorted(self._copies.items(), key=lambda item: item[1].used_at):
                if held <= self._capacity:
                    break
                if copy.users == 0:
                    gone.append(self._copies.pop(identity))
                    held -= copy.size_bytes
        for copy in gone:
            shutil.rmtree(copy.path.parent, ignore_errors=True)


def _digest(value: str) -> str:
    """A folder name for any string: a key may hold separators, an id may not
    be a name this filesystem allows."""
    return hashlib.sha256(value.encode()).hexdigest()[:32]


_COPIES: Copies | None = None


def copies() -> Copies:
    """The process's copies, beside the personal homes and out of their reach."""
    global _COPIES
    if _COPIES is None:
        _COPIES = Copies(Path(settings.USER_STORAGE_ROOT) / ".explorer-copies")
    return _COPIES
