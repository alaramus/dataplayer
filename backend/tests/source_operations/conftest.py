from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlmodel import delete
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.db import async_session_maker
from app.jobs.models import Job
from app.users import crud as user_crud
from app.users.models import User


@pytest.fixture
async def owner(db: AsyncSession) -> User:
    user = await user_crud.get_user_by_email(session=db, email=settings.FIRST_SUPERUSER)
    assert user is not None
    return user


@pytest.fixture(autouse=True)
async def without_jobs() -> AsyncGenerator[None]:
    """Every test here reads "the jobs there are", so it starts with none."""
    async with async_session_maker() as session:
        await session.exec(delete(Job))
        await session.commit()
    yield


@pytest.fixture
def cache() -> MagicMock:
    spy = MagicMock()
    spy.invalidate_connector = AsyncMock()
    return spy
