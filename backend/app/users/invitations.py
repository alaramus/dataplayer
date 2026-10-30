"""A link that lets an account choose its own password, once.

A new account has no password: its `hashed_password` is a random lock, `!`
followed by noise, which no password verifies against — the convention of a
locked account in `/etc/shadow`. The link is a token naming the account and
the lock it was issued against, so it is spent the moment the password is set
(the lock is gone) and superseded the moment another link is issued (the lock
is new). Nothing is stored beside the account, so there is nothing to clean up.

The superuser copies the link for now; sending it by mail is the next stage.
"""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from jwt.exceptions import InvalidTokenError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core import security
from app.core.config import settings
from app.users.models import PASSWORD_LOCK, InvitationLink, User


def new_lock() -> str:
    return PASSWORD_LOCK + secrets.token_urlsafe(24)


def _key() -> str:
    # Not SECRET_KEY itself: a session token is any token signed with it that
    # names a user, and this one names a user too.
    return settings.SECRET_KEY + ":invitation"


def _lock_of(user: User) -> str:
    return hashlib.sha256(user.hashed_password.encode()).hexdigest()[:32]


def issue(user: User) -> InvitationLink:
    """A link for the account's current lock. The caller locks it first."""
    expires_at = datetime.now(UTC) + timedelta(hours=settings.INVITATION_EXPIRE_HOURS)
    token = jwt.encode(
        {"sub": str(user.id), "exp": expires_at, "lock": _lock_of(user)},
        _key(),
        algorithm=security.ALGORITHM,
    )
    return InvitationLink(
        url=f"{settings.FRONTEND_HOST}/set-password?token={token}",
        expires_at=expires_at,
    )


async def holder(session: AsyncSession, token: str) -> User | None:
    """The account a link is for, while it can still be used."""
    try:
        claims = jwt.decode(token, _key(), algorithms=[security.ALGORITHM])
        user = await session.get(User, uuid.UUID(str(claims["sub"])))
    except (InvalidTokenError, KeyError, ValueError):
        return None
    if user is None or not user.is_active or user.password_set:
        return None
    if not secrets.compare_digest(str(claims.get("lock", "")), _lock_of(user)):
        return None
    return user
