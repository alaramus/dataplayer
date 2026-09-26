from collections.abc import AsyncGenerator, AsyncIterator
from pathlib import Path

import pytest
from sqlmodel import col, delete
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.db import async_session_maker
from app.jobs.models import Job
from app.pipelines.models import Pipeline
from app.users import crud, storage
from tests.utils.relation_fixture import make_schema, run


@pytest.fixture
async def clean() -> AsyncIterator[None]:
    """Pipelines and their runs go with the test that made them."""
    yield
    async with async_session_maker() as session:
        await session.exec(delete(Pipeline))
        await session.exec(delete(Job).where(col(Job.kind) == "pipeline.run"))
        await session.commit()


@pytest.fixture
async def home(db: AsyncSession) -> Path:
    """The personal directory of the user the route tests sign in as."""
    user = await crud.get_user_by_email(session=db, email=settings.EMAIL_TEST_USER)
    assert user is not None
    home = storage.create_home(user.id)
    (home / "reports").mkdir(exist_ok=True)
    return home


@pytest.fixture
async def schema() -> AsyncGenerator[str]:
    async for name in make_schema():
        await run(f"INSERT INTO {name}.regions VALUES (1, 'EU'), (2, 'US')")  # noqa: S608 -- a fixture's own schema name
        yield name
