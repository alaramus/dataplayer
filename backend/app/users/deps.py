from typing import Annotated

import jwt
from fastapi import Depends, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pydantic import ValidationError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core import security
from app.core.config import settings
from app.core.db import SessionDep
from app.core.problems import Problem
from app.users.models import TokenPayload, User

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/login/access-token"
)

TokenDep = Annotated[str, Depends(reusable_oauth2)]


def _subject(token: str) -> TokenPayload | None:
    """What a token claims, or nothing if it does not hold up."""
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        return TokenPayload(**payload)
    except InvalidTokenError, ValidationError:
        return None


async def user_for_token(session: AsyncSession, token: str) -> User | None:
    """Whom a token stands for, or nobody.

    Separate from the dependency below because a WebSocket has no request to
    raise an HTTP status into: it takes a token as its first frame and either
    goes on or hangs up. Which tokens are accepted is decided in one place all
    the same.
    """
    claim = _subject(token)
    if claim is None:
        return None
    user = await session.get(User, claim.sub)
    if user is None or not user.is_active:
        return None
    return user


async def get_current_user(session: SessionDep, token: TokenDep) -> User:
    """Whom this request is from, or 401.

    401 and not 403, which is what this used to answer. The two say different
    things — "I do not know who you are" against "I know, and you may not" —
    and while a level was never refused to anybody the difference cost nothing.
    It does now: the client signs a user out when the server rejects who they
    are, and under the old status a grant too low to run one action would have
    signed them out of the application (D33).
    """
    claim = _subject(token)
    if claim is None:
        raise Problem(
            status.HTTP_401_UNAUTHORIZED,
            "auth.not_signed_in",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = await session.get(User, claim.sub)
    if not user:
        raise Problem(
            status.HTTP_401_UNAUTHORIZED,
            "auth.not_signed_in",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        # Also 401: the account exists and cannot be used, so the session it
        # is holding is over.
        raise Problem(
            status.HTTP_401_UNAUTHORIZED,
            "auth.inactive_user",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_current_active_superuser(current_user: CurrentUser) -> User:
    if not current_user.is_superuser:
        raise Problem(403, "auth.not_enough_privileges")
    return current_user
