"""Personal access tokens an outside agent enters `/mcp` with (D358).

A token is shown once, when it is made; the server keeps its SHA-256, which is
enough for a random 256-bit secret, and its first characters for the person to
tell one from another. It carries no rights of its own: a call made with it is
its owner's, checked as the owner is checked today.
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic import Field as Constrained
from sqlalchemy import Column, DateTime, Index, String
from sqlmodel import Field, SQLModel, col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.schemas import get_datetime_utc
from app.users.models import User

TokenPolicy = Literal["read_only", "full"]
# The days a token may be made to last. A closed set, as an unlock span is: a
# free number is a field somebody types a decade into. None is no expiry.
ExpiryDays = Literal[7, 30, 90, 365]

PREFIX = "dp_mcp_"
# What the list shows of a token: the prefix and a few characters after it.
SHOWN = len(PREFIX) + 6
# A use is written down at most this often, so a busy client does not turn
# every call into a write.
LAST_USED_STEP = timedelta(minutes=1)


class McpToken(SQLModel, table=True):
    __tablename__ = "mcp_token"
    __table_args__ = (Index("ix_mcp_token_owner", "owner_id"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE"
    )
    name: str = Field(min_length=1, max_length=100)
    policy: str = Field(sa_column=Column(String(16), nullable=False))
    digest: str = Field(
        sa_column=Column(String(64), nullable=False, unique=True)
    )
    shown: str = Field(max_length=32)
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),
    )
    expires_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
    )
    last_used_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
    )


class McpTokenCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Constrained(min_length=1, max_length=100)
    policy: TokenPolicy
    expires_in_days: ExpiryDays | None = None


class McpTokenPublic(BaseModel):
    id: uuid.UUID
    name: str
    policy: TokenPolicy
    shown: str
    created_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None


class McpTokenCreated(McpTokenPublic):
    """The one answer that carries the token itself."""

    token: str


class Caller(BaseModel):
    """Who a verified token speaks for, and what it may do."""

    model_config = ConfigDict(frozen=True)

    token_id: uuid.UUID
    user_id: uuid.UUID
    policy: TokenPolicy


def digest_of(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def policy_of(stored: str) -> TokenPolicy:
    # Anything but the one wider policy reads as the narrow one.
    return "full" if stored == "full" else "read_only"


def public_of(row: McpToken) -> McpTokenPublic:
    return McpTokenPublic(
        id=row.id,
        name=row.name,
        policy=policy_of(row.policy),
        shown=row.shown,
        created_at=row.created_at,
        expires_at=row.expires_at,
        last_used_at=row.last_used_at,
    )


async def list_own(session: AsyncSession, owner_id: uuid.UUID) -> list[McpToken]:
    rows = await session.exec(
        select(McpToken)
        .where(McpToken.owner_id == owner_id)
        .order_by(col(McpToken.created_at).desc())
    )
    return list(rows.all())


async def create(
    session: AsyncSession, owner_id: uuid.UUID, body: McpTokenCreate
) -> McpTokenCreated:
    token = PREFIX + secrets.token_urlsafe(32)
    now = get_datetime_utc()
    row = McpToken(
        owner_id=owner_id,
        name=body.name.strip() or body.name,
        policy=body.policy,
        digest=digest_of(token),
        shown=token[:SHOWN],
        created_at=now,
        expires_at=(
            now + timedelta(days=body.expires_in_days)
            if body.expires_in_days is not None
            else None
        ),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return McpTokenCreated(**public_of(row).model_dump(), token=token)


async def delete_own(
    session: AsyncSession, owner_id: uuid.UUID, token_id: uuid.UUID
) -> bool:
    row = await session.get(McpToken, token_id)
    if row is None or row.owner_id != owner_id:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def verify(session: AsyncSession, token: str) -> Caller | None:
    """The caller a presented token speaks for; None for anything that opens nothing.

    Unknown, expired, and a token whose owner is no longer active are the same
    answer, so a caller learns nothing about which it was.
    """
    if not token.startswith(PREFIX):
        return None
    row = (
        await session.exec(select(McpToken).where(McpToken.digest == digest_of(token)))
    ).first()
    if row is None:
        return None
    now = get_datetime_utc()
    if row.expires_at is not None and row.expires_at <= now:
        return None
    owner = await session.get(User, row.owner_id)
    if owner is None or not owner.is_active:
        return None
    if row.last_used_at is None or now - row.last_used_at >= LAST_USED_STEP:
        row.last_used_at = now
        session.add(row)
        await session.commit()
    return Caller(token_id=row.id, user_id=row.owner_id, policy=policy_of(row.policy))
