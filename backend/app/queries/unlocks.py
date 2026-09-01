"""Deciding whether a person may change anything through a connection.

D66: the owner's policy sits above every grant, the level decides what kind of
statement is admitted, and an unlock is the deliberate movement out of reading.
Three things, in one place, so a route cannot check two of them and forget the
third.
"""

import uuid
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, ConfigDict
from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters.query import ExecutionMode, StatementClass
from app.connectors.models import Connector
from app.core.access import Access, ExecutionPolicy, at_least
from app.core.config import settings
from app.core.schemas import get_datetime_utc

# What a class of statement needs before it may run at all.
NEEDED: dict[StatementClass, Access] = {
    "read": "read",
    "explain": "read",
    "dml": "write",
    "ddl": "structure",
}


class WriteUnlock(SQLModel, table=True):
    """That somebody deliberately left read-only on one connection.

    Per person and per connection, not per document: what was unlocked is the
    ability to change this source, and a second console is the same person
    doing the same thing. It expires by disuse, which is why the last use is
    kept rather than only the moment it was given (D66).
    """

    user_id: uuid.UUID = Field(
        foreign_key="user.id", primary_key=True, ondelete="CASCADE"
    )
    connector_id: uuid.UUID = Field(
        foreign_key="connector.id", primary_key=True, ondelete="CASCADE"
    )
    granted_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
    )
    used_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
    )


class UnlockRequest(BaseModel):
    """Asking to leave read-only, in the words the policy requires.

    Under `confirm_writes` the name of the connection is typed out: a
    deliberate movement is one that cannot be made by pressing what happened to
    be under the pointer.
    """

    model_config = ConfigDict(extra="forbid")

    connector_name: str = ""


class UnlockState(BaseModel):
    """Whether writes are open on this connection, and until when."""

    connector_id: uuid.UUID
    policy: ExecutionPolicy
    access: Access
    unlocked: bool
    # Nothing at all when it is not unlocked, or when the policy forbids it.
    expires_at: datetime | None = None
    # Why it cannot be unlocked, when it cannot.
    reason: str | None = None


class WriteRefused(Exception):
    """This run will not be accepted, and the answer says exactly why."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def _idle_deadline(moment: datetime) -> datetime:
    return moment - timedelta(minutes=settings.QUERY_UNLOCK_IDLE_MINUTES)


async def state_of(
    session: AsyncSession,
    *,
    connector: Connector,
    user_id: uuid.UUID,
    access: Access,
    now: datetime | None = None,
) -> UnlockState:
    """Where this person stands on writing through this connection."""
    moment = now or datetime.now(UTC)
    policy: ExecutionPolicy = connector.execution_policy
    if policy == "read_only":
        return UnlockState(
            connector_id=connector.id,
            policy=policy,
            access=access,
            unlocked=False,
            reason="The owner of this connection allows reading only",
        )
    if not at_least(access, "write"):
        return UnlockState(
            connector_id=connector.id,
            policy=policy,
            access=access,
            unlocked=False,
            reason="You have read access to this connection",
        )
    held = await session.get(WriteUnlock, (user_id, connector.id))
    used = held.used_at if held is not None else None
    if held is None or used is None or used < _idle_deadline(moment):
        return UnlockState(
            connector_id=connector.id, policy=policy, access=access, unlocked=False
        )
    return UnlockState(
        connector_id=connector.id,
        policy=policy,
        access=access,
        unlocked=True,
        expires_at=used + timedelta(minutes=settings.QUERY_UNLOCK_IDLE_MINUTES),
    )


async def unlock(
    session: AsyncSession,
    *,
    connector: Connector,
    user_id: uuid.UUID,
    access: Access,
    typed_name: str,
) -> UnlockState:
    """Leave read-only, once the policy's own condition is met.

    Under confirmation the name is typed and compared here rather than in a
    browser: a check a client performs is a check a client can skip.
    """
    if connector.execution_policy == "read_only":
        raise WriteRefused(403, "The owner of this connection allows reading only")
    if not at_least(access, "write"):
        raise WriteRefused(403, "You have read access to this connection")
    if connector.execution_policy == "confirm_writes" and typed_name != connector.name:
        raise WriteRefused(
            422, "Type the name of the connection exactly to allow writing"
        )
    held = await session.get(WriteUnlock, (user_id, connector.id))
    now = get_datetime_utc()
    if held is None:
        held = WriteUnlock(user_id=user_id, connector_id=connector.id)
    held.granted_at = now
    held.used_at = now
    session.add(held)
    await session.commit()
    return await state_of(
        session, connector=connector, user_id=user_id, access=access
    )


async def relock(
    session: AsyncSession, *, connector_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    """Go back to reading, immediately and on purpose."""
    held = await session.get(WriteUnlock, (user_id, connector_id))
    if held is None:
        return
    await session.delete(held)
    await session.commit()


async def touch(
    session: AsyncSession, *, connector_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    """Note that the unlock was used, which is what keeps it alive."""
    held = await session.get(WriteUnlock, (user_id, connector_id))
    if held is None:
        return
    held.used_at = get_datetime_utc()
    session.add(held)
    await session.commit()


async def admit_write(
    session: AsyncSession,
    *,
    connector: Connector,
    user_id: uuid.UUID,
    access: Access,
    mode: ExecutionMode,
    kinds: list[StatementClass],
    confirmed_high_risk: bool,
    risky: bool,
) -> None:
    """Everything that stands between a written statement and the database.

    In this order, because each answer is about something different: what the
    owner allows at all, what this person's level admits, whether they have
    deliberately left read-only, and whether they have just been told what this
    particular statement would do (D66).
    """
    writing = [kind for kind in kinds if kind in ("dml", "ddl")]
    if not writing:
        return
    if mode == "read":
        raise WriteRefused(
            422, "This run is in read mode; choose auto-commit or a transaction"
        )
    if connector.execution_policy == "read_only":
        raise WriteRefused(403, "The owner of this connection allows reading only")
    for kind in writing:
        needed = NEEDED.get(kind, "own")
        if not at_least(access, needed):
            raise WriteRefused(
                403, f"A {kind} statement needs {needed} access to this connection"
            )
    state = await state_of(
        session, connector=connector, user_id=user_id, access=access
    )
    if not state.unlocked:
        raise WriteRefused(
            409, "Writing is not unlocked on this connection"
        )
    if risky and not confirmed_high_risk:
        raise WriteRefused(
            409,
            "This run asks for something that cannot be undone; confirm it first",
        )
