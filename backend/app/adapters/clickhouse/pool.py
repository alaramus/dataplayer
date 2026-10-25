"""Keeping HTTP connections to a ClickHouse server between requests.

The HTTP interface has no session to keep: what outlives a request is a client
whose connections stay open, so the next page does not pay for a handshake —
a TLS one, for ClickHouse Cloud.
"""

import hashlib
import uuid

import httpx

from app.adapters.resources import Pooling
from app.core.config import settings

# Equal to the timeout of a direct attempt, for the reason PostgreSQL's is.
ACQUIRE_TIMEOUT_SECONDS = 5.0
# Below the server's own keep-alive of ten seconds: a connection the server is
# about to close is not handed to a request that would find it closed.
KEEPALIVE_SECONDS = 5.0


def make_client(*, verify: bool, read_timeout: float | None) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        verify=verify,
        # `read` is how long a statement may go without the server sending a
        # byte: a long analytical read sends nothing until it is done.
        timeout=httpx.Timeout(
            connect=ACQUIRE_TIMEOUT_SECONDS,
            read=read_timeout,
            write=ACQUIRE_TIMEOUT_SECONDS,
            pool=ACQUIRE_TIMEOUT_SECONDS,
        ),
        limits=httpx.Limits(
            max_connections=settings.POOL_MAX_SIZE,
            max_keepalive_connections=settings.POOL_MAX_SIZE,
            keepalive_expiry=KEEPALIVE_SECONDS,
        ),
        # A proxy named in the backend's environment is not the user's to
        # send their password through.
        trust_env=False,
    )


class KeptClient:
    """An HTTP client held in the resource store."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def close(self) -> None:
        await self.client.aclose()


def key_for(connector_id: uuid.UUID, fingerprint_source: str) -> str:
    """Hashed, as MySQL's pool key is: the source carries the password."""
    fingerprint = hashlib.sha256(fingerprint_source.encode()).hexdigest()[:16]
    return f"clickhouse:{connector_id}:{fingerprint}"


async def client_for(
    pooling: Pooling, fingerprint_source: str, *, verify: bool
) -> KeptClient | None:
    """The connector's client, or None where the store makes none to keep (D127)."""
    key = key_for(pooling.connector_id, fingerprint_source)
    if not pooling.store.keeps:
        return await pooling.store.existing(key, KeptClient)

    async def create() -> KeptClient:
        return KeptClient(make_client(verify=verify, read_timeout=None))

    return await pooling.store.get_or_create(key, KeptClient, create)
