"""Transactions this process is holding open for somebody.

D66: a manual transaction leases a physical connection lazily, keeps its state
visible, and ends only by an explicit Commit or Rollback — or by the lease
running out, because a connection held by a browser tab somebody closed is a
connection nobody will ever give back.

Process-local, like the result store and the runner, and for the same reason:
what is held is a connection, which does not cross a process. A transaction is
therefore never restored after a restart; there is nothing to restore, and the
database has already rolled it back.
"""

import asyncio
import logging
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, Request
from pydantic import BaseModel

from app.adapters.query import QueryTransaction, TransactionState
from app.core.schemas import get_datetime_utc

logger = logging.getLogger(__name__)


@dataclass
class Lease:
    """One open transaction, and who is holding it."""

    id: str
    owner_id: uuid.UUID
    connector_id: uuid.UUID
    connector_label: str
    document_id: uuid.UUID | None
    transaction: QueryTransaction
    opened_at: datetime
    used_at: datetime
    # A run is going on this transaction; the sweep leaves it alone.
    busy: bool = field(default=False)


class TransactionPublic(BaseModel):
    """An open transaction as the console reads it.

    This is also the commit preview: everything D66 asks to be listed before
    committing — the context, how long it has been open, what it has changed
    and where — is here, so there is no second shape that could disagree with
    the first.
    """

    id: str
    connector_id: uuid.UUID
    connector_label: str
    document_id: uuid.UUID | None
    state: TransactionState
    opened_at: datetime
    used_at: datetime
    expires_at: datetime
    # How long it has been open, in seconds, so a screen does not have to do
    # clock arithmetic to say "seven minutes".
    age_seconds: float


class QuerySessions:
    """Every transaction this process holds, and the lease that ends them."""

    def __init__(self, *, idle_seconds: float) -> None:
        self._idle_seconds = idle_seconds
        self._leases: dict[str, Lease] = {}
        self._lock = asyncio.Lock()

    async def open(
        self,
        *,
        owner_id: uuid.UUID,
        connector_id: uuid.UUID,
        connector_label: str,
        document_id: uuid.UUID | None,
        transaction: QueryTransaction,
    ) -> Lease:
        now = get_datetime_utc()
        lease = Lease(
            id=secrets.token_urlsafe(18),
            owner_id=owner_id,
            connector_id=connector_id,
            connector_label=connector_label,
            document_id=document_id,
            transaction=transaction,
            opened_at=now,
            used_at=now,
        )
        async with self._lock:
            self._leases[lease.id] = lease
        return lease

    async def get(self, session_id: str, *, owner_id: uuid.UUID) -> Lease | None:
        """One transaction, if it belongs to this caller.

        Ownership here rather than in a route comparing ids: a transaction is a
        connection somebody else is holding, and an opaque id is not a right to
        it — the same rule a captured result follows.
        """
        async with self._lock:
            lease = self._leases.get(session_id)
            return lease if lease is not None and lease.owner_id == owner_id else None

    async def touch(self, session_id: str) -> None:
        async with self._lock:
            lease = self._leases.get(session_id)
            if lease is not None:
                lease.used_at = get_datetime_utc()

    async def mark_busy(self, session_id: str, busy: bool) -> None:
        async with self._lock:
            lease = self._leases.get(session_id)
            if lease is not None:
                lease.busy = busy
                lease.used_at = get_datetime_utc()

    async def for_document(self, document_id: uuid.UUID) -> Lease | None:
        async with self._lock:
            for lease in self._leases.values():
                if lease.document_id == document_id:
                    return lease
        return None

    async def count_for(self, owner_id: uuid.UUID) -> int:
        async with self._lock:
            return sum(1 for lease in self._leases.values() if lease.owner_id == owner_id)

    async def end(self, session_id: str, *, commit: bool) -> None:
        """Commit or roll one back, and let go of the connection either way."""
        async with self._lock:
            lease = self._leases.pop(session_id, None)
        if lease is None:
            return
        try:
            if commit:
                await lease.transaction.commit()
            else:
                await lease.transaction.rollback()
        finally:
            await lease.transaction.aclose()

    async def sweep(self, *, now: datetime | None = None) -> int:
        """Roll back what has been sitting idle longer than the lease.

        Not a tidy-up nobody notices: an open transaction holds locks, and the
        console shows the countdown before this happens (D66).
        """
        moment = now or datetime.now(UTC)
        deadline = moment - timedelta(seconds=self._idle_seconds)
        async with self._lock:
            expired = [
                lease.id
                for lease in self._leases.values()
                if not lease.busy and lease.used_at < deadline
            ]
        for session_id in expired:
            await self.end(session_id, commit=False)
        return len(expired)

    async def aclose(self) -> None:
        """Roll everything back: this process is not going to end them later."""
        async with self._lock:
            leases = list(self._leases)
        for session_id in leases:
            try:
                await self.end(session_id, commit=False)
            except Exception:
                logger.exception("A transaction could not be rolled back at shutdown")

    def public(self, lease: Lease) -> TransactionPublic:
        now = datetime.now(UTC)
        return TransactionPublic(
            id=lease.id,
            connector_id=lease.connector_id,
            connector_label=lease.connector_label,
            document_id=lease.document_id,
            state=lease.transaction.state(),
            opened_at=lease.opened_at,
            used_at=lease.used_at,
            expires_at=lease.used_at + timedelta(seconds=self._idle_seconds),
            age_seconds=(now - lease.opened_at).total_seconds(),
        )


def get_sessions(request: Request) -> QuerySessions:
    sessions = request.app.state.query_sessions
    if not isinstance(sessions, QuerySessions):
        raise RuntimeError("The application has no sessions; is the lifespan running?")
    return sessions


SessionsDep = Annotated[QuerySessions, Depends(get_sessions)]
