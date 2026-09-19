"""A storage that says how much of it was read, and what was copied out of it.

A remote storage is paid for by the byte: a viewer that needs a header must
read a header, and must not ask for a local copy of the whole file (D152). The
local disk hides the difference, because its copy is the file itself, so the
tests that care use this instead.
"""

import io
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO

from app.adapters.explorer.storage import Place
from app.adapters.file.storage import LocalStorage

# As the SFTP storage buffers, so a header read here costs what it would there.
BUFFER_BYTES = 64 * 1024


class CountingStorage(LocalStorage):
    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.read_bytes = 0
        self.copied: list[str] = []

    def open(self, place: Place) -> BinaryIO:
        raw = _Counted(self.path_of(place).open("rb", buffering=0), self)
        return io.BufferedReader(raw, buffer_size=BUFFER_BYTES)

    @contextmanager
    def local_file(self, place: Place) -> Iterator[Path]:
        self.copied.append(place.key)
        with super().local_file(place) as path:
            yield path


class _Counted(io.RawIOBase):
    def __init__(self, inner: io.FileIO, owner: CountingStorage) -> None:
        super().__init__()
        self._inner = inner
        self._owner = owner

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def readinto(self, buffer: memoryview) -> int:  # type: ignore[override]  # io's own signature takes a writable buffer
        count = self._inner.readinto(buffer)
        self._owner.read_bytes += count
        return count

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        return self._inner.seek(offset, whence)

    def tell(self) -> int:
        return self._inner.tell()

    def close(self) -> None:
        self._inner.close()
        super().close()

