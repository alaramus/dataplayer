"""A request the daemon upgrades to a raw stream: attach, and exec (D406).

httpx has no way to hand over a connection it upgraded, so the request is
written here on a byte stream the caller opened — a Unix socket for the
services, a forwarded port for the source.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

type Connect = Callable[[], Awaitable[tuple[asyncio.StreamReader, asyncio.StreamWriter]]]


class UpgradeRefused(Exception):
    """The daemon answered the upgrade with something other than a stream."""


def upgrade_request(path: str, body: bytes = b"") -> bytes:
    """`POST <path>` asking for the connection to become the stream."""
    head = (
        f"POST {path} HTTP/1.1\r\n"
        "Host: docker\r\n"
        "Upgrade: tcp\r\n"
        "Connection: Upgrade\r\n"
    )
    if body:
        head += "Content-Type: application/json\r\n"
    head += f"Content-Length: {len(body)}\r\n\r\n"
    return head.encode() + body


async def upgraded(reader: asyncio.StreamReader, seconds: float) -> None:
    """Read the daemon's answer up to where the stream begins."""
    async with asyncio.timeout(seconds):
        head = await reader.readuntil(b"\r\n\r\n")
    status = head.split(b"\r\n", 1)[0].split(b" ")
    code = int(status[1]) if len(status) > 1 and status[1].isdigit() else 0
    # 101 from a daemon that honours the upgrade; 200 from an old one that
    # hijacks the connection without saying so.
    if code not in (101, 200):
        logger.warning("Docker refused an upgrade: %s", head[:200])
        raise UpgradeRefused(str(code))
