"""A container's output out of the daemon's framing, and progress streams (D406)."""

import json
import logging
from typing import Literal

logger = logging.getLogger(__name__)

# The eight-byte header the daemon puts in front of every chunk of a
# container's output when the container has no TTY. Nothing about it is
# optional and nothing about it is documented anywhere near the endpoint, so
# it is named here: one byte of stream, three of padding, four of length.
HEADER = 8

type Stream = Literal["stdin", "stdout", "stderr"]
_STREAMS: dict[int, Stream] = {0: "stdin", 1: "stdout", 2: "stderr"}


def frames(body: bytes) -> list[tuple[Stream, bytes]] | None:
    """Each chunk with the stream it came on, or None for a body not framed.

    A container with a TTY has one plain stream and no headers; whether a body
    is one of those is said by the caller where it knows (`Config.Tty`), and
    guessed here only by the framing not adding up.
    """
    found: list[tuple[Stream, bytes]] = []
    at = 0
    while at + HEADER <= len(body):
        stream = _STREAMS.get(body[at])
        if stream is None or body[at + 1 : at + 4] != b"\0\0\0":
            return None
        size = int.from_bytes(body[at + 4 : at + HEADER], "big")
        chunk = body[at + HEADER : at + HEADER + size]
        if len(chunk) != size:
            return None
        found.append((stream, chunk))
        at += HEADER + size
    if at != len(body):
        return None
    return found


def demultiplexed(body: bytes) -> list[str]:
    """The text out of the daemon's framed output, blank lines left out.

    A body that does not parse as frames is returned as it stands rather than
    mangled.
    """
    if not body:
        return []
    found = frames(body)
    text = body if found is None else b"".join(chunk for _, chunk in found)
    decoded = text.decode("utf-8", errors="replace")
    return [line for line in decoded.splitlines() if line.strip()]


def stream_failed(line: str) -> bool:
    """Whether one line of a JSON-lines progress stream reports a failure.

    A pull or a build answers 200 and then says what it is doing, so an error
    arrives inside a response the daemon called successful.
    """
    if not line.strip():
        return False
    try:
        message = json.loads(line)
    except ValueError:
        return False
    if isinstance(message, dict) and ("error" in message or "errorDetail" in message):
        logger.warning("Docker reported a failure in a stream: %s", str(message)[:500])
        return True
    return False
