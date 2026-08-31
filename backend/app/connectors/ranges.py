"""Reading one `Range` header against a known size.

The HTTP of a ranged response belongs to the transport, not to a source (D52):
an adapter is asked for the bytes between two offsets and knows nothing about
headers, and this module knows nothing about files.

One range only. A multi-range request is answered with the whole body, which
RFC 9110 allows and which no media element ever asks for.
"""

import re
from dataclasses import dataclass

_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")


@dataclass(frozen=True)
class ByteRange:
    """An inclusive range, already resolved against the size of the body."""

    start: int
    end: int

    @property
    def length(self) -> int:
        return self.end - self.start + 1

    def content_range(self, size: int) -> str:
        return f"bytes {self.start}-{self.end}/{size}"


class UnsatisfiableRange(ValueError):
    """The request named bytes the body does not have (RFC 9110, 416)."""


def parse_range(header: str | None, size: int) -> ByteRange | None:
    """The range asked for, or None when the whole body is meant.

    None covers the honest cases for a whole body: no header at all, and a
    header this function does not handle, such as several ranges at once or a
    unit other than bytes. `UnsatisfiableRange` is the one refusal: bytes that
    are not there.
    """
    if header is None:
        return None
    match = _RANGE.match(header.strip())
    if match is None:
        return None

    first, last = match.group(1), match.group(2)
    if not first and not last:
        return None
    if size == 0:
        # There is no byte to point at, so every range is unsatisfiable —
        # including the suffix form, which would otherwise read as "the last
        # nothing of nothing".
        raise UnsatisfiableRange(header)

    if not first:
        # The suffix form: the last N bytes, as in "bytes=-500".
        length = int(last)
        if length <= 0:
            raise UnsatisfiableRange(header)
        return ByteRange(start=max(0, size - length), end=size - 1)

    start = int(first)
    end = int(last) if last else size - 1
    if start >= size or end < start:
        raise UnsatisfiableRange(header)
    return ByteRange(start=start, end=min(end, size - 1))
