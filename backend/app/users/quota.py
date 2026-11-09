"""How much a person's directory may hold (D324).

The server's figure applies unless a superuser set another for that person.
Those figures are held in this process and loaded at start: an adapter is
built in many places without a session, and asking the database there would
be a query per write. That holds because the backend is one process (D124).
"""

import uuid

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.users.models import User

MEGABYTE = 1024 * 1024

_set_for: dict[uuid.UUID, int] = {}


async def load(session: AsyncSession) -> None:
    rows = await session.exec(
        select(User.id, User.storage_quota_mb).where(col(User.storage_quota_mb).is_not(None))
    )
    _set_for.clear()
    for user_id, megabytes in rows.all():
        if megabytes is not None:
            _set_for[user_id] = megabytes


def remember(user_id: uuid.UUID, megabytes: int | None) -> None:
    if megabytes is None:
        _set_for.pop(user_id, None)
    else:
        _set_for[user_id] = megabytes


def limit_bytes(user_id: uuid.UUID) -> int | None:
    """The limit in bytes, or None for none; zero megabytes means none."""
    megabytes = _set_for.get(user_id, settings.USER_STORAGE_QUOTA_MB)
    return None if megabytes == 0 else megabytes * MEGABYTE
