"""What counts as text inside a file: one rule for the live search and the kept
one (D218), so the two never disagree about a file.

A directory or a link is not read, a file above the storage's ceiling is not
read, and one whose first bytes hold a zero byte is binary. What is read is
UTF-8, a byte it cannot decode replaced rather than refused.
"""

import hashlib
from dataclasses import dataclass

from app.adapters.explorer.binary import SNIFF_BYTES, bytes_look_binary
from app.adapters.explorer.storage import Entry, Storage

ENCODING = "utf-8"


def readable(entry: Entry, file_bytes: int) -> bool:
    """Whether the file is one the rule reads at all, before it is opened."""
    return not entry.is_directory and not entry.is_link and entry.size_bytes <= file_bytes


@dataclass(frozen=True)
class Extracted:
    """A file's lines, or why there are none, and what reading it cost."""

    lines: list[str] | None
    # Of the bytes read: what tells a pass the text did not change though the
    # file's time did.
    digest: str | None = None
    read_bytes: int = 0


def extract(storage: Storage, entry: Entry, file_bytes: int) -> Extracted:
    """Every line of a text file, whole, for the kept contents. Blocking."""
    if not readable(entry, file_bytes):
        return Extracted(lines=None)
    try:
        with storage.open(entry.place) as raw:
            data = raw.read(file_bytes + 1)
    except OSError:
        return Extracted(lines=None)
    if len(data) > file_bytes or bytes_look_binary(data[:SNIFF_BYTES]):
        return Extracted(lines=None, read_bytes=len(data))
    return Extracted(
        lines=data.decode(ENCODING, errors="replace").splitlines(),
        digest=hashlib.sha256(data).hexdigest(),
        read_bytes=len(data),
    )
