"""Signed-in IMAP sessions kept between requests (D368).

Connecting, TLS and LOGIN cost Gmail about 650 ms and LOGOUT 200 more, on
every request. A session left signed in is lent to the next operation of the
same connection instead, one operation at a time.
"""

import hashlib
import imaplib
import logging
import threading
import time
import uuid
from dataclasses import dataclass

from app.adapters.resources import Pooling

logger = logging.getLogger(__name__)

# Far below the thirty minutes a server must keep an idle session (RFC 3501,
# 5.4), so one handed out is seldom one the server has already dropped.
IDLE_SECONDS = 120.0
# Enough for the folders, a page and a letter read at once; Gmail allows
# fifteen sessions to an account.
MAX_IDLE = 3


@dataclass
class Lent:
    conn: imaplib.IMAP4
    idle_seconds: float


class KeptImap:
    """Idle sessions of one connection, held in the resource store."""

    def __init__(self) -> None:
        self._idle: list[tuple[imaplib.IMAP4, float]] = []
        # Taken and given from the thread pool, not the event loop.
        self._lock = threading.Lock()

    def take(self) -> Lent | None:
        now = time.monotonic()
        stale: list[imaplib.IMAP4] = []
        lent: Lent | None = None
        with self._lock:
            while self._idle:
                conn, since = self._idle.pop()
                if now - since > IDLE_SECONDS:
                    stale.append(conn)
                    continue
                lent = Lent(conn, now - since)
                break
        for conn in stale:
            drop(conn)
        return lent

    def give(self, conn: imaplib.IMAP4) -> None:
        with self._lock:
            if len(self._idle) < MAX_IDLE:
                self._idle.append((conn, time.monotonic()))
                return
        drop(conn)

    async def close(self) -> None:
        with self._lock:
            idle, self._idle = self._idle, []
        for conn, _ in idle:
            drop(conn)


def drop(conn: imaplib.IMAP4) -> None:
    """The socket closed without LOGOUT: a round trip nobody waits for is not paid."""
    try:
        conn.shutdown()
    except Exception:  # noqa: BLE001 - closing a session that may already be gone
        logger.debug("IMAP session did not close cleanly", exc_info=True)


def key_for(connector_id: uuid.UUID, fingerprint_source: str) -> str:
    """Hashed, as ClickHouse's is: the source carries the password."""
    fingerprint = hashlib.sha256(fingerprint_source.encode()).hexdigest()[:16]
    return f"mail-imap:{connector_id}:{fingerprint}"


async def kept_for(pooling: Pooling, fingerprint_source: str) -> KeptImap | None:
    """The connection's sessions, or None where the store keeps nothing (D127)."""
    key = key_for(pooling.connector_id, fingerprint_source)
    if not pooling.store.keeps:
        return await pooling.store.existing(key, KeptImap)

    async def create() -> KeptImap:
        return KeptImap()

    return await pooling.store.get_or_create(key, KeptImap, create)
